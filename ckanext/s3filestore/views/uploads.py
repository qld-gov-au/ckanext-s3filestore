# encoding: utf-8

import flask

from . import uploaded_file_redirect

Blueprint = flask.Blueprint

s3_uploads = Blueprint(
    u's3_uploads',
    __name__
)


s3_uploads.add_url_rule(u'/uploads/<upload_to>/<filename>', view_func=uploaded_file_redirect)


def get_blueprints():
    return [s3_uploads]
