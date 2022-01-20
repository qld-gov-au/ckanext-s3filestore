# encoding: utf-8

import io
import logging
import os
import requests
import six

from nose.tools import (assert_equal,
                        assert_in,
                        with_setup)

from werkzeug.datastructures import FileStorage as FlaskFileStorage

from ckan.plugins import toolkit
from ckan.plugins.toolkit import config
from ckan.lib.helpers import url_for
from ckan.tests import helpers
from ckan.tests import factories

from ckanext.s3filestore import uploader

from . import _get_status_code, _get_response_body, teardown_function

log = logging.getLogger(__name__)


def setup_function(self):
    self.sysadmin = factories.Sysadmin(apikey="my-test-key")

    assert_equal(config.get('ckanext.s3filestore.signature_version'), 's3v4')
    self.bucket_name = config.get(u'ckanext.s3filestore.aws_bucket_name')
    uploader.BaseS3Uploader().get_s3_bucket(self.bucket_name)


def _test_org():
    try:
        return helpers.call_action('organization_show', id='test-org')
    except toolkit.ObjectNotFound:
        user = factories.Sysadmin()
        context = {
            u"user": user["name"]
        }
        return helpers.call_action(
            'organization_create',
            context=context,
            name=u"test-org",
            upload_field_name="image_upload",
            image_upload=FlaskFileStorage(six.BytesIO(b"\0\0\0"), u"image.png"))


