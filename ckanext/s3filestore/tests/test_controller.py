import os

from nose.tools import (assert_equal,
                        assert_true)

import requests

import ckan.tests.helpers as helpers
import ckan.tests.factories as factories

import ckanapi
import boto3

import logging
log = logging.getLogger(__name__)

# moto s3 client is started externally on localhost:5000
class TestS3ControllerResourceDownload(helpers.FunctionalTestBase):
    endpoint_url = 'http://localhost:5000'

    def __init__(self):
        self.botoSession = boto3.Session(region_name='ap-southeast-2', aws_access_key_id='a', aws_secret_access_key='b')
        conn = self.botoSession.resource('s3', endpoint_url=self.endpoint_url)
        # We need to create the bucket since this is all in Moto's 'virtual' AWS account
        conn.create_bucket(Bucket='my-bucket')

    def _upload_resource(self):
        factories.Sysadmin(apikey="my-test-key")

        app = self._get_test_app()
        demo = ckanapi.TestAppCKAN(app, apikey='my-test-key')
        factories.Dataset(name="my-dataset")

        file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
        resource = demo.action.resource_create(package_id='my-dataset',
                                               upload=open(file_path),
                                               url='file.txt')
        return resource, demo, app

    @helpers.change_config('ckan.site_url', 'http://mytest.ckan.net')
    def test_resource_show_url(self):
        '''The resource_show url is expected for uploaded resource file.'''

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
        #logging.info("ckanext.s3filestore.tests: response is: {0}, {1}".format(location, file_response))
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
        logging.info("ckanext.s3filestore.tests: response is: {0}, {1}".format(location, file_response))

        if hasattr(file_response, 'text'):
            body = file_response.text
        else:
            body = file_response.body
        assert_true('date,price' in body)
        #assert_equal("text/csv", file_response.content_type)

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

    def get_matching_s3_objects(self, s3client, bucket, prefix="", suffix=""):
        """
        Generate objects in an S3 bucket.

        :param bucket: Name of the S3 bucket.
        :param prefix: Only fetch objects whose key starts with
            this prefix (optional).
        :param suffix: Only fetch objects whose keys end with
            this suffix (optional).
        """
        paginator = s3client.get_paginator("list_objects_v2")

        kwargs = {'Bucket': bucket}

        # We can pass the prefix directly to the S3 API.  If the user has passed
        # a tuple or list of prefixes, we go through them one by one.
        if isinstance(prefix, str):
            prefixes = (prefix, )
        else:
            prefixes = prefix

        for key_prefix in prefixes:
            kwargs["Prefix"] = key_prefix

            for page in paginator.paginate(**kwargs):
                try:
                    contents = page["Contents"]
                except KeyError:
                    break

                for obj in contents:
                    key = obj["Key"]
                    if key.endswith(suffix):
                        yield obj


    def get_matching_s3_keys(self, s3client, bucket, prefix="", suffix=""):
        """
        Generate the keys in an S3 bucket.

        :param bucket: Name of the S3 bucket.
        :param prefix: Only fetch keys that start with this prefix (optional).
        :param suffix: Only fetch keys that end with this suffix (optional).
        """
        for obj in self.get_matching_s3_objects(s3client, bucket, prefix, suffix):
            yield obj["Key"]
