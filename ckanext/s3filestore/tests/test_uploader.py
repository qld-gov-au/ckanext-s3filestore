# encoding: utf-8

import datetime
import io
import os
import six

import mock
from nose.tools import (assert_equal,
                        assert_true,
                        assert_false,
                        assert_in,
                        assert_is_none,
                        assert_raises,
                        with_setup)

from botocore.exceptions import ClientError

from werkzeug.datastructures import FileStorage as FlaskFileStorage

from ckan.plugins import toolkit
from ckan.plugins.toolkit import config
from ckan.tests import helpers
import ckan.tests.factories as factories

from ckanext.s3filestore.uploader import (
    BaseS3Uploader, S3Uploader, S3ResourceUploader, _is_presigned_url)

from . import _get_status_code


DIRECT_DOWNLOAD_URL_FORMAT = '/dataset/{0}/resource/{1}/orig_download/{2}'


def _setup_function(self):
    helpers.reset_db()
    self.app = helpers._get_test_app()
    self.sysadmin = factories.Sysadmin(apikey="my-test-key")
    self.organisation = factories.Organization(name='my-organisation')
    self.endpoint_url = config.get('ckanext.s3filestore.host_name')
    uploader = BaseS3Uploader()
    self.s3 = uploader.get_s3_client()
    # ensure the bucket exists, create if needed
    self.bucket_name = config.get('ckanext.s3filestore.aws_bucket_name')
    uploader.get_s3_bucket(self.bucket_name)


def _resource_setup_function(self):
    _setup_function(self)


def _get_object_key(resource):
    ''' Determine the S3 object key for the specified resource.
    '''
    return '{0}/resources/{1}/data.csv'.format(
        config.get('ckanext.s3filestore.aws_storage_path'),
        resource['id'])


def _assert_public(resource, url, uploader):
    assert_false(_is_presigned_url(url), "Expected {} [{}] to use public URL but was {}".format(
        resource, uploader.get_path(resource['id']), url))


def _assert_private(resource, url, uploader):
    assert_true(_is_presigned_url(url), "Expected {} [{}] to use private URL but was {}".format(
        resource, uploader.get_path(resource['id']), url))


