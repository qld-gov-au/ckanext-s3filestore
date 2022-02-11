# encoding: utf-8

import sys

from ckan.plugins import toolkit

from cli_commands import S3FilestoreCommands


class TestConnection(toolkit.CkanCommand, S3FilestoreCommands):
    '''CKAN S3 FileStore utilities

    Usage:

        s3 update-all-visibility

            Updates the visibility of all existing S3 objects to match current config

        s3 check-config

            Checks if the configuration entered in the ini file is correct

        s3 upload [pairtree|<id>|all]

            Uploads existing files from disk to S3.

            If 'all' is specified, this will scan for files on disk and
            attempt to upload each one to the matching resource.

            If 'pairtree' is specified, this attempts to upload items from
            the legacy 'Pairtree' storage. NB Selecting 'all' will not
            attempt to load from Pairtree.

            Otherwise, if a UUID is specified, this will attempt to
            upload the matching resource or all resources in the
            matching package.

    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__
    min_args = 1

    def command(self):
        if not self.args:
            print(self.usage)
            sys.exit(1)
        self._load_config()
        if self.args[0] == 'check-config':
            self.check_config()
        elif self.args[0] == 'update-all-visibility':
            self.update_all_visibility()
        elif self.args[0] == 'upload':
            if len(self.args) < 2 or self.args[1] == 'all':
                self.upload_all()
            elif self.args[1] == 'pairtree':
                self.upload_pairtree()
            else:
                self.upload_single(self.args[1])
        else:
            self.parser.error('Unrecognized command')
