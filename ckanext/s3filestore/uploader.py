# encoding: utf-8

import cgi
import datetime
import errno
import logging
import mimetypes
import magic
import os
import re
import six

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import ckantoolkit as toolkit
import ckan.lib.helpers as h
from ckan.lib.redis import connect_to_redis

from ckan.common import g
from ckan.lib.uploader import ResourceUpload as DefaultResourceUpload, Upload as DefaultUpload

import ckan.model as model
from ckan.lib import munge

if toolkit.check_ckan_version(min_version='2.7.0'):
    from werkzeug.datastructures import FileStorage as FlaskFileStorage
    ALLOWED_UPLOAD_TYPES = (cgi.FieldStorage, FlaskFileStorage)
else:
    ALLOWED_UPLOAD_TYPES = (cgi.FieldStorage)

config = toolkit.config
log = logging.getLogger(__name__)

_storage_path = None
_max_resource_size = None
_max_image_size = None

URL_HOST = re.compile('^https?://[^/]*/')
REDIS_PREFIX = 'ckanext-s3filestore:'
VISIBILITY_CACHE_PATH = '/visibility'
PUBLIC_ACL = 'public-read'
PRIVATE_ACL = 'private'


def _get_cache_key(path):
    return REDIS_PREFIX + path


def _get_underlying_file(wrapper):
    if isinstance(wrapper, FlaskFileStorage):
        return wrapper.stream
    return wrapper.file


def is_path_addressing():
    if config.get('ckanext.s3filestore.download_proxy'):
        return False
    configured_style = config.get('ckanext.s3filestore.addressing_style', 'auto')
    if configured_style == 'path':
        return True
    if configured_style == 'auto':
        return config.get('ckanext.s3filestore.signature_version') == 's3v4'
    return False


def ensure_ascii(text):
    """ Returns a version of the specified text that contains
    only ASCII characters. 'text' should be UTF-8 encoded.
    Non-ASCII characters may be either stripped or encoded/escaped.
    """
    if not isinstance(text, six.text_type):
        text = six.text_type(text, 'utf-8')
    return text.encode('ascii', 'xmlcharrefreplace').decode()


class S3FileStoreException(Exception):
    pass


def get_s3_session(config):
    if config.get('ckanext.s3filestore.aws_use_ami_role', False):
        p_key = None
        s_key = None
    else:
        p_key = config.get('ckanext.s3filestore.aws_access_key_id')
        s_key = config.get('ckanext.s3filestore.aws_secret_access_key')
    region = config.get('ckanext.s3filestore.region_name')
    return boto3.session.Session(aws_access_key_id=p_key,
                                 aws_secret_access_key=s_key,
                                 region_name=region)


def _is_presigned_url(url):
    ''' Determines whether a URL represents a presigned S3 URL.'''
    parts = url.split('?')
    return len(parts) >= 2 and 'Signature=' in parts[1]


