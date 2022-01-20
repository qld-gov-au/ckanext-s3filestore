# encoding: utf-8

from ckan.tests import helpers


def _get_status_code(response):
    """ Get the status code from a HTTP response.
    Supports both Pylons/WebOb and Flask.
    """
    if hasattr(response, 'status_code'):
        return response.status_code
    elif hasattr(response, 'status_int'):
        return response.status_int
    else:
        raise Exception("No status code found on %s" % response)


def _get_response_body(response):
    if hasattr(response, 'text'):
        return response.text
    else:
        return response.body


def teardown_function(self=None):
    helpers.reset_db()
