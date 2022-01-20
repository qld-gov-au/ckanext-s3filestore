# encoding: utf-8
import requests
import six

from nose.tools import assert_raises, with_setup
from werkzeug.datastructures import FileStorage as FlaskFileStorage

from ckan.lib.helpers import url_for
from ckantoolkit import config
from ckan.tests import helpers, factories

from . import _get_status_code, _get_response_body, teardown_function


@with_setup(teardown=teardown_function)
@helpers.change_config("ckan.plugins", "webpage_view s3filestore")
@helpers.change_config("ckan.views.default_views", "webpage_view")
def test_view_shown_for_url_type_upload(app=None):

    if not app:
        app = helpers._get_test_app()

    dataset = factories.Dataset()
    context = {u'user': factories.Sysadmin()[u'name']}

    content = u"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <title>WebpageView</title>
                </head>
                <body>
                </body>
                </html>
               """
    resource = helpers.call_action(
        'resource_create',
        package_id=dataset['id'],
        upload=FlaskFileStorage(six.StringIO(content), u'test.html')
    )

    resource_view = helpers.call_action(u'resource_view_list', context,
                                        id=resource[u'id'])[0]

    with assert_raises(KeyError):
        assert resource_view[u'page_url']

    resource_view_src_url = url_for(
        u's3_resource.resource_download',
        id=dataset[u'name'],
        resource_id=resource[u'id']
    )

    url = url_for(
        u'resource.read', id=dataset[u'name'], resource_id=resource[u'id']
    )

    response = app.get(url)

    assert (u'/dataset/{0}/resource/{1}/download?preview=True'
            .format(dataset[u'id'], resource[u'id'])
            in response)

    status_code, location = _get_expecting_redirect(resource_view_src_url)

    r = requests.get(location)

    assert u'<title>WebpageView</title>' in _get_response_body(r)


def _get_expecting_redirect(url, app=None):
    if url.startswith('http:') or url.startswith('https:'):
        site_url = config.get('ckan.site_url')
        url = url.replace(site_url, '')
    if not app:
        app = helpers._get_test_app()
    response = app.get(url, follow_redirects=False)
    status_code = _get_status_code(response)
    assert status_code in [301, 302], \
        "%s resulted in %s instead of a redirect" % (url, response.status)
    return status_code, response.location
