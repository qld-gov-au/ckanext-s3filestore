# encoding: utf-8

import mock
from parameterized import parameterized

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
        '''S3 object visibility is updated to match package'''
        pkg_dict = {'id': 'test-package',
                    'resources': [{'id': 'test-resource'}]}
        if is_private is not None:
            pkg_dict['private'] = is_private
        with mock.patch('ckanext.s3filestore.plugin.toolkit') as mock_toolkit:
            self.plugin.after_update({}, pkg_dict)
            mock_toolkit.enqueue_job.assert_called_once
