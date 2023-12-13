# encoding: utf-8

import logging
import os


from botocore.exceptions import ClientError

from ckan import model
from ckan.common import request

from ckanext.s3filestore import uploader
from ckan.lib.uploader import ResourceUpload as DefaultResourceUpload
from ckan.plugins.toolkit import abort, _, g, get_action, \
    NotAuthorized, ObjectNotFound, redirect_to

from ckanext.s3filestore.uploader import S3Uploader, BaseS3Uploader

log = logging.getLogger(__name__)


def resource_download(package_type, id, resource_id, filename=None):
    '''
    Provide a download by either redirecting the user to the url stored or
    downloading the uploaded file from S3.
    '''
    context = {u'model': model,
               u'session': model.Session,
               u'user': g.user,
               u'auth_user_obj': g.userobj}

    try:
        rsc = get_action(u'resource_show')(context, {'id': resource_id})
        get_action(u'package_show')(context, {u'id': id})

        if rsc.get('url_type') == 'upload':
            upload = uploader.S3ResourceUploader(rsc)
            return upload.download(rsc['id'], filename)

        elif u'url' not in rsc:
            return abort(404, _(u'No download is available'))

        # if we're trying to download a link resource, just redirect to it
        return redirect_to(rsc['url'])
    except ObjectNotFound:
        return abort(404, _(u'Resource not found'))
    except NotAuthorized:
        return abort(401, _(u'Not authorized to download resource %s') % id)
    except (IOError, OSError):
        return abort(404, _('Resource data not found'))


def filesystem_resource_download(package_type, id, resource_id, filename=None):
    """
    Provide a direct download by either redirecting the user to the url
    stored or downloading an uploaded file directly.
    """
    context = {u'model': model,
               u'session': model.Session,
               u'user': g.user,
               u'auth_user_obj': g.userobj}

    try:
        rsc = get_action(u'resource_show')(context, {u'id': resource_id})
        get_action(u'package_show')(context, {u'id': id})

        upload = DefaultResourceUpload(rsc)
        if hasattr(DefaultResourceUpload, 'download'):
            return upload.download(rsc[u'id'], filename)
        else:
            # Fall back as IUploader is not updated, this needs to stay aligned to core ckan.
            filepath = upload.get_path(rsc[u'id'])
            if hasattr(request, 'call_application'):
                return _pylons_download(filepath)
            else:
                return _flask_download(filepath)

    except ObjectNotFound:
        return abort(404, _(u'Resource not found'))
    except NotAuthorized:
        return abort(401, _(u'Unauthorised to read resource %s') % resource_id)
    except (IOError, OSError):
        return abort(404, _(u'Resource data not found'))


def uploaded_file_redirect(upload_to, filename):
    '''Redirect static file requests to their location on S3.'''
    storage_path = S3Uploader.get_storage_path(upload_to)
    filepath = os.path.join(storage_path, filename)
    base_uploader = BaseS3Uploader()

    try:
        url = base_uploader.get_signed_url_to_key(filepath)
    except ClientError as ex:
        if ex.response[u'Error'][u'Code'] in [u'NoSuchKey', u'404']:
            return abort(404, _(u'Keys not found on S3'))
        else:
            raise ex

    return redirect_to(url)


def _get_package_type(self, id):
    """
    Given the id of a package this method will return the type of the
    package, or 'dataset' if no type is currently set
    """
    pkg = model.Package.get(id)
    if pkg:
        return pkg.type or 'dataset'
    return None


def _pylons_download(filepath):
    import paste
    from pylons import response
    import mimetypes
    fileapp = paste.fileapp.FileApp(filepath)

    status, headers, app_iter = request.call_application(fileapp)
    response.headers.update(dict(headers))
    content_type, content_enc = mimetypes.guess_type(filepath)
    _add_download_headers(filepath, content_type, response)
    response.status = status
    return app_iter


def _flask_download(filepath):
    import flask
    import mimetypes
    resp = flask.send_file(filepath)
    content_type, content_enc = mimetypes.guess_type(filepath)
    _add_download_headers(filepath, content_type, resp)
    return resp


def _add_download_headers(file_path, mime_type, response):
    """ Add appropriate 'Content-Type' and 'Content-Disposition' headers
    to a a file download.
    """
    if mime_type:
        response.headers['Content-Type'] = mime_type
    if mime_type != 'application/pdf':
        file_name = file_path.split('/')[-1]
        response.headers['Content-Disposition'] = \
            'attachment; filename=' + file_name