@with_setup(_setup_function)
class TestS3Uploader():

    def test_get_bucket(self):
        '''S3Uploader retrieves bucket as expected'''
        uploader = S3Uploader('')
        assert_true(uploader.get_s3_bucket(self.bucket_name))

    def test_clean_dict(self):
        '''S3Uploader retrieves bucket as expected'''
        uploader = S3Uploader('')
        date_dict = {'key': datetime.datetime(1970, 1, 2, 3, 4, 5, 6)}
        clean_dict = uploader.as_clean_dict(date_dict)
        assert_equal(clean_dict['key'], '1970-01-02T03:04:05.000006')

    def test_uploader_storage_path(self):
        '''S3Uploader get_storage_path returns as expected'''
        returned_path = S3Uploader.get_storage_path('myfiles')
        assert_equal(returned_path, 'my-path/storage/uploads/myfiles')

    def test_group_image_upload(self):
        '''Test a group image file upload'''

        file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
        file_name = 'somename.png'

        img_uploader = FlaskFileStorage(filename=file_name, stream=io.open(file_path, 'rb'), content_type='image/png')

        with mock.patch('ckanext.s3filestore.uploader.datetime') as mock_date:
            mock_date.datetime.utcnow.return_value = \
                datetime.datetime(2001, 1, 29)
            context = {'user': self.sysadmin['name']}
            helpers.call_action('group_create', context=context,
                                name="my-group",
                                image_upload=img_uploader,
                                image_url=file_name,
                                save='save')

        key = '{0}/storage/uploads/group/2001-01-29-000000{1}' \
            .format(config.get('ckanext.s3filestore.aws_storage_path'), file_name)

        # check whether the object exists in S3
        # will throw exception if not existing
        self.s3.head_object(Bucket=self.bucket_name, Key=key)

        # requesting image redirects to s3
        # attempt redirect to linked url
        image_file_url = '/uploads/group/2001-01-29-000000{0}'.format(file_name)
        status_code, location = self._get_expecting_redirect(self.app, image_file_url)
        assert_equal(location.split('?')[0],
                     '{0}/my-bucket/my-path/storage/uploads/group/2001-01-29-000000{1}'
                     .format(self.endpoint_url, file_name))

    def test_group_image_upload_then_clear(self):
        '''Test that clearing an upload removes the S3 key'''

        file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
        file_name = "somename.png"

        img_uploader = FlaskFileStorage(filename=file_name, stream=io.open(file_path, 'rb'), content_type='image/png')

        with mock.patch('ckanext.s3filestore.uploader.datetime') as mock_date:
            mock_date.datetime.utcnow.return_value = \
                datetime.datetime(2001, 1, 29)
            context = {'user': self.sysadmin['name']}
            helpers.call_action('group_create', context=context,
                                name="my-group",
                                image_upload=img_uploader,
                                image_url=file_name)

        key = '{0}/storage/uploads/group/2001-01-29-000000{1}' \
            .format(config.get('ckanext.s3filestore.aws_storage_path'), file_name)

        # check whether the object exists in S3
        # will throw exception if not existing
        self.s3.head_object(Bucket=self.bucket_name, Key=key)

        # clear upload
        helpers.call_action('group_update', context=context,
                            id='my-group', name='my-group',
                            image_url="http://asdf", clear_upload=True)

        # key shouldn't exist
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=key)
            # broken by https://github.com/ckan/ckan/commit/48afb9da4d
            # assert_false(True, "file '{}' should not exist".format(key))
        except ClientError:
            # passed
            assert_true(True, "passed")

    if toolkit.check_ckan_version('2.9'):

        def _get_expecting_redirect(self, app, url):
            response = app.get(url, follow_redirects=False)
            status_code = _get_status_code(response)
            assert_in(status_code, [301, 302],
                      "%s resulted in %s instead of a redirect" % (url, status_code))
            return status_code, response.location

    else:

        def _get_expecting_redirect(self, app, url):
            response = app.get(url)
            status_code = _get_status_code(response)
            assert_in(status_code, [301, 302],
                      "%s resulted in %s instead of a redirect" % (url, status_code))
            return status_code, response.headers['Location']


