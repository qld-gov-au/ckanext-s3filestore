'''
This script copies all resource files from a local FileStore directory
to a remote S3 bucket.

**It will not work for group images**

It requires SQLalchemy and Boto.

Please update the configuration details, all keys are mandatory except
AWS_STORAGE_PATH.

'''

import os
from sqlalchemy import create_engine
from sqlalchemy.sql import text
import boto3

import configparser

# Configuration

CONFIG_FILE = '/etc/ckan/default/production.ini'

config = configparser.ConfigParser(strict=False)
config.read(CONFIG_FILE)
main_config = config['app:main']

BASE_PATH = main_config.get('ckan.storage_path', '/var/lib/ckan/default/resources')
SQLALCHEMY_URL = main_config.get('sqlalchemy.url', 'postgresql://user:pass@localhost/db')
if main_config.get('ckanext.s3filestore.aws_use_ami_role', False):
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
else:
    AWS_ACCESS_KEY_ID = main_config.get('ckanext.s3filestore.aws_access_key_id', 'AKIxxxxxx')
    AWS_SECRET_ACCESS_KEY = main_config.get('ckanext.s3filestore.aws_secret_access_key', '+NGxxxxxx')
AWS_BUCKET_NAME = main_config.get('ckanext.s3filestore.aws_bucket_name', 'my-bucket')
AWS_STORAGE_PATH = ''
AWS_S3_ACL = main_config.get('ckanext.s3filestore.acl', 'public-read')


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
    if AWS_STORAGE_PATH:
        key = AWS_STORAGE_PATH + '/' + key

    s3_connection.Object(AWS_BUCKET_NAME, key).put(Body=open(resource_ids_and_paths[resource_id]), ACL=AWS_S3_ACL)
    uploaded_resources.append(resource_id)
    print('Uploaded resource {0} ({1}) to S3'.format(resource_id, file_name))

print('Done, uploaded {0} resources to S3'.format(len(uploaded_resources)))
