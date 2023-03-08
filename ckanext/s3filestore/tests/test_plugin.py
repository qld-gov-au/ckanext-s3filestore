# encoding: utf-8

import mock
from parameterized import parameterized

import ckantoolkit as toolkit

from ckanext.s3filestore import tasks
from ckanext.s3filestore.plugin import S3FileStorePlugin


class TestS3Plugin():

    def setup(self):
        self.plugin = S3FileStorePlugin()

    def test_update_config(self):
        '''Plugin sets template directories'''
        config = {}
        with mock.patch('ckanext.s3filestore.plugin.toolkit') as mock_toolkit:
            self.plugin.update_config(config)
            mock_toolkit.add_template_directory.assert_has_calls(
                [mock.call(config, 'templates'),
                 mock.call(config, 'theme/templates')]
            )

    @parameterized.expand([
        (None, 'public-read'),
        (True, 'private'),
        (False, 'public-read')
    ])
    def test_package_after_update(self, is_private, expected_acl):
        ''' S3 object visibility is updated to match package'''
        pkg_dict = {'id': 'test-package',
                    'resources': [{'id': 'test-resource'}]}
        if is_private is not None:
            pkg_dict['private'] = is_private
        with mock.patch('ckanext.s3filestore.plugin.toolkit') as mock_toolkit:
            mock_toolkit.get_action.return_value = lambda **kwargs: [] if 'limit' in kwargs['data_dict'] else pkg_dict
            mock_uploader = mock.MagicMock()
            with mock.patch('ckanext.s3filestore.plugin.get_resource_uploader') as mock_get_uploader:
                mock_get_uploader.return_value = mock_uploader
                mock_uploader.update_visibility = mock.MagicMock()

                self.plugin.after_update({}, pkg_dict)
                mock_uploader.update_visibility.assert_called_once_with(
                    'test-resource', target_acl=expected_acl)

    def test_enqueueing_visibility_update(self):
        ''' Asynchronous job is created to update object visibility.
        '''
        # ensure that we don't trigger errors
        self.plugin.enqueue_resource_visibility_update_job('private', 'abcde')

        # check that the args were actually passed in
        with mock.patch('rq.Queue.enqueue_call') as enqueue_call:
            self.plugin.enqueue_resource_visibility_update_job('private', 'abcde')
            if toolkit.check_ckan_version(max_version='2.7.99'):
                enqueue_call.assert_called_once_with(
                    func=tasks.s3_afterUpdatePackage,
                    args=[],
                    kwargs={'visibility_level': 'private', 'pkg_id': 'abcde'}
                )
            else:
                if toolkit.check_ckan_version('2.10'):
                    timeout = toolkit.config.get('ckan.jobs.timeout')
                else:
                    from ckan.lib.jobs import DEFAULT_JOB_TIMEOUT
                    timeout = DEFAULT_JOB_TIMEOUT

                if toolkit.check_ckan_version('2.9'):
                    enqueue_call.assert_called_once_with(
                        func=tasks.s3_afterUpdatePackage,
                        args=[],
                        kwargs={'visibility_level': 'private', 'pkg_id': 'abcde'},
                        timeout=timeout,
                        ttl=86400,
                        failure_ttl=86400
                    )
                else:
                    enqueue_call.assert_called_once_with(
                        func=tasks.s3_afterUpdatePackage,
                        args=[],
                        kwargs={'visibility_level': 'private', 'pkg_id': 'abcde'},
                        timeout=timeout,
                        ttl=86400
                    )
