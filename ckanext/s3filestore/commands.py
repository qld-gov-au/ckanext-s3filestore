import sys

from ckantoolkit import config
import ckantoolkit as toolkit
import ckanext.s3filestore.uploader



class TestConnection(toolkit.CkanCommand):
    '''CKAN S3 FileStore utilities

    Usage:

        paster s3 check-config

            Checks if the configuration entered in the ini file is correct

    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__
    min_args = 1

    def command(self):
        self._load_config()
        if not self.args:
            print(self.usage)
        elif self.args[0] == 'check-config':
            self.check_config()

    def check_config(self):
        exit = False
        required_keys = ('ckanext.s3filestore.aws_bucket_name',)
        if not config.get('ckanext.s3filestore.aws_use_ami_role'):
            required_keys += ('ckanext.s3filestore.aws_access_key_id',
                              'ckanext.s3filestore.aws_secret_access_key')
        for key in required_keys:
            if not config.get(key):
                print
                'You must set the "{0}" option in your ini file'.format(
                    key)
                exit = True
        if exit:
            sys.exit(1)

        print('All configuration options defined')
        bucket_name = config.get('ckanext.s3filestore.aws_bucket_name')

        try:
            ckanext.s3filestore.uploader.BaseS3Uploader().get_s3_bucket(bucket_name)
        except ckanext.S3FileStoreException as ex:
            print('An error was found while finding or creating the bucket:')
            print(str(ex))
            sys.exit(1)


        print('Configuration OK!')
