# encoding: utf-8

import logging

import flask

from ckan.plugins.toolkit import config

from . import resource_download, filesystem_resource_download

log = logging.getLogger(__name__)

Blueprint = flask.Blueprint

s3_resource = Blueprint(
    u's3_resource',
    __name__,
    url_prefix=u'/dataset/<id>/resource'
)


s3_resource.add_url_rule(u'/<resource_id>/download',
                         view_func=resource_download)
s3_resource.add_url_rule(u'/<resource_id>/download/<filename>',
                         view_func=resource_download)
s3_resource.add_url_rule(u'/<resource_id>/fs_download/<filename>',
                         view_func=filesystem_resource_download)

if not config.get('ckanext.s3filestore.use_filename', False):
    s3_resource.add_url_rule(
        u'/<resource_id>/orig_download/<filename>', view_func=resource_download
    )


def get_blueprints():
    return [s3_resource]