@with_setup(_resource_setup_function)
class TestS3ResourceUploader():

    def _test_dataset(self, private=False, title='Test Dataset', author='test'):
        ''' Creates a test dataset.
        '''
        return factories.Dataset(
            name="my-dataset",
            private=private,
            title=title,
            author=author,
            owner_org=self.organisation['id'])

    def _upload_test_resource(self, dataset=None):
        ''' Creates a test resource in the specified dataset
        by uploading a file.
        '''
        if not dataset:
            dataset = self._test_dataset()
        file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
        return helpers.call_action(
            'resource_create',
            package_id=dataset['id'],
            upload=FlaskFileStorage(io.open(file_path, 'rb')),
            url='data.csv')

    def test_resource_upload(self):
        '''Test a basic resource file upload'''
        file_path = os.path.join(os.path.dirname(__file__), 'data.csv')
        resource = self._upload_test_resource()

        key = _get_object_key(resource)

        # check whether the object exists in S3
        # will throw exception if not existing
        self.s3.head_object(Bucket=self.bucket_name, Key=key)

        # test the file contains what's expected
        obj = self.s3.get_object(Bucket=self.bucket_name, Key=key)
        data = obj['Body'].read()
        assert_equal(data, io.open(file_path, 'rb').read())

    def test_package_update(self):
        ''' Test a typical package_update API call.
        '''
        dataset = self._test_dataset()
        test_resource = self._upload_test_resource(dataset)
        pkg_dict = helpers.call_action('package_show', id=dataset['id'])
        # package_update calls won't necessarily provide package ID
        # on each resource
        for resource in pkg_dict['resources']:
            resource['description'] = 'updated description'
            del resource['package_id']

        helpers.call_action(
            'package_update',
            context={'user': self.sysadmin['name']},
            **pkg_dict
        )
        assert helpers.call_action(
            'resource_show', id=test_resource['id']
        )['description'] == 'updated description'

    def test_uploader_get_path(self):
        '''Uploader get_path returns as expected'''
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset['id'])

        uploader = S3ResourceUploader(resource)
        returned_path = uploader.get_path(resource['id'], 'myfile.txt')
        assert_equal(returned_path,
                     'my-path/resources/{0}/myfile.txt'.format(resource['id']))

    def test_is_presigned_url(self):
        ''' Tests that presigned URLs are correctly recognised.'''
        assert_true(_is_presigned_url('https://example.s3.amazonaws.com/resources/foo?AWSAccessKeyId=SomeKey&Expires=9999999999Signature=hb7%2F%2Bz1H%2B8wdEy0pCsX7bZG%2BuPU%3D'))
        assert_false(_is_presigned_url('https://example.s3.amazonaws.com/resources/foo'))

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    def test_resource_url_unsigned_for_public_dataset(self):
        ''' Tests that resources in public datasets give unsigned URLs.
        '''
        resource = self._upload_test_resource()
        key = _get_object_key(resource)
        uploader = S3ResourceUploader(resource)

        url = uploader.get_signed_url_to_key(key)

        _assert_public(resource, url, uploader)
        assert_in('ETag=', url)

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    def test_resource_url_signed_for_private_dataset(self):
        ''' Tests that resources in private datasets generate presigned URLs.
        '''
        dataset = self._test_dataset(private=True)
        resource = self._upload_test_resource(dataset)
        key = _get_object_key(resource)
        uploader = S3ResourceUploader(resource)

        url = uploader.get_signed_url_to_key(key)

        _assert_private(resource, url, uploader)

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    def test_making_dataset_private_updates_object_visibility(self):
        ''' Tests that a dataset that changes from public to private
        will change from unsigned to signed URLs.
        '''
        dataset = self._test_dataset()
        resource = self._upload_test_resource(dataset)
        key = _get_object_key(resource)
        uploader = S3ResourceUploader(resource)

        url = uploader.get_signed_url_to_key(key)
        _assert_public(resource, url, uploader)
        assert_in('ETag=', url)

        helpers.call_action('package_patch',
                            context={'user': self.sysadmin['name']},
                            id=dataset['id'],
                            private=True)

        url = uploader.get_signed_url_to_key(key)
        _assert_private(resource, url, uploader)

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    def test_making_dataset_public_updates_object_visibility(self):
        ''' Tests that a dataset that changes from private to public
        will change from signed to unsigned URLs.
        '''
        dataset = self._test_dataset(private=True)
        resource = self._upload_test_resource(dataset)
        key = _get_object_key(resource)
        uploader = S3ResourceUploader(resource)

        url = uploader.get_signed_url_to_key(key)
        _assert_private(resource, url, uploader)

        helpers.call_action('package_patch',
                            context={'user': self.sysadmin['name']},
                            id=dataset['id'],
                            private=False)

        url = uploader.get_signed_url_to_key(key)
        _assert_public(resource, url, uploader)
        assert_in('ETag=', url)

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    def test_non_current_objects_are_private(self):
        ''' Tests that prior versions of a resource, with different
        filenames, are made private by default.
        '''
        dataset = self._test_dataset(private=False)
        resource = self._upload_test_resource(dataset)
        file_path = os.path.join(os.path.dirname(__file__), 'data.txt')
        resource = helpers.call_action(
            'resource_patch',
            id=resource['id'],
            upload=FlaskFileStorage(io.open(file_path, 'rb')),
            url='data.txt')

        uploader = S3ResourceUploader(resource)

        key = uploader.get_path(resource['id'])
        url = uploader.get_signed_url_to_key(key)
        assert_false(_is_presigned_url(url), "Expected [{}] to use public URL but was {}".format(key, url))

        key = uploader.get_path(resource['id'], 'data.csv')
        url = uploader.get_signed_url_to_key(key)
        assert_true(_is_presigned_url(url), "Expected [{}] to use private URL but was {}".format(key, url))

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    @helpers.change_config('ckanext.s3filestore.non_current_acl', 'public-read')
    def test_non_current_objects_match_acl(self):
        ''' Tests that prior versions of a resource, with different
        filenames, are updated to match the configured ACL.
        '''
        dataset = self._test_dataset(private=False)
        resource = self._upload_test_resource(dataset)
        file_path = os.path.join(os.path.dirname(__file__), 'data.txt')
        resource = helpers.call_action(
            'resource_patch',
            id=resource['id'],
            upload=FlaskFileStorage(io.open(file_path, 'rb')),
            url='data.txt')

        uploader = S3ResourceUploader(resource)

        key = uploader.get_path(resource['id'])
        url = uploader.get_signed_url_to_key(key)
        assert_false(_is_presigned_url(url), "Expected [{}] to use public URL but was {}".format(key, url))

        key = uploader.get_path(resource['id'], 'data.csv')
        url = uploader.get_signed_url_to_key(key)
        assert_false(_is_presigned_url(url), "Expected [{}] to use public URL but was {}".format(key, url))

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    @helpers.change_config('ckanext.s3filestore.non_current_acl', 'auto')
    def test_non_current_objects_match_auto_acl(self):
        ''' Tests that prior versions of a resource, with different
        filenames, are updated to match the configured ACL.
        '''
        dataset = self._test_dataset(private=False)
        resource = self._upload_test_resource(dataset)
        file_path = os.path.join(os.path.dirname(__file__), 'data.txt')
        resource = helpers.call_action(
            'resource_patch',
            id=resource['id'],
            upload=FlaskFileStorage(io.open(file_path, 'rb')),
            url='data.txt')

        uploader = S3ResourceUploader(resource)

        key = uploader.get_path(resource['id'])
        url = uploader.get_signed_url_to_key(key)
        assert_false(_is_presigned_url(url), "Expected [{}] to use public URL but was {}".format(key, url))

        key = uploader.get_path(resource['id'], 'data.csv')
        url = uploader.get_signed_url_to_key(key)
        assert_false(_is_presigned_url(url), "Expected [{}] to use public URL but was {}".format(key, url))

        helpers.call_action(
            'package_patch',
            id=dataset['id'],
            private=True
        )
        url = uploader.get_signed_url_to_key(key)
        assert_true(_is_presigned_url(url), "Expected [{}] to use private URL but was {}".format(key, url))

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    @helpers.change_config('ckanext.s3filestore.delete_non_current_days', '0')
    def test_delete_non_current_objects_after_expiry(self):
        ''' Tests that prior versions of a resource, with different
        filenames, are deleted after the configured expiry.
        '''
        dataset = self._test_dataset(private=False)
        resource = self._upload_test_resource(dataset)
        file_path = os.path.join(os.path.dirname(__file__), 'data.txt')
        resource = helpers.call_action(
            'resource_patch',
            id=resource['id'],
            upload=FlaskFileStorage(io.open(file_path, 'rb')),
            url='data.txt')

        uploader = S3ResourceUploader(resource)

        key = uploader.get_path(resource['id'])
        assert uploader.get_signed_url_to_key(key) is not None

        key = uploader.get_path(resource['id'], 'data.csv')
        with assert_raises(toolkit.ObjectNotFound):
            assert uploader.get_signed_url_to_key(key) is not None

    @helpers.change_config('ckanext.s3filestore.acl', 'auto')
    @helpers.change_config('ckanext.s3filestore.delete_non_current_days', '2')
    def test_do_not_delete_non_current_objects_before_expiry(self):
        ''' Tests that prior versions of a resource, with different
        filenames, are deleted after the configured expiry.
        '''
        dataset = self._test_dataset(private=False)
        resource = self._upload_test_resource(dataset)
        file_path = os.path.join(os.path.dirname(__file__), 'data.txt')
        resource = helpers.call_action(
            'resource_patch',
            id=resource['id'],
            upload=FlaskFileStorage(io.open(file_path, 'rb')),
            url='data.txt')

        uploader = S3ResourceUploader(resource)

        key = uploader.get_path(resource['id'])
        url = uploader.get_signed_url_to_key(key)

        key = uploader.get_path(resource['id'], 'data.csv')
        url = uploader.get_signed_url_to_key(key)
        assert_true(_is_presigned_url(url), "Expected [{}] to use private URL but was {}".format(key, url))

    def test_assembling_object_metadata_headers(self):
        ''' Tests that text fields from the package are passed to S3.
        '''
        dataset = self._test_dataset()
        resource = self._upload_test_resource(dataset)
        uploader = S3ResourceUploader(resource)

        object_metadata = uploader._get_resource_metadata()
        assert_equal(object_metadata['package_id'], dataset['id'])
        assert_false('notes' in object_metadata['package_id'])

    def test_encoding_object_metadata_headers(self):
        ''' Tests that text fields from the package are passed to S3.
        '''
        dataset = self._test_dataset(title=u'Test Dataset—with em dash', author=u'擬製 暗影')
        resource = self._upload_test_resource(dataset)
        uploader = S3ResourceUploader(resource)

        object_metadata = uploader._get_resource_metadata()
        assert_equal(object_metadata['package_title'], 'Test Dataset&#8212;with em dash')
        assert_equal(object_metadata['package_author'], '&#25836;&#35069; &#26263;&#24433;')

    def test_ignoring_non_uploads(self):
        ''' Tests that resources not containing an upload are ignored.
        '''
        dataset = self._test_dataset()
        resources = [factories.Resource(package_id=dataset['id'], url='https://example.com'),
                     helpers.call_action(
                         'resource_create',
                         package_id=dataset['id'],
                         upload=FlaskFileStorage(six.BytesIO(b'')),
                         url='https://example.com')
                     ]
        for resource in resources:
            uploader = S3ResourceUploader(resource)
            assert_equal(resource['url'], 'https://example.com')
            assert_is_none(getattr(uploader, 'filename', None))
            assert_is_none(getattr(uploader, 'filesize', None))
            with mock.patch('ckanext.s3filestore.uploader.S3ResourceUploader.update_visibility') as mock_update_visibility,\
                    mock.patch('ckanext.s3filestore.uploader.S3ResourceUploader.upload_to_key') as mock_upload_to_key:
                uploader.upload(resource['id'])
                mock_upload_to_key.assert_not_called()
                mock_update_visibility.assert_called_once_with(resource['id'])

    if toolkit.check_ckan_version(max_version='2.8.99'):

        def test_resource_upload_then_clear(self):
            '''Test that clearing an upload removes the S3 key'''

            dataset = self._test_dataset()
            resource = self._upload_test_resource(dataset)
            key = _get_object_key(resource)

            # check whether the object exists in S3
            # will throw exception if not existing
            self.s3.head_object(Bucket=self.bucket_name, Key=key)

            # clear upload
            url = toolkit.url_for(controller='package', action='resource_edit',
                                  id=dataset['id'], resource_id=resource['id'])
            env = {'REMOTE_USER': self.sysadmin['name'].encode('ascii')}
            self.app.post(
                url,
                {'clear_upload': True,
                 'url': 'http://asdf', 'save': 'save'},
                extra_environ=env)

            # key shouldn't exist
            try:
                self.s3.head_object(Bucket=self.bucket_name, Key=key)
                assert_false(True, "file should not exist")
            except ClientError:
                # passed
                assert_true(True, "passed")
