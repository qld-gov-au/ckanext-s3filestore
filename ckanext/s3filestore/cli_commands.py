# encoding: utf-8

from botocore.exceptions import ClientError
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.sql import text
from ckan.lib import munge
from ckan.plugins.toolkit import config, get_action, ValidationError
from ckanext.s3filestore import uploader
from ckanext.s3filestore.uploader import get_s3_session, S3FileStoreException


class DBConnection:

    def __init__(self, config):
        self.SQLALCHEMY_URL = config.get('sqlalchemy.url', 'postgresql://user:pass@localhost/db')

    def __enter__(self):
        self.engine = create_engine(self.SQLALCHEMY_URL)
        self.connection = self.engine.connect()
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.close()
        self.engine.dispose()


class S3FilestoreCommands():

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
            uploader.BaseS3Uploader().get_s3_bucket(bucket_name)
        except S3FileStoreException as ex:
            print('An error was found while finding or creating the bucket:')
            print(str(ex))
            sys.exit(1)

        print('Configuration OK!')

    def upload_all(self):
        BASE_PATH = config.get('ckan.storage_path', '/var/lib/ckan/default/resources')
        resource_ids_and_paths = {}

        for root, dirs, files in os.walk(BASE_PATH):
            if files:
                resource_id = root.split('/')[-2] + root.split('/')[-1] + files[0]
                resource_ids_and_paths[resource_id] = os.path.join(root, files[0])

        print('Found {0} resource files in the file system'.format(
            len(resource_ids_and_paths.keys())))

        with DBConnection(config) as connection:
            resource_ids_and_names = {}

            for resource_id, file_path in resource_ids_and_paths.iteritems():
                resource = connection.execute(text('''
                    SELECT id, url
                    FROM resource
                    WHERE id = :id
                    AND state = 'active'
                    AND url IS NOT NULL
                    AND url <> ''
                    AND url_type = 'upload'
                '''), id=resource_id)
                if resource.rowcount:
                    _id, url = resource.first()
                    file_name = url.split('/')[-1] if '/' in url else url
                    resource_ids_and_names[_id] = file_name.lower()
                else:
                    print("{} is an orphan; no resource points to it".format(file_path))

        print('{0} resources matched on the database'.format(
            len(resource_ids_and_names.keys())))

        _upload_files_to_s3(resource_ids_and_names, resource_ids_and_paths)

    def upload_single(self, id):
        with DBConnection(config) as connection:
            resource_ids_and_names = {}
            for resource in connection.execute(text('''
                    SELECT id, url
                    FROM resource
                    WHERE (id = :id or package_id = :id)
                    AND state = 'active'
                    AND url IS NOT NULL
                    AND url <> ''
                    AND url_type = 'upload'
            '''), id=id):
                _id, url = resource
                file_name = url.split('/')[-1] if '/' in url else url
                resource_ids_and_names[_id] = file_name.lower()

        print('{0} resources matched on the database'.format(
            len(resource_ids_and_names.keys())))

        BASE_PATH = os.path.join(config.get('ckan.storage_path', '/var/lib/ckan/default/'), 'resources')
        resource_ids_and_paths = {}
        for resource_id in resource_ids_and_names.keys():
            path = '{}/{}/{}/{}'.format(BASE_PATH, resource_id[0:3], resource_id[3:6], resource_id[6:])
            if os.path.isfile(path):
                resource_ids_and_paths[resource_id] = path
            else:
                print("[{}] not found on the file system".format(path))

        print('Found {0} resource files in the file system'.format(
            len(resource_ids_and_paths.keys())))

        _upload_files_to_s3(resource_ids_and_names, resource_ids_and_paths)

    def upload_pairtree(self):
        def _to_pairtree_path(path):
            return os.path.join(*[path[i:i + 2] for i in range(0, len(path), 2)])

        BASE_PATH = os.path.join(
            config.get('ckan.storage_path', config.get('ofs.storage_dir', '/var/lib/ckan/default')),
            'pairtree_root',
            _to_pairtree_path(config.get('ckan.storage.key_prefix', 'ckan-file')),
            'obj'
        )
        print("Uploading pairtree files from {}".format(BASE_PATH))
        resource_paths = []
        resource_ids_and_paths = {}

        # identify files on disk
        for root, dirs, files in os.walk(BASE_PATH):
            if files:
                path = root.split('/')[-1]
                resource_paths.append(path + '/' + files[0])

        print('Found {0} resource files in the file system'.format(
            len(resource_paths)))

        # match files to resource URLs
        with DBConnection(config) as connection:
            resource_ids_and_names = {}

            SITE_URL = config.get('ckan.site_url')
            BASE_URL = SITE_URL + '/storage/f/'
            for file_path in resource_paths:
                pairtree_url = BASE_URL + file_path.replace(':', '%3A')
                resource = connection.execute(text('''
                    SELECT id, url
                    FROM resource
                    WHERE url = :url
                    AND state = 'active'
                    AND url IS NOT NULL
                    AND url <> ''
                '''), url=pairtree_url)
                if resource.rowcount:
                    _id, url = resource.first()
                    if url:
                        file_name = url.split('/')[-1] if '/' in url else url
                        resource_ids_and_names[_id] = file_name.lower()
                        resource_ids_and_paths[_id] = BASE_PATH + '/' + file_path
                else:
                    print("{} is an orphan; no resource points to it".format(file_path))

        resource_count = len(resource_ids_and_names.keys())
        print('{0} resources matched on the database'.format(resource_count))
        if resource_count == 0:
            return

        _upload_files_to_s3(resource_ids_and_names, resource_ids_and_paths)

    def update_all_visibility(self):
        if config.get('ckanext.s3filestore.acl', None) != 'auto':
            print("ckanext.s3filestore.acl must be set to 'auto' to execute update_all_visibility")
            return

        print("Updating the visibility of all datasets")

        packages_ids = []

        with DBConnection(config) as connection:

            packages = connection.execute(text('''
                    SELECT distinct package_id
                    FROM resource
                    WHERE state = 'active'
                    AND url IS NOT NULL
                    AND url <> ''
                    AND url_type = 'upload'
                '''))

            if packages.rowcount:
                for package in packages:
                    # package[0] is expected to be the id within the tuple
                    packages_ids.append(package[0])
            else:
                print("No resources found to make visible")

        for package_id in packages_ids:
            try:
                get_action('package_patch')(data_dict={'id': package_id}, context={'ignore_auth': True})
            except Exception as e:
                print("Unable to package_patch on package_id '{}', exception {} ".format(package_id, e))


