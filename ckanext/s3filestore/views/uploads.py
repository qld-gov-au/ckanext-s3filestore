# encoding: utf-8
import os
import logging

import flask

import ckantoolkit as toolkit

from ckanext.s3filestore.uploader import S3Uploader, BaseS3Uploader


Blueprint = flask.Blueprint
redirect = toolkit.redirect_to
log = logging.getLogger(__name__)

s3_uploads = Blueprint(
    u's3_uploads',
    __name__
)


def uploaded_file_redirect(upload_to, filename):
    '''Redirect static file requests to their location on S3.'''

    storage_path = S3Uploader.get_storage_path(upload_to)
    filepath = os.path.join(storage_path, filename)
    base_uploader = BaseS3Uploader()
    client = base_uploader.get_s3_client()
    bucket = base_uploader.bucket_name

    url = client.generate_presigned_url(ClientMethod='get_object',
                                        Params={'Bucket': bucket,
                                                'Key': filepath
                                                })
    return redirect(url)


s3_uploads.add_url_rule(u'/uploads/<upload_to>/<filename>', view_func=uploaded_file_redirect)


def get_blueprints():
    return [s3_uploads]
