import os

from nose.tools import (assert_equal,
                        assert_true,
                        with_setup)

import requests

import ckan.plugins.toolkit as toolkit
from ckantoolkit import config
import ckan.tests.helpers as helpers
import ckan.tests.factories as factories

import ckanapi

import logging
log = logging.getLogger(__name__)


if toolkit.check_ckan_version('2.9'):

    def setup_function(self):
        helpers.reset_db()

    @with_setup(setup_function)
    class TestS3ControllerResourceDownload():

        def _upload_resource(self):
            factories.Dataset(name="my-dataset")

            file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
            resource = helpers.call_action('resource_create', context={'ignore_auth': True}, package_id='my-dataset',
                                           upload=open(file_path))
            return resource

        @helpers.change_config('ckan.site_url', 'http://mytest.ckan.net')
        def test_resource_show_url(self):
            '''The resource_show url is expected for uploaded resource file.'''

            assert_equal(config.get('ckan.site_url'), 'http://mytest.ckan.net')
            resource = self._upload_resource()

            # does resource_show have the expected resource file url?
            resource_show = helpers.call_action('resource_show', id=resource['id'])

            expected_url = 'http://mytest.ckan.net/dataset/{0}/resource/{1}/download/data.csv' \
                .format(resource['package_id'], resource['id'])

            assert_equal(resource_show['url'], expected_url)

        def test_resource_download_s3(self):
            '''A resource uploaded to S3 can be downloaded.'''

            resource = self._upload_resource()
            resource_show = helpers.call_action('resource_show', id=resource['id'])
            resource_file_url = resource_show['url']

            file_response = requests.get(resource_file_url)
            location = file_response.headers['Location']
            log.info("ckanext.s3filestore.tests: response is: %s, %s", location, file_response)
            assert_equal(file_response.status_int, 302)
            file_response = requests.get(location)
            if hasattr(file_response, 'content_type'):
                content_type = file_response.content_type
            else:
                content_type = file_response.headers.get('Content-Type')
            assert_equal(content_type, "text/csv")
            if hasattr(file_response, 'text'):
                body = file_response.text
            else:
                body = file_response.body
            assert_true('date,price' in body)

        def test_resource_download_wrong_filename(self):
            '''A resource downloaded with the wrong filename gives 404.'''

            resource, demo, app = self._upload_resource()
            resource_file_url = '/dataset/{0}/resource/{1}/fs_download/foo.txt' \
                .format(resource['package_id'], resource['id'])

            file_response = app.get(resource_file_url, expect_errors=True)
            log.info("ckanext.s3filestore.tests: response is: %s", file_response)
            assert_equal(404, file_response.status_int)

        def test_resource_download_s3_no_filename(self):
            '''A resource uploaded to S3 can be downloaded when no filename in
            url.'''

            resource = self._upload_resource()

            resource_file_url = '/dataset/{0}/resource/{1}/download' \
                .format(resource['package_id'], resource['id'])

            file_response = requests.get(resource_file_url)
            location = file_response.headers['Location']
            assert_equal(file_response.status_code, 302)
            file_response = requests.get(location)
            log.info("ckanext.s3filestore.tests: response is: {0}, {1}".format(location, file_response))

            if hasattr(file_response, 'text'):
                body = file_response.text
            else:
                body = file_response.body
            assert_true('date,price' in body)

        def test_resource_download_url_link(self):
            '''A resource with a url (not file) is redirected correctly.'''
            dataset = factories.Dataset()

            resource = helpers.call_action('resource_create', context={'ignore_auth': True}, package_id=dataset['id'],
                                           url='http://example')
            resource_show = helpers.call_action('resource_show', id=resource['id'])
            resource_file_url = '/dataset/{0}/resource/{1}/download' \
                .format(resource['package_id'], resource['id'])
            assert_equal(resource_show['url'], 'http://example')

            # attempt redirect to linked url
            r = requests.get(resource_file_url)
            assert_true(r.status_code in [302, 301])
            assert_equal(r.headers['Location'], 'http://example')