@with_setup(setup_function, teardown_function)
class TestS3Controller(object):

    def _upload_resource(self):
        dataset = factories.Dataset(name="my-dataset")

        file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
        resource = helpers.call_action(
            'resource_create',
            package_id=dataset['id'],
            upload=FlaskFileStorage(io.open(file_path, 'rb')))
        return resource

    def test_resource_show_url(self):
        '''The resource_show url is expected for uploaded resource file.'''

        site_url = config.get('ckan.site_url')
        resource = self._upload_resource()
        assert_in('url', resource)

        # does resource_show have the expected resource file url?
        resource_show = helpers.call_action('resource_show', id=resource['id'])
        assert_in('url', resource_show)

        expected_url = site_url + '/dataset/{0}/resource/{1}/download/data.csv' \
            .format(resource['package_id'], resource['id'])

        assert_equal(resource['url'], expected_url)
        assert_equal(resource_show['url'], expected_url)

    def test_resource_download_s3(self):
        '''A resource uploaded to S3 can be downloaded.'''

        resource = self._upload_resource()
        resource_show = helpers.call_action('resource_show', id=resource['id'])
        assert_in('url', resource_show)
        location = resource_show['url']

        status_code, location = self._get_expecting_redirect(location)
        file_response = requests.get(location)
        log.info("ckanext.s3filestore.tests: response is: %s, %s", location, file_response)

        if hasattr(file_response, 'content_type'):
            content_type = file_response.content_type
        else:
            content_type = file_response.headers.get('Content-Type')
        assert_equal(content_type, "text/csv")
        assert_in('date,price', _get_response_body(file_response))

    def test_resource_download_wrong_filename(self):
        '''A resource downloaded with the wrong filename gives 404.'''

        resource = self._upload_resource()
        resource_file_url = '/dataset/{0}/resource/{1}/fs_download/foo.txt' \
            .format(resource['package_id'], resource['id'])

        app = helpers._get_test_app()
        file_response = app.get(resource_file_url, expect_errors=True)
        log.info("ckanext.s3filestore.tests: response is: %s", file_response)
        assert_equal(_get_status_code(file_response), 404)

    def test_resource_download_s3_no_filename(self):
        '''A resource uploaded to S3 can be downloaded when no filename in
        url.'''

        resource = self._upload_resource()

        location = '/dataset/{0}/resource/{1}/download' \
            .format(resource['package_id'], resource['id'])

        status_code, location = self._get_expecting_redirect(location)
        file_response = requests.get(location)
        log.info("ckanext.s3filestore.tests: response is: {0}, {1}".format(location, file_response))

        assert_in('date,price', _get_response_body(file_response))

    def test_resource_download_url_link(self):
        '''A resource with a url (not file) is redirected correctly.'''
        dataset = factories.Dataset()

        resource = helpers.call_action(
            'resource_create',
            package_id=dataset['id'],
            url='http://example')
        resource_show = helpers.call_action('resource_show', id=resource['id'])
        assert_equal(resource_show['url'], 'http://example')

        resource_file_url = '/dataset/{0}/resource/{1}/download' \
            .format(resource['package_id'], resource['id'])
        # attempt redirect to linked url
        status_code, location = self._get_expecting_redirect(resource_file_url)
        assert_equal(location, 'http://example')

    def test_resource_download_url(self):
        u'''The resource url is expected for uploaded resource file.'''
        resource_with_upload = self._upload_resource()

        site_url = config.get('ckan.site_url')
        expected_url = site_url + u'/dataset/{0}/resource/{1}/download/data.csv'.\
            format(resource_with_upload[u'package_id'],
                   resource_with_upload[u'id'])

        assert resource_with_upload['url'] == expected_url

    def test_resource_download_no_filename(self):
        '''A resource uploaded to S3 can be downloaded
        when no filename in url.'''
        resource_with_upload = self._upload_resource()

        resource_file_url = u'/dataset/{0}/resource/{1}/download' \
            .format(resource_with_upload[u'package_id'],
                    resource_with_upload[u'id'])

        status_code, location = self._get_expecting_redirect(resource_file_url)

        assert 302 == status_code

    def test_s3_resource_mimetype(self):
        u'''A resource mimetype test.'''
        resource_with_upload = self._upload_resource()

        assert u'text/csv' == resource_with_upload[u'mimetype']

    def test_organization_image_redirects_to_s3(self):
        organization_with_image = _test_org()
        url = u'/uploads/group/{0}'\
            .format(organization_with_image[u'image_url'])
        status_code, location = self._get_expecting_redirect(url)
        assert 302 == status_code

    def test_organization_image_download_from_s3(self):
        organization_with_image = _test_org()
        url = u'/uploads/group/{0}'\
            .format(organization_with_image[u'image_url'])
        status_code, location = self._get_expecting_redirect(url)
        assert 302 == status_code
        assert location
        image = requests.get(location)
        assert image.content == b"\0\0\0"

    if toolkit.check_ckan_version('2.9'):

        def _get_expecting_redirect(self, url, app=None):
            if url.startswith('http:') or url.startswith('https:'):
                site_url = config.get('ckan.site_url')
                url = url.replace(site_url, '')
            if not app:
                app = helpers._get_test_app()
            response = app.get(url, follow_redirects=False)
            status_code = _get_status_code(response)
            assert_in(status_code, [301, 302],
                      "%s resulted in %s instead of a redirect" % (url, response.status))
            return status_code, response.location

        def test_resource_download(self):
            u'''When trying to download resource
            from CKAN it should redirect to S3.'''
            resource_with_upload = self._upload_resource()

            status_code, location = self._get_expecting_redirect(
                url_for(
                    u'dataset_resource.download',
                    id=resource_with_upload[u'package_id'],
                    resource_id=resource_with_upload[u'id'],
                )
            )
            assert 302 == status_code

        def test_resource_download_not_found(self):
            u'''Downloading a nonexistent resource gives HTTP 404.'''

            app = helpers._get_test_app()
            response = app.get(
                url_for(
                    u'dataset_resource.download',
                    id=u'package_id',
                    resource_id=u'resource_id',
                )
            )
            assert 404 == _get_status_code(response)

        def test_s3_download_link(self):
            u'''A resource download from s3 test.'''
            resource_with_upload = self._upload_resource()

            status_code, location = self._get_expecting_redirect(
                url_for(
                    u'dataset_resource.download',
                    id=resource_with_upload[u'package_id'],
                    resource_id=resource_with_upload[u'id'],
                )
            )
            file_response = requests.get(location)
            assert 'date,price' in _get_response_body(file_response)

    else:

        def _get_expecting_redirect(self, url, app=None):
            if url.startswith('http:') or url.startswith('https:'):
                site_url = config.get('ckan.site_url')
                url = url.replace(site_url, '')
            if not app:
                app = helpers._get_test_app()
            response = app.get(url)
            status_code = _get_status_code(response)
            assert_in(status_code, [301, 302],
                      "%s resulted in %s instead of a redirect" % (url, response.status))
            return status_code, response.headers['Location']

        def test_resource_upload_with_url_and_clear(self):
            '''Test that clearing an upload and using a URL does not crash'''
            dataset = factories.Dataset(name="my-dataset")

            url = toolkit.url_for(controller='package', action='new_resource',
                                  id=dataset['id'])
            env = {'REMOTE_USER': self.sysadmin['name'].encode('ascii')}

            helpers._get_test_app().post(
                url,
                {'clear_upload': True,
                 'id': '',    # Empty id from the form
                 'url': 'http://asdf', 'save': 'save'},
                headers={'Authorization': 'my-test-key'},
                extra_environ=env)
