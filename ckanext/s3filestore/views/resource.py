# encoding: utf-8

import logging

import flask

from ckan.plugins.toolkit import config, asbool
from ckan.lib.uploader import ResourceUpload as DefaultResourceUpload

from . import resource_download, filesystem_resource_download

log = logging.getLogger(__name__)

Blueprint = flask.Blueprint

s3_resource = Blueprint(
    u's3_resource',
    __name__,
    url_prefix=u'/dataset/<id>/resource',
    url_defaults={u'package_type': u'dataset'}
)

# IUploader interface does not handle download, like qgov version does, override core ckan controllers
if not hasattr(DefaultResourceUpload, 'download'):
    # Override the resource download links
    s3_resource.add_url_rule(u'/<resource_id>/download',
                             view_func=resource_download)
    s3_resource.add_url_rule(u'/<resource_id>/download/<filename>',
                             view_func=resource_download)

# fallback controller action to download from the filesystem
s3_resource.add_url_rule(u'/<resource_id>/fs_download/<filename>',
                         view_func=filesystem_resource_download)

# Allow fallback to access old files
if not asbool(config.get('ckanext.s3filestore.use_filename', False)):
    s3_resource.add_url_rule(
        u'/<resource_id>/orig_download/<filename>', view_func=resource_download
    )


def get_blueprints():
    return [s3_resource]