else:

    class TestS3ControllerResourceDownload(helpers.FunctionalTestBase):

        def _upload_resource(self):
            factories.Sysadmin(apikey="my-test-key")

            app = self._get_test_app()
            demo = ckanapi.TestAppCKAN(app, apikey='my-test-key')
            factories.Dataset(name="my-dataset")

            file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
            resource = demo.action.resource_create(package_id='my-dataset',
                                                   upload=open(file_path))
            return resource, demo, app

        @helpers.change_config('ckan.site_url', 'http://mytest.ckan.net')
        def test_resource_show_url(self):
            '''The resource_show url is expected for uploaded resource file.'''

            assert_equal(config.get('ckan.site_url'), 'http://mytest.ckan.net')
            resource, demo, _ = self._upload_resource()

            # does resource_show have the expected resource file url?
            resource_show = demo.action.resource_show(id=resource['id'])

            expected_url = 'http://mytest.ckan.net/dataset/{0}/resource/{1}/download/data.csv' \
                .format(resource['package_id'], resource['id'])

            assert_equal(resource_show['url'], expected_url)

        def test_resource_download_s3(self):
            '''A resource uploaded to S3 can be downloaded.'''

            resource, demo, app = self._upload_resource()
            resource_show = demo.action.resource_show(id=resource['id'])
            resource_file_url = resource_show['url']

            file_response = app.get(resource_file_url)
            location = file_response.headers['Location']
            log.info("ckanext.s3filestore.tests: response is: %s, %s", location, file_response)
            assert_equal(302, file_response.status_int)
            file_response = requests.get(location)
            if hasattr(file_response, 'content_type'):
                content_type = file_response.content_type
            else:
                content_type = file_response.headers.get('Content-Type')
            assert_equal("text/csv", content_type)
            if hasattr(file_response, 'text'):
                body = file_response.text
            else:
                body = file_response.body
            assert_true('date,price' in body)

        def test_resource_download_wrong_filename(self):
            '''A resource downloaded with the wrong filename gives 404.'''

            resource, demo, app = self._upload_resource()
            resource_file_url = '/dataset/{0}/resource/{1}/fs_download/foo.txt' \
                .format(resource['package_id'], resource['id'])

            file_response = app.get(resource_file_url, expect_errors=True)
            log.info("ckanext.s3filestore.tests: response is: %s", file_response)
            assert_equal(404, file_response.status_int)

        def test_resource_download_s3_no_filename(self):
            '''A resource uploaded to S3 can be downloaded when no filename in
            url.'''

            resource, demo, app = self._upload_resource()

            resource_file_url = '/dataset/{0}/resource/{1}/download' \
                .format(resource['package_id'], resource['id'])

            file_response = app.get(resource_file_url)
            location = file_response.headers['Location']
            assert_equal(302, file_response.status_int)
            file_response = requests.get(location)
            log.info("ckanext.s3filestore.tests: response is: {0}, {1}".format(location, file_response))

            if hasattr(file_response, 'text'):
                body = file_response.text
            else:
                body = file_response.body
            assert_true('date,price' in body)

        def test_resource_download_url_link(self):
            '''A resource with a url (not file) is redirected correctly.'''
            factories.Sysadmin(apikey="my-test-key")

            app = self._get_test_app()
            demo = ckanapi.TestAppCKAN(app, apikey='my-test-key')
            dataset = factories.Dataset()

            resource = demo.action.resource_create(package_id=dataset['id'],
                                                   url='http://example')
            resource_show = demo.action.resource_show(id=resource['id'])
            resource_file_url = '/dataset/{0}/resource/{1}/download' \
                .format(resource['package_id'], resource['id'])
            assert_equal(resource_show['url'], 'http://example')

            # attempt redirect to linked url
            r = app.get(resource_file_url, status=[302, 301])
            assert_equal(r.location, 'http://example')
