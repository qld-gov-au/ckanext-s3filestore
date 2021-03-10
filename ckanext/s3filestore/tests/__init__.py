# encoding: utf-8

from ckantoolkit import config
import boto3

# moto AWS mock is started externally on port 5000
endpoint_url = config.get('ckanext.s3filestore.host_name', 'http://localhost:5000')
botoSession = boto3.Session(region_name='ap-southeast-2', aws_access_key_id='a', aws_secret_access_key='b')
s3 = botoSession.client('s3', endpoint_url=endpoint_url)
BUCKET_NAME = 'my-bucket'


def setup_package(self):
    # We need to create the bucket since this is all in Moto's 'virtual' AWS account
    s3.create_bucket(Bucket=BUCKET_NAME)
