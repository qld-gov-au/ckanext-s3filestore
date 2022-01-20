# encoding: utf-8

import flask

from . import resource_download, filesystem_resource_download

Blueprint = flask.Blueprint

s3_resource = Blueprint(
    u's3_resource',
    __name__,
    url_prefix=u'/dataset/<id>/resource',
    url_defaults={u'package_type': u'dataset'}
)

s3_resource.add_url_rule(u'/<resource_id>/download',
                         view_func=resource_download)
s3_resource.add_url_rule(u'/<resource_id>/download/<filename>',
                         view_func=resource_download)
s3_resource.add_url_rule(u'/<resource_id>/fs_download/<filename>',
                         view_func=filesystem_resource_download)


def get_blueprints():
    return [s3_resource]
