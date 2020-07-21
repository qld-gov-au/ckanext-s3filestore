import os
import cgi
import logging
import datetime
import mimetypes
import errno

import boto3
import botocore
import ckantoolkit as toolkit
import ckan.lib.helpers as h

from ckan.lib.uploader import ResourceUpload as DefaultResourceUpload, Upload as DefaultUpload

import ckan.model as model
import ckan.lib.munge as munge
redirect = toolkit.redirect_to
from botocore.exceptions import ClientError

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


def _get_underlying_file(wrapper):
    if isinstance(wrapper, FlaskFileStorage):
        return wrapper.stream
    return wrapper.file


class S3FileStoreException(Exception):
    pass


class BaseS3Uploader(object):

    def __init__(self):
        self.bucket_name = config.get('ckanext.s3filestore.aws_bucket_name')
        self.p_key = config.get('ckanext.s3filestore.aws_access_key_id', None)
        self.s_key = config.get('ckanext.s3filestore.aws_secret_access_key', None)
        self.region = config.get('ckanext.s3filestore.region_name')
        self.signature = config.get('ckanext.s3filestore.signature_version')
        self.host_name = config.get('ckanext.s3filestore.host_name', None)
        self.acl = config.get('ckanext.s3filestore.acl', 'public-read')
        self.session = None

    def get_directory(self, id, storage_path):
        directory = os.path.join(storage_path, id)
        return directory

    def get_s3_session(self):
        return boto3.session.Session(aws_access_key_id=self.p_key,
                                     aws_secret_access_key=self.s_key,
                                     region_name=self.region)

    def get_s3_resource(self):
        return self.get_s3_session().resource('s3', endpoint_url=self.host_name,
                                     config=botocore.client.Config(
                                     signature_version=self.signature))

    def get_s3_client(self):
        return self.get_s3_session().client('s3', endpoint_url=self.host_name,
                                     config=botocore.client.Config(
                                     signature_version=self.signature))


    def get_s3_bucket(self, bucket_name):
        '''Return a boto bucket, creating it if it doesn't exist.'''

        # make s3 connection using boto3
        s3 = self.get_s3_resource()

        bucket = s3.Bucket(bucket_name)
        try:
            if s3.Bucket(bucket.name) in s3.buckets.all():
                log.info('Bucket {0} found!'.format(bucket_name))

            else:
                log.warning(
                    'Bucket {0} could not be found,\
                    attempting to create it...'.format(bucket_name))
                try:
                    bucket = s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={
                        'LocationConstraint': 'us-east-1'})
                    log.info(
                        'Bucket {0} successfully created'.format(bucket_name))
                except botocore.exceptions.ClientError as e:
                    log.warning('Could not create bucket {0}: {1}'.format(
                        bucket_name, str(e)))
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                log.warning('Bucket {0} could not be found, ' +
                            'attempting to create it...'.format(bucket_name))
                try:
                    bucket = s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={
                        'LocationConstraint': self.region})
                    log.info(
                        'Bucket {0} successfully created'.format(bucket_name))
                except botocore.exceptions.ClientError as e:
                    log.warning('Could not create bucket {0}: {1}'.format(
                        bucket_name, str(e)))
            elif error_code == '403':
                raise S3FileStoreException(
                    'Access to bucket {0} denied'.format(bucket_name))
            else:
                raise S3FileStoreException(
                    'Something went wrong for bucket {0}'.format(bucket_name))

        return bucket

    def upload_to_key(self, filepath, upload_file, make_public=False):
        '''Uploads the `upload_file` to `filepath` on `self.bucket`.'''
        upload_file.seek(0)
        logging.debug("ckanext.s3filestore.uploader: going to upload {0} to bucket {1} with mimetype {2}".format(
            filepath, self.bucket_name, getattr(self, 'mimetype', None)))

        try:
            self.get_s3_resource().Object(self.bucket_name, filepath).put(
                Body=upload_file.read(), ACL=self.acl,
                ContentType=getattr(self, 'mimetype', None))
            log.info("Successfully uploaded {0} to S3!".format(filepath))
        except Exception as e:
            log.error('Something went very very wrong for {0}'.format(str(e)))
            raise e

    def clear_key(self, filepath):
        '''Deletes the contents of the key at `filepath` on `self.bucket`.'''
        try:
            self.get_s3_resource().Object(self.bucket_name, filepath).delete()
        except Exception as e:
            raise e

    def get_signed_url_to_key(self, key_path, expiredin=60):
        # Small workaround to manage downloading of large files
        # We are using redirect to resource public URL
        client = self.get_s3_client()

        # check whether the object exists in S3
        client.head_object(Bucket=self.bucket_name, Key=key_path)

        return client.generate_presigned_url(ClientMethod='get_object',
                                            Params={'Bucket': self.bucket_name,
                                                    'Key': key_path},
                                            ExpiresIn=expiredin)

    def as_clean_dict(self, dict):
        for k, v in dict:
            value = v
            if isinstance(value, datetime.datetime):
                value = value.isoformat()
                dict[k] = value
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

        #Store path if we need to fall back
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
        logging.debug("ckanext.s3filestore.uploader: update_data_dic: {0}, url {1}, file {2}, clear {3}".format(data_dict, url_field, file_field, clear_field))
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
        self.preserve_filename = data_dict.get('preserve_filename', None)

        if not self.storage_path:
            return
        if isinstance(self.upload_field_storage, ALLOWED_UPLOAD_TYPES):
            self.filename = self.upload_field_storage.filename
            if not self.preserve_filename:
                self.filename = str(datetime.datetime.utcnow()) + self.filename
            self.filename = munge.munge_filename_legacy(self.filename)
            self.filepath = os.path.join(self.storage_path, self.filename)
            self.mimetype = self.upload_field_storage.mimetype
            if not self.mimetype:
                try:
                    self.mimetype = mimetypes.guess_type(self.filename, strict=False)[0]
                except Exception:
                    pass
            data_dict[url_field] = self.filename
            self.upload_file = _get_underlying_file(self.upload_field_storage)
            logging.debug("ckanext.s3filestore.uploader: is allowed upload type: filanem: {0}, upload_file: {1}, data_dict: {2}".format(self.filename, self.upload_file, data_dict))
        # keep the file if there has been no change
        elif self.old_filename and not self.old_filename.startswith('http'):
            if not self.clear:
                data_dict[url_field] = self.old_filename
            if self.clear and self.url == self.old_filename:
                data_dict[url_field] = ''
        else:
            logging.debug(
                "ckanext.s3filestore.uploader: is not allowed upload type: filename: {0}, upload_file: {1}, data_dict: {2}".format(
                    self.filename, self.upload_file, data_dict))

    def upload(self, max_size=2):
        logging.debug(
            "upload: {0}, {1}, max_size {2}".format(self.filename, max_size, self.filepath))
        '''Actually upload the file.

        This should happen just before a commit but after the data has been
        validated and flushed to the db. This is so we do not store anything
        unless the request is actually good. max_size is size in MB maximum of
        the file'''

        # If a filename has been provided (a file is being uploaded) write the
        # file to the appropriate key in the AWS bucket.
        if self.filename:
            self.upload_to_key(self.filepath, self.upload_file,
                               make_public=True)
            self.clear = True

        if (self.clear and self.old_filename
                and not self.old_filename.startswith('http')):
            self.clear_key(self.old_filepath)

    def delete(self, filename):
        ''' Delete file we are pointing at'''
        key_path = os.path.join(self.storage_path, filename)
        try:
            self.clear_key(key_path)
        except ClientError as ex:
            log.warning('Key \'{0}\' not found in bucket \'{1}\' for delete'
                        .format(key_path, self.bucket_name))
            pass

    def download(self, filename):
        '''
        Provide a download by either redirecting the user to the url stored or
        downloading the uploaded file from S3.
        '''

        key_path = os.path.join(self.storage_path, filename)

        if key_path is None:
            log.warning('Key \'{0}\' not found in bucket \'{1}\''
                     .format(key_path, self.bucket_name))

        try:
            # Small workaround to manage downloading of large files
            client = self.get_s3_client()

            # check whether the object exists in S3
            client.head_object(Bucket=self.bucket_name, Key=key_path)

            url = client.generate_presigned_url(ClientMethod='get_object',
                                                Params={'Bucket': self.bucket_name,
                                                        'Key': key_path},
                                                ExpiresIn=60)
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
        key_path = os.path.join(self.storage_path, filename)
        key = filename

        if key is None:
            log.warning('Key \'{0}\' not found in bucket \'{1}\''
                     .format(key_path, self.bucket_name))

        try:
            # Small workaround to manage downloading of large files
            # We are using redirect to minio's resource public URL
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

            #Uploader interface does not know about s3 errors
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

        path = config.get('ckanext.s3filestore.aws_storage_path', '')
        self.storage_path = os.path.join(path, 'resources')
        self.filename = None
        self.old_filename = None
        self.url = resource['url']
        # Hold onto resource just in case we need to fallback to Default ResourceUpload from core ckan.lib.uploader
        self.resource = resource

        upload_field_storage = resource.pop('upload', None)
        self.clear = resource.pop('clear_upload', None)

        if isinstance(upload_field_storage, ALLOWED_UPLOAD_TYPES):
            self.filesize = 0  # bytes

            self.filename = upload_field_storage.filename
            self.filename = munge.munge_filename(self.filename)
            resource['url'] = self.filename
            resource['url_type'] = 'upload'
            resource['last_modified'] = datetime.datetime.utcnow()
            self.mimetype = resource.get('mimetype')
            if not self.mimetype:
                try:
                    self.mimetype = resource['mimetype'] = mimetypes.guess_type(self.filename, strict=False)[0]
                except Exception:
                    pass
            self.upload_file = _get_underlying_file(upload_field_storage)
            self.upload_file.seek(0, os.SEEK_END)
            self.filesize = self.upload_file.tell()
            # go back to the beginning of the file buffer
            self.upload_file.seek(0, os.SEEK_SET)
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

        directory = self.get_directory(id, self.storage_path)
        filepath = os.path.join(directory, filename)
        return filepath

    def upload(self, id, max_size=10):
        '''Upload the file to S3.'''

        # If a filename has been provided (a file is being uploaded) write the
        # file to the appropriate key in the AWS bucket.
        if self.filename:
            filepath = self.get_path(id, self.filename)
            self.upload_to_key(filepath, self.upload_file)

        # The resource form only sets self.clear (via the input clear_upload)
        # to True when an uploaded file is not replaced by another uploaded
        # file, only if it is replaced by a link. If the uploaded file is
        # replaced by a link, we should remove the previously uploaded file to
        # clean up the file system.
        if self.clear and self.old_filename:
            filepath = self.get_path(id, self.old_filename)
            self.clear_key(filepath)

    def delete(self, id, filename=None):
        ''' Delete file we are pointing at'''

        if filename is None:
            filename = os.path.basename(self.url)
        key_path = self.get_path(id, filename)
        try:
            self.clear_key(key_path)
        except ClientError as ex:
            log.warning('Key \'{0}\' not found in bucket \'{1}\' for delete'
                        .format(key_path, self.bucket_name))
            pass

    def download(self, id, filename=None):
        '''
        Provide a download by either redirecting the user to the url stored or
        downloading the uploaded file from S3.
        '''


        if filename is None:
            filename = os.path.basename(self.url)
        key_path = self.get_path(id, filename)
        key = filename

        if key is None:
            log.warning('Key \'{0}\' not found in bucket \'{1}\''
                     .format(key_path, self.bucket_name))

        try:
            # Small workaround to manage downloading of large files
            # We are using redirect to minio's resource public URL
            client = self.get_s3_client()

            # check whether the object exists in S3
            client.head_object(Bucket=self.bucket_name, Key=key_path)

            url = client.generate_presigned_url(ClientMethod='get_object',
                                                Params={'Bucket': self.bucket_name,
                                                        'Key': key_path},
                                                ExpiresIn=60)
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
        key_path = self.get_path(id, filename)
        key = filename

        if key is None:
            log.warning('Key \'{0}\' not found in bucket \'{1}\''
                     .format(key_path, self.bucket_name))

        try:
            # Small workaround to manage downloading of large files
            # We are using redirect to minio's resource public URL
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

                    default_resource_upload = DefaultResourceUpload(self.resource)
                    return default_resource_upload.metadata(id)

            #Uploader interface does not know about s3 errors
            raise OSError(errno.ENOENT)