class BaseS3Uploader(object):

    def __init__(self):
        self.bucket_name = config.get('ckanext.s3filestore.aws_bucket_name')
        self.region = config.get('ckanext.s3filestore.region_name')
        self.signature = config.get('ckanext.s3filestore.signature_version')
        self.download_proxy = config.get('ckanext.s3filestore.download_proxy')
        self.signed_url_expiry = int(config.get('ckanext.s3filestore.signed_url_expiry', '3600'))
        self.signed_url_cache_window = int(config.get('ckanext.s3filestore.signed_url_cache_window', '1800'))
        self.signed_url_cache_enabled = self.signed_url_cache_window > 0 and self.signed_url_expiry > 0
        self.acl = config.get('ckanext.s3filestore.acl', PUBLIC_ACL)
        self.non_current_acl = config.get('ckanext.s3filestore.non_current_acl', PRIVATE_ACL)
        self.addressing_style = config.get('ckanext.s3filestore.addressing_style', 'auto')
        if is_path_addressing():
            self.host_name = config.get('ckanext.s3filestore.host_name')
        else:
            self.host_name = None

    def _cache_get(self, key):
        ''' Get a value from the cache, if enabled, otherwise return None.
        Returned values will be converted to text type instead of bytes.
        '''
        if not self.signed_url_cache_enabled:
            return None
        redis_conn = connect_to_redis()
        cache_key = _get_cache_key(key)
        cache_value = redis_conn.get(cache_key)
        if cache_value is not None and hasattr(six, 'ensure_text'):
            cache_value = six.ensure_text(cache_value)
        return cache_value

    def _cache_put(self, key, value):
        ''' Set a value in the cache, if enabled, with an appropriate expiry.
        '''
        cache_key = _get_cache_key(key)
        if self.signed_url_cache_enabled:
            redis_conn = connect_to_redis()
            redis_conn.set(cache_key, value, ex=self.signed_url_cache_window)

    def _cache_delete(self, key):
        ''' Delete a value from the cache, if enabled.
        '''
        cache_key = _get_cache_key(key)
        if self.signed_url_cache_enabled:
            redis_conn = connect_to_redis()
            redis_conn.delete(cache_key)

    def get_directory(self, id, storage_path):
        directory = os.path.join(storage_path, id)
        return directory

    def _get_s3_config(self):
        return Config(
            signature_version=self.signature,
            s3={'addressing_style': self.addressing_style}
        )

    def get_s3_resource(self, session=None):
        if not session:
            session = get_s3_session(config)
        return session.resource('s3',
                                endpoint_url=self.host_name,
                                config=self._get_s3_config())

    def get_s3_client(self, session=None):
        if not session:
            session = get_s3_session(config)
        return session.client('s3',
                              endpoint_url=self.host_name,
                              config=self._get_s3_config())

    def get_s3_bucket(self, bucket_name=None):
        '''Return a boto bucket, creating it if it doesn't exist.'''

        if not bucket_name:
            bucket_name = self.bucket_name

        # make s3 connection using boto3
        s3 = self.get_s3_resource()

        bucket = s3.Bucket(bucket_name)
        try:
            s3.meta.client.head_bucket(Bucket=bucket_name)
            log.debug('Bucket %s found!', bucket_name)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                log.warning('Bucket %s could not be found, attempting to create it...',
                            bucket_name)
                try:
                    bucket = s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={
                        'LocationConstraint': self.region})
                    log.info(
                        'Bucket %s successfully created', bucket_name)
                except ClientError as e:
                    log.warning('Could not create bucket %s: %s',
                                bucket_name, str(e))
            elif error_code == '403':
                raise S3FileStoreException(
                    'Access to bucket {0} denied'.format(bucket_name))
            else:
                raise S3FileStoreException(
                    'Something went wrong for bucket {0}'.format(bucket_name))

        return bucket

    def upload_to_key(self, filepath, upload_file, acl, extra_metadata=None):
        '''Uploads the `upload_file` to `filepath` on `self.bucket`.'''

        upload_file.seek(0)
        mime_type = getattr(self, 'mimetype', '') or 'application/octet-stream'
        log.debug(
            "ckanext.s3filestore.uploader: going to upload [%s] to bucket [%s] "
            "with access [%s] and mimetype [%s]",
            filepath, self.bucket_name, acl, mime_type)

        try:
            kwargs = {
                'Body': upload_file.read(), 'ACL': acl,
                'ContentType': mime_type}
            if mime_type != 'application/pdf':
                filename = filepath.split('/')[-1]
                kwargs['ContentDisposition'] = 'attachment; filename=' + filename
            if extra_metadata:
                kwargs['Metadata'] = extra_metadata

            self.get_s3_resource().Object(self.bucket_name, filepath).put(**kwargs)
            log.info("Successfully uploaded %s to S3!", filepath)
            self._cache_delete(filepath)
            self._cache_delete(filepath + VISIBILITY_CACHE_PATH + '/all')
            self._cache_put(filepath + VISIBILITY_CACHE_PATH, acl)
        except Exception as e:
            log.error('Something went very very wrong when uploading to [%s]: %s', filepath, e)
            raise e

    def clear_key(self, filepath):
        '''Deletes the contents of the key at `filepath` on `self.bucket`.'''
        try:
            self.get_s3_resource().Object(self.bucket_name, filepath).delete()
            log.info("Removed %s from S3", filepath)
            self._cache_delete(filepath)
            self._cache_delete(filepath + VISIBILITY_CACHE_PATH)
        except Exception as e:
            raise e

    def is_key_public(self, key):
        ''' Check whether an S3 object key is publicly readable.
        May cache results to reduce API calls.
        '''
        acl_key = key + VISIBILITY_CACHE_PATH
        acl = self._cache_get(acl_key)
        if acl == PUBLIC_ACL:
            return True
        if acl == PRIVATE_ACL:
            return False

        client = self.get_s3_client()
        # check if the object ACL grants any permission to all users
        acl = PUBLIC_ACL if any(
            grant['Grantee']['Type'] == 'Group'
            and grant['Grantee'].get('URI', '').endswith('AllUsers')
            for grant in client.get_object_acl(Bucket=self.bucket_name, Key=key)['Grants']
        ) else PRIVATE_ACL
        self._cache_put(acl_key, acl)
        return acl == PUBLIC_ACL

    def get_signed_url_to_key(self, key, extra_params={}):
        '''Generates a pre-signed URL giving access to an S3 object,
        or, if the object is already publicly visible, an unsigned URL.

        If a download_proxy is configured, then the URL will be
        generated using the true S3 host, and then the hostname will be
        rewritten afterward. Note that the Host header is part of a
        version 4 signature, so the resulting request, as it stands,
        will fail signature verification; the download_proxy server must
        be configured to set the Host header back to the true value when
        forwarding the request (CloudFront does this automatically).
        '''
        client = self.get_s3_client()

        # check whether the object exists in S3
        log.debug('Checking that S3 object %s exists', key)
        metadata = client.head_object(Bucket=self.bucket_name, Key=key)

        # check whether the object is publicly readable
        is_public_read = self.is_key_public(key)

        cache_url = self._cache_get(key)
        # use cache only if the visibility is still correct
        if cache_url and is_public_read != _is_presigned_url(cache_url):
            log.debug('Returning cached URL for path %s', key)
            return cache_url
        else:
            log.debug('No cache found for %s; generating a new URL', key)

        params = {'Bucket': self.bucket_name,
                  'Key': key}
        if not is_public_read and metadata['ContentType'] != 'application/pdf':
            filename = key.split('/')[-1]
            params['ResponseContentDisposition'] = 'attachment; filename=' + filename
        params.update(extra_params)
        url = client.generate_presigned_url(ClientMethod='get_object',
                                            Params=params,
                                            ExpiresIn=self.signed_url_expiry)
        if self.download_proxy:
            url = URL_HOST.sub(self.download_proxy + '/', url, 1)

        if is_public_read:
            url = url.split('?')[0] + '?ETag=' + metadata['ETag']

        self._cache_put(key, url)
        return url

    def as_clean_dict(self, dict):
        for k, v in dict.items():
            if isinstance(v, datetime.datetime):
                dict[k] = v.isoformat()
        return dict