def _upload_files_to_s3(resource_ids_and_names, resource_ids_and_paths):
    AWS_BUCKET_NAME = config.get('ckanext.s3filestore.aws_bucket_name')
    AWS_S3_ACL = config.get('ckanext.s3filestore.acl', 'public-read')
    s3_connection = get_s3_session(config).client('s3')

    context = {'ignore_auth': True}
    uploaded_resources = []
    for resource_id, file_name in resource_ids_and_names.iteritems():
        file_name = munge.munge_filename(file_name)
        key = 'resources/{resource_id}/{file_name}'.format(
            resource_id=resource_id, file_name=file_name)

        try:
            s3_connection.head_object(Bucket=AWS_BUCKET_NAME, Key=key)
            print("{} is already in S3, skipping".format(key))
            continue
        except ClientError:
            upload_file = open(resource_ids_and_paths[resource_id])

            acl = AWS_S3_ACL
            if acl == 'auto':
                package_id = get_action('resource_show')({'ignore_auth': True}, {'id': resource_id})['package_id']
                package = get_action('package_show')({'ignore_auth': True}, {'id': package_id})
                acl = 'private' if package['private'] else 'public-read'

            print("Uploading {} to S3 bucket {} under key {} with ACL {}".format(upload_file, AWS_BUCKET_NAME, key, acl))
            s3_connection.put_object(Bucket=AWS_BUCKET_NAME, Key=key, Body=upload_file, ACL=acl)
            uploaded_resources.append(resource_id)
            print('Uploaded resource {0} ({1}) to S3'.format(resource_id, file_name))
            try:
                get_action('resource_patch')(context, {'id': resource_id, 'url': file_name})
            except ValidationError:
                print("{} failed to validate; file is in S3 but might not be used".format(resource_id))
                pass

    print('Done, uploaded {0} resources to S3'.format(len(uploaded_resources)))
