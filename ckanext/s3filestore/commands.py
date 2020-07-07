import sys
import boto3
import botocore
from ckantoolkit import config
import ckantoolkit as toolkit


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
        public_key = config.get('ckanext.s3filestore.aws_access_key_id')
        secret_key = config.get('ckanext.s3filestore.aws_secret_access_key')
        region_name = config.get('ckanext.s3filestore.region_name')

        S3_conn = boto3.client('s3', aws_access_key_id=public_key, aws_secret_access_key=secret_key)

        # Check if bucket exists
        try:
            S3_conn.meta.client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = e.response['Error']['Code']
            if error_code == '404':
                try:
                    S3_conn.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={
    'LocationConstraint': region_name})
                except boto3.exception.StandardError as ex:
                    print('An error was found while creating the bucket:')
                    print(str(ex))
                    sys.exit(1)

        print('Configuration OK!')
