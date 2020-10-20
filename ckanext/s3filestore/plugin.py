from routes.mapper import SubMapper
import ckan.plugins as plugins
import ckantoolkit as toolkit

import ckanext.s3filestore.uploader
from ckan.lib.uploader import ResourceUpload as DefaultResourceUpload

class S3FileStorePlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.IUploader)
    plugins.implements(plugins.IRoutes, inherit=True)


    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')

    # IConfigurable

    def configure(self, config):
        # Certain config options must exists for the plugin to work. Raise an
        # exception if they're missing.
        missing_config = "{0} is not configured. Please amend your .ini file."

        required_options = (
            'ckanext.s3filestore.aws_bucket_name',
            'ckanext.s3filestore.region_name',
            'ckanext.s3filestore.signature_version'
        )
        if not config.get('ckanext.s3filestore.aws_use_ami_role'):
            required_options += ('ckanext.s3filestore.aws_access_key_id',
                                 'ckanext.s3filestore.aws_secret_access_key')

        for option in required_options:
            if not config.get(option, None):
                raise RuntimeError(missing_config.format(option))

        # Check that options actually work, if not exceptions will be raised
        if toolkit.asbool(
                config.get('ckanext.s3filestore.check_access_on_startup',
                           True)):
            ckanext.s3filestore.uploader.BaseS3Uploader().get_s3_bucket(
                config.get('ckanext.s3filestore.aws_bucket_name'))


    # IUploader

    def get_resource_uploader(self, data_dict):
        '''Return an uploader object used to upload resource files.'''
        return ckanext.s3filestore.uploader.S3ResourceUploader(data_dict)

    def get_uploader(self, upload_to, old_filename=None):
        '''Return an uploader object used to upload general files.'''
        return ckanext.s3filestore.uploader.S3Uploader(upload_to,
                                                       old_filename)

    # IRoutes

    def before_map(self, map):
        with SubMapper(map, controller='ckanext.s3filestore.controller:S3Controller') as m:
            # Override the resource download links
            # if plugins.toolkit.check_ckan_version(max_version='2.8.2') & \
            if hasattr(DefaultResourceUpload, "download") == False :
                m.connect('resource_download',
                          '/dataset/{id}/resource/{resource_id}/download',
                          action='resource_download')
                m.connect('resource_download',
                          '/dataset/{id}/resource/{resource_id}/download/{filename}',
                          action='resource_download')
            #Allow fallback to access old files
            use_filename = toolkit.asbool(toolkit.config.get('ckanext.s3filestore.use_filename', False))
            if not use_filename:
                m.connect('resource_download',
                          '/dataset/{id}/resource/{resource_id}/orig_download/{filename}',
                          action='resource_download')

            # fallback controller action to download from the filesystem
            m.connect('filesystem_resource_download',
                      '/dataset/{id}/resource/{resource_id}/fs_download/{filename}',
                      action='filesystem_resource_download')

            # Intercept the uploaded file links (e.g. group images)
            m.connect('uploaded_file', '/uploads/{upload_to}/{filename}',
                      action='uploaded_file_redirect')

        return map