class S3Uploader(BaseS3Uploader):

    '''
    An uploader class to replace local file storage with Amazon Web Services
    S3 for general files (e.g. Group cover images).
    '''

    def __init__(self, upload_to, old_filename=None):
        '''Setup the uploader. Additional setup is performed by
        update_data_dict(), and actual uploading performed by `upload()`.

        Create a storage path in the format:
        <ckanext.s3filestore.aws_storage_path>/storage/uploads/<upload_to>/
        '''

        super(S3Uploader, self).__init__()

        # Store path if we need to fall back
        self.upload_to = upload_to

        self.storage_path = self.get_storage_path(upload_to)

        self.filename = None
        self.filepath = None

        self.old_filename = old_filename
        if old_filename:
            self.old_filepath = os.path.join(self.storage_path, old_filename)

    @classmethod
    def get_storage_path(cls, upload_to):
        path = config.get('ckanext.s3filestore.aws_storage_path', '')
        return os.path.join(path, 'storage', 'uploads', upload_to)

    def update_data_dict(self, data_dict, url_field, file_field, clear_field):
        log.debug("ckanext.s3filestore.uploader: update_data_dic: %s, url %s, file %s, clear %s",
                  data_dict, url_field, file_field, clear_field)
        '''Manipulate data from the data_dict. This needs to be called before it
        reaches any validators.

        `url_field` is the name of the field where the upload is going to be.

        `file_field` is name of the key where the FieldStorage is kept (i.e
        the field where the file data actually is).

        `clear_field` is the name of a boolean field which requests the upload
        to be deleted.
        '''

        self.url = data_dict.get(url_field, '')
        self.clear = data_dict.pop(clear_field, None)
        self.file_field = file_field
        self.upload_field_storage = data_dict.pop(file_field, None)
        self.upload_file = None
        self.preserve_filename = data_dict.get('preserve_filename', False)

        if not self.storage_path:
            return
        if isinstance(self.upload_field_storage, ALLOWED_UPLOAD_TYPES) \
                and self.upload_field_storage.filename:
            self.filename = self.upload_field_storage.filename
            if not self.preserve_filename:
                self.filename = str(datetime.datetime.utcnow()) + self.filename
            self.filename = munge.munge_filename_legacy(self.filename)
            self.filepath = os.path.join(self.storage_path, self.filename)
            if hasattr(self.upload_field_storage, 'mimetype'):
                self.mimetype = self.upload_field_storage.mimetype
            else:
                try:
                    self.mimetype = mimetypes.guess_type(self.filename, strict=False)[0]
                except Exception:
                    pass
            data_dict[url_field] = self.filename
            self.upload_file = _get_underlying_file(self.upload_field_storage)
            log.debug("ckanext.s3filestore.uploader: is allowed upload type: filename: %s, upload_file: %s, data_dict: %s",
                      self.filename, self.upload_file, data_dict)
        # keep the file if there has been no change
        elif self.old_filename and not self.old_filename.startswith('http'):
            if not self.clear:
                data_dict[url_field] = self.old_filename
            if self.clear and self.url == self.old_filename:
                data_dict[url_field] = ''
        else:
            log.debug(
                "ckanext.s3filestore.uploader: is not allowed upload type: filename: %s, upload_file: %s, data_dict: %s",
                self.filename, self.upload_file, data_dict)

    def upload(self, max_size=2):
        log.debug(
            "upload: %s, %s, max_size %s", self.filename, max_size, self.filepath)
        '''Actually upload the file.

        This should happen just before a commit but after the data has been
        validated and flushed to the db. This is so we do not store anything
        unless the request is actually good. max_size is size in MB maximum of
        the file'''

        # If a filename has been provided (a file is being uploaded) write the
        # file to the appropriate key in the AWS bucket.
        if self.filename:
            self.upload_to_key(self.filepath, self.upload_file,
                               acl=PUBLIC_ACL)
            self.clear = True

        if (self.clear and self.old_filename
                and not self.old_filename.startswith('http')):
            self.clear_key(self.old_filepath)

    def delete(self, filename):
        ''' Delete file we are pointing at'''
        filename = munge.munge_filename_legacy(filename)
        key_path = os.path.join(self.storage_path, filename)
        try:
            self.clear_key(key_path)
        except ClientError:
            log.warning("Key '%s' not found in bucket '%s' for delete",
                        key_path, self.bucket_name)
            pass

    def download(self, filename):
        '''
        Provide a download by either redirecting the user to the url stored or
        downloading the uploaded file from S3.
        '''

        filename = munge.munge_filename_legacy(filename)
        key = os.path.join(self.storage_path, filename)

        if filename is None:
            log.warning("Key '%s' not found in bucket '%s'",
                        filename, self.bucket_name)

        try:
            url = self.get_signed_url_to_key(key)
            h.redirect_to(url)
        except ClientError as ex:
            if ex.response['Error']['Code'] in ['NoSuchKey', '404']:
                if config.get(
                        'ckanext.s3filestore.filesystem_download_fallback',
                        False):
                    log.info('Attempting filesystem fallback for resource %s', id)
                    default_upload = DefaultUpload(self.upload_to)
                    return default_upload.download(filename)

            # Uploader interface does not know about s3 errors
            raise OSError(errno.ENOENT)

    def metadata(self, filename):
        '''
        Provide metadata about the download, such as might be obtained from a HTTP HEAD request.
        Returns a dict that includes 'ContentType', 'ContentLength', 'Hash', and 'LastModified',
        and may include other keys depending on the implementation.
        '''
        filename = munge.munge_filename_legacy(filename)
        key_path = os.path.join(self.storage_path, filename)

        if filename is None:
            log.warning("Key '%s' not found in bucket '%s'",
                        filename, self.bucket_name)

        try:
            client = self.get_s3_client()

            metadata = client.head_object(Bucket=self.bucket_name, Key=key_path)
            metadata['content_type'] = metadata['ContentType']
            metadata['size'] = metadata['ContentLength']
            metadata['hash'] = metadata['ETag']
            return self.as_clean_dict(metadata)
        except ClientError as ex:
            if ex.response['Error']['Code'] in ['NoSuchKey', '404']:
                if config.get(
                        'ckanext.s3filestore.filesystem_download_fallback',
                        False):
                    log.info('Attempting filesystem fallback for resource %s', id)

                    default_upload = DefaultUpload(self.upload_to)
                    return default_upload.metadata(filename)

            # Uploader interface does not know about s3 errors
            raise OSError(errno.ENOENT)


