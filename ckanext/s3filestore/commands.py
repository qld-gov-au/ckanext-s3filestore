from __future__ import print_function

import boto3
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.sql import text
import ckantoolkit as toolkit
from ckantoolkit import config
import ckanext.s3filestore.uploader


class TestConnection(toolkit.CkanCommand):
    '''CKAN S3 FileStore utilities

    Usage:

        s3 check-config

            Checks if the configuration entered in the ini file is correct

        s3 upload [all]

            Uploads existing files from disk to S3.

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
        elif self.args[0] == 'upload':
            if len(self.args) < 2 or args[1] == 'all':
                self.upload_all()
        else:
            self.parser.error('Unrecognized command')

    def check_config(self):
        exit = False
        required_keys = ('ckanext.s3filestore.aws_bucket_name',
                         'ckanext.s3filestore.region_name',
                         'ckanext.s3filestore.signature_version')
        if not config.get('ckanext.s3filestore.aws_use_ami_role'):
            required_keys += ('ckanext.s3filestore.aws_access_key_id',
                              'ckanext.s3filestore.aws_secret_access_key')
        for key in required_keys:
            if not config.get(key):
                print('You must set the "{0}" option in your ini file'.format(key))
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

    def upload_all(self):
        BASE_PATH = config.get('ckan.storage_path', '/var/lib/ckan/default/resources')
        SQLALCHEMY_URL = config.get('sqlalchemy.url', 'postgresql://user:pass@localhost/db')
        if config.get('ckanext.s3filestore.aws_use_ami_role', False):
            AWS_ACCESS_KEY_ID = None
            AWS_SECRET_ACCESS_KEY = None
        else:
            AWS_ACCESS_KEY_ID = config.get('ckanext.s3filestore.aws_access_key_id')
            AWS_SECRET_ACCESS_KEY = config.get('ckanext.s3filestore.aws_secret_access_key')
        AWS_BUCKET_NAME = config.get('ckanext.s3filestore.aws_bucket_name')
        AWS_S3_ACL = config.get('ckanext.s3filestore.acl', 'public-read')
        resource_ids_and_paths = {}

        for root, dirs, files in os.walk(BASE_PATH):
            if files:
                resource_id = root.split('/')[-2] + root.split('/')[-1] + files[0]
                resource_ids_and_paths[resource_id] = os.path.join(root, files[0])

        print('Found {0} resource files in the file system'.format(
            len(resource_ids_and_paths.keys())))

        engine = create_engine(SQLALCHEMY_URL)
        connection = engine.connect()

        resource_ids_and_names = {}

        try:
            for resource_id, file_path in resource_ids_and_paths.iteritems():
                resource = connection.execute(text('''
                    SELECT id, url, url_type
                    FROM resource
                    WHERE id = :id
                '''), id=resource_id)
                if resource.rowcount:
                    _id, url, _type = resource.first()
                    if _type == 'upload' and url:
                        file_name = url.split('/')[-1] if '/' in url else url
                        resource_ids_and_names[_id] = file_name.lower()
        finally:
            connection.close()
            engine.dispose()

        print('{0} resources matched on the database'.format(
            len(resource_ids_and_names.keys())))

        # todo: move to plugin initi so we don't need to reinit secrets
        s3_connection = boto3.resource('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
        bucket = s3_connection.Bucket(AWS_BUCKET_NAME)

        uploaded_resources = []
        for resource_id, file_name in resource_ids_and_names.iteritems():
            key = 'resources/{resource_id}/{file_name}'.format(
                resource_id=resource_id, file_name=file_name)

            s3_connection.Object(AWS_BUCKET_NAME, key).put(Body=open(resource_ids_and_paths[resource_id]), ACL=AWS_S3_ACL)
            uploaded_resources.append(resource_id)
            print('Uploaded resource {0} ({1}) to S3'.format(resource_id, file_name))

        print('Done, uploaded {0} resources to S3'.format(len(uploaded_resources)))
