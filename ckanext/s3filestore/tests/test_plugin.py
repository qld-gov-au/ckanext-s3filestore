# encoding: utf-8

import mock

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

    def test_package_after_update(self):
        '''S3 object visibility is updated to match package'''
        pkg_dict = {'id': 'test-package',
                    'resources': [{'id': 'test-resource'}]}
        with mock.patch('ckanext.s3filestore.plugin.toolkit') as mock_toolkit:
            mock_toolkit.get_action.return_value = lambda **kwargs: pkg_dict
            mock_uploader = mock.MagicMock()
            self.plugin.get_resource_uploader = mock.MagicMock()
            self.plugin.get_resource_uploader.return_value = mock_uploader
            mock_uploader.update_visibility = mock.MagicMock()

            self.plugin.after_update({}, pkg_dict)
            mock_uploader.update_visibility.assert_called_once_with(
                'test-resource', 'public-read')