class S3ResourceUploader(BaseS3Uploader):

    '''
    An uploader class to replace local file storage with Amazon Web Services
    S3 for resource files.
    '''

    def __init__(self, resource):
        '''Setup the resource uploader. Actual uploading performed by
        `upload()`.

        Create a storage path in the format:
        <ckanext.s3filestore.aws_storage_path>/resources/
        '''

        super(S3ResourceUploader, self).__init__()

        self.use_filename = toolkit.asbool(config.get('ckanext.s3filestore.use_filename', False))
        path = config.get('ckanext.s3filestore.aws_storage_path', '')
        self.storage_path = os.path.join(path, 'resources')
        self.filename = None
        self.old_filename = None
        self.url = resource['url']
        # Hold onto resource just in case we need to fallback to Default ResourceUpload from core ckan.lib.uploader
        self.resource = resource

        upload_field_storage = resource.pop('upload', None)
        self.clear = resource.pop('clear_upload', None)

        mime = magic.Magic(mime=True)

        if isinstance(upload_field_storage, ALLOWED_UPLOAD_TYPES) \
                and upload_field_storage.filename:
            self.filesize = 0  # bytes

            self.filename = upload_field_storage.filename
            self.filename = munge.munge_filename(self.filename)
            resource['url'] = self.filename
            resource['url_type'] = 'upload'
            resource['last_modified'] = datetime.datetime.utcnow()

            # Check the resource format from its filename extension,
            # if no extension use the default CKAN implementation
            if 'format' not in resource:
                resource_format = os.path.splitext(self.filename)[1][1:]
                if resource_format:
                    resource['format'] = resource_format

            self.upload_file = _get_underlying_file(upload_field_storage)
            self.upload_file.seek(0, os.SEEK_END)
            self.filesize = self.upload_file.tell()
            # go back to the beginning of the file buffer
            self.upload_file.seek(0, os.SEEK_SET)

            self.mimetype = resource.get('mimetype')
            if not self.mimetype:
                try:
                    # 512 bytes should be enough for a mimetype check
                    self.mimetype = resource['mimetype'] = mime.from_buffer(self.upload_file.read(512))

                    # additional check on text/plain mimetypes for
                    # more reliable result, if None continue with text/plain
                    if self.mimetype == 'text/plain':
                        self.mimetype = resource['mimetype'] = \
                            mimetypes.guess_type(self.filename, strict=False)[0] or 'text/plain'
                    # go back to the beginning of the file buffer
                    self.upload_file.seek(0, os.SEEK_SET)
                except Exception:
                    pass
        elif self.clear and resource.get('id'):
            # New, not yet created resources can be marked for deletion if the
            # users cancels an upload and enters a URL instead.
            old_resource = model.Session.query(model.Resource) \
                .get(resource['id'])
            self.old_filename = old_resource.url
            resource['url_type'] = ''

    def get_path(self, id, filename=None):
        '''Return the key used for this resource in S3.

        Keys are in the form:
        <ckanext.s3filestore.aws_storage_path>/resources/<resource id>/<filename>

        e.g.:
        my_storage_path/resources/165900ba-3c60-43c5-9e9c-9f8acd0aa93f/data.csv
        '''

        if filename is None:
            filename = os.path.basename(self.url)
        filename = munge.munge_filename(filename)

        directory = self.get_directory(id, self.storage_path)
        filepath = os.path.join(directory, filename)
        return filepath

    def _get_target_acl(self, resource_id):
        if self.acl == 'auto':
            package = toolkit.get_action('package_show')({'ignore_auth': True}, {'id': self.resource['package_id']})
            return PRIVATE_ACL if package['private'] else PUBLIC_ACL
        else:
            return self.acl

    def update_visibility(self, id, target_acl=None):
        ''' Update the visibility of all S3 objects for a resource
        to match the package, if the ACL config is set to 'auto'.
        '''
        if self.acl != 'auto':
            return
        if not target_acl:
            target_acl = self._get_target_acl(id)

        client = self.get_s3_client()

        current_key = self.get_path(id)
        all_visibility = self._cache_get(current_key + VISIBILITY_CACHE_PATH + '/all')
        if all_visibility is not None and all_visibility == target_acl:
            log.debug("update_visibility: id: %s already set and found in cache as %s", id, target_acl)
            return
        # iterate through every S3 object matching the resource ID
        log.debug("update_visibility: id: %s getting item list from store", id)
        resource_objects = client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=self.get_directory(id, self.storage_path)
        )
        log.debug("update_visibility: id: %s finished item list from store", id)
        if not resource_objects['KeyCount']:
            return

        for upload in resource_objects['Contents']:
            upload_key = upload['Key']
            log.debug("Setting visibility for key [%s], current object is [%s]", upload_key, current_key)
            if upload_key == current_key or self.non_current_acl == 'auto':
                acl = target_acl
            else:
                acl = self.non_current_acl
            is_public_read = self.is_key_public(upload_key)
            # if the ACL status doesn't match what we want, update it
            if (acl == PUBLIC_ACL) != is_public_read:
                log.debug("Updating ACL for object %s to %s", upload_key, acl)
                client.put_object_acl(
                    Bucket=self.bucket_name, Key=upload_key, ACL=acl)
                self._cache_delete(upload_key)
                self._cache_put(upload_key + VISIBILITY_CACHE_PATH, acl)
        self._cache_put(current_key + VISIBILITY_CACHE_PATH + '/all', target_acl)

    def upload(self, id, max_size=10):
        '''Upload the file to S3.'''

        # If a filename has been provided (a file is being uploaded) write the
        # file to the appropriate key in the AWS bucket.
        if self.filename:
            filepath = self.get_path(id, self.filename)
            self.upload_to_key(filepath, self.upload_file, acl=self._get_target_acl(id),
                               extra_metadata=self._get_resource_metadata())
        self.update_visibility(id)

        # The resource form only sets self.clear (via the input clear_upload)
        # to True when an uploaded file is not replaced by another uploaded
        # file, only if it is replaced by a link. If the uploaded file is
        # replaced by a link, we should remove the previously uploaded file to
        # clean up the file system.
        if self.clear and self.old_filename:
            filepath = self.get_path(id, self.old_filename)
            self.clear_key(filepath)

    def _get_resource_metadata(self):
        ''' Retrieve a dict of metadata about the resource,
        to be added to the S3 object.
        '''
        username = g.user if 'user' in dir(g) else '__anonymous__'
        package = toolkit.get_action('package_show')(
            context={'ignore_auth': True}, data_dict={'id': self.resource['package_id']})
        metadata = {
            'package_' + field: ensure_ascii(package[field]) for field in package.keys()
            if field != 'notes' and isinstance(package[field], six.string_types)
        }
        metadata['uploaded_by'] = ensure_ascii(username)
        return metadata

    def delete(self, id, filename=None):
        ''' Delete file we are pointing at'''

        if filename is None:
            filename = os.path.basename(self.url)
        filename = munge.munge_filename(filename)
        key_path = self.get_path(id, filename)
        try:
            self.clear_key(key_path)
        except ClientError:
            log.warning("Key '%s' not found in bucket '%s' for delete",
                        key_path, self.bucket_name)
            pass

    def download(self, id, filename=None):
        '''
        Provide a download by either redirecting the user to the url stored or
        downloading the uploaded file from S3.
        '''

        if not self.use_filename or filename is None:
            filename = os.path.basename(self.url)
        filename = munge.munge_filename(filename)
        key_path = self.get_path(id, filename)

        if filename is None:
            log.warning("Key '%s' not found in bucket '%s'",
                        filename, self.bucket_name)

        try:
            url = self.get_signed_url_to_key(key_path)
            h.redirect_to(url)
        except ClientError as ex:
            if ex.response['Error']['Code'] in ['NoSuchKey', '404']:
                # attempt fallback
                default_resource_upload = DefaultResourceUpload(self.resource)
                return default_resource_upload.download(id, self.filename)
            else:
                # Controller will raise 404 for us
                raise OSError(errno.ENOENT)

    def metadata(self, id, filename=None):
        if filename is None:
            filename = os.path.basename(self.url)
        filename = munge.munge_filename(filename)
        key_path = self.get_path(id, filename)

        if filename is None:
            log.warning("Key '%s' not found in bucket '%s'",
                        filename, self.bucket_name)

        try:
            # Small workaround to manage downloading of large files
            # We are using redirect to minio's resource public URL
            client = self.get_s3_client()

            metadata = client.head_object(Bucket=self.bucket_name, Key=key_path)
            metadata['content_type'] = metadata['ContentType']

            # Drop non public metadata
            metadata.pop('ServerSideEncryption', None)
            metadata.pop('SSECustomerAlgorithm', None)
            metadata.pop('SSECustomerKeyMD5', None)
            metadata.pop('SSEKMSKeyId', None)
            metadata.pop('StorageClass', None)
            metadata.pop('RequestCharged', None)
            metadata.pop('ReplicationStatus', None)
            metadata.pop('ObjectLockLegalHoldStatus', None)

            metadata['size'] = metadata['ContentLength']
            metadata['hash'] = metadata['ETag']
            return self.as_clean_dict(metadata)
        except ClientError as ex:
            if ex.response['Error']['Code'] in ['NoSuchKey', '404']:
                if config.get(
                        'ckanext.s3filestore.filesystem_download_fallback',
                        False):
                    log.info('Attempting filesystem fallback for resource %s', id)

                    default_resource_upload = DefaultResourceUpload(self.resource)
                    return default_resource_upload.metadata(id)

            # Uploader interface does not know about s3 errors
            raise OSError(errno.ENOENT)
