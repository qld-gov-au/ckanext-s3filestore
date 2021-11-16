# encoding: utf-8

import mock

from ckanext.s3filestore.plugin import S3FileStorePlugin


class TestS3Plugin():

    def test_update_config(self):
        '''Plugin sets template directories'''
        plugin = S3FileStorePlugin()
        config = {}
        with mock.patch('ckanext.s3filestore.plugin.toolkit') as mock_toolkit:
            plugin.update_config(config)
            mock_toolkit.add_template_directory.assert_has_calls(
                [mock.call(config, 'templates'),
                 mock.call(config, 'theme/templates')]
            )
