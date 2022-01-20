# encoding: utf-8

import logging
import os

from botocore.exceptions import ClientError

from ckan import model
from ckan.lib import uploader
from ckan.lib.uploader import ResourceUpload as DefaultResourceUpload
from ckan.plugins.toolkit import abort, config, _, g, get_action,\
    NotAuthorized, ObjectNotFound, url_for, redirect_to

from ckanext.s3filestore.uploader import S3Uploader, BaseS3Uploader

log = logging.getLogger(__name__)


def resource_download(id, resource_id, filename=None):
    '''
    Provide a download by either redirecting the user to the url stored or
    downloading the uploaded file from S3.
    '''
    context = {'model': model, 'session': model.Session,
               'user': g.user, 'auth_user_obj': g.userobj}

    try:
        rsc = get_action('resource_show')(context, {'id': resource_id})
    except ObjectNotFound:
        return abort(404, _('Resource not found'))
    except NotAuthorized:
        return abort(401, _('Unauthorized to read resource %s') % id)

    if 'url' not in rsc:
        return abort(404, _('No download is available'))
    elif rsc.get('url_type') == 'upload':
        upload = uploader.get_resource_uploader(rsc)

        if filename is None:
            filename = os.path.basename(rsc['url'])
        key_path = upload.get_path(rsc['id'], filename)

        if filename is None:
            log.warn("Key '%s' not found in bucket '%s'",
                     key_path, upload.bucket_name)

        try:
            url = upload.get_signed_url_to_key(key_path)
            return redirect_to(url)
        except ClientError as ex:
            if ex.response['Error']['Code'] in ['NoSuchKey', '404']:
                # attempt fallback
                if config.get(
                        'ckanext.s3filestore.filesystem_download_fallback',
                        False):
                    log.info('Attempting filesystem fallback for resource %s',
                             resource_id)
                    url = url_for(
                        u's3_resource.filesystem_resource_download',
                        id=id,
                        resource_id=resource_id,
                        filename=filename)
                    return redirect_to(url)

                return abort(404, _('Resource data not found'))
            else:
                raise ex
    # if we're trying to download a link resource, just redirect to it
    return redirect_to(rsc['url'])


def filesystem_resource_download(id, resource_id, filename=None):
    """
    Provide a direct download by either redirecting the user to the url
    stored or downloading an uploaded file directly.
    """
    if hasattr(DefaultResourceUpload, 'download'):
        context = {'model': model, 'session': model.Session,
                   'user': g.user, 'auth_user_obj': g.userobj}

        try:
            rsc = get_action('resource_show')(context, {'id': resource_id})
        except ObjectNotFound:
            return abort(404, _('Resource not found'))
        except NotAuthorized:
            return abort(401, _('Unauthorised to read resource %s') % resource_id)
        upload = DefaultResourceUpload(rsc)
        return upload.download(rsc['id'], filename)
    else:
        try:
            from ckan.views.resource import download
            return download('dataset', id, resource_id, filename)
        except ImportError:
            # pre-Flask
            from ckan.controllers.package import PackageController
            return PackageController().resource_download(id, resource_id, filename)
        except (IOError, OSError):
            # probably file not found
            return abort(404, _('Resource data not found'))


def uploaded_file_redirect(upload_to, filename):
    '''Redirect static file requests to their location on S3.'''
    storage_path = S3Uploader.get_storage_path(upload_to)
    filepath = os.path.join(storage_path, filename)
    base_uploader = BaseS3Uploader()

    try:
        url = base_uploader.get_signed_url_to_key(filepath)
    except ClientError as ex:
        if ex.response['Error']['Code'] in ['NoSuchKey', '404']:
            return abort(404, _('Keys not found on S3'))
        else:
            raise ex

    return redirect_to(url)
