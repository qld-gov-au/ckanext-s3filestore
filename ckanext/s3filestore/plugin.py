# encoding: utf-8
import ckan.plugins as plugins
import ckantoolkit as toolkit

from ckanext.s3filestore import uploader as s3_uploader


class S3FileStorePlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.IUploader)

    if toolkit.check_ckan_version(min_version='2.9.0'):
        plugins.implements(plugins.IBlueprint)
        plugins.implements(plugins.IClick)
    else:
        plugins.implements(plugins.IRoutes, inherit=True)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        # We need to register the following templates dir in order
        # to fix downloading the HTML file instead of previewing when
        # 'webpage_view' is enabled
        toolkit.add_template_directory(config_, 'theme/templates')

    # IConfigurable

    def configure(self, config):
        # Certain config options must exists for the plugin to work. Raise an
        # exception if they're missing.
        missing_config = "{0} is not configured. Please amend your .ini file."
        config_options = (
            'ckanext.s3filestore.aws_bucket_name',
            'ckanext.s3filestore.region_name',
            'ckanext.s3filestore.signature_version'
        )

        if not config.get('ckanext.s3filestore.aws_use_ami_role'):
            config_options += ('ckanext.s3filestore.aws_access_key_id',
                               'ckanext.s3filestore.aws_secret_access_key')

        for option in config_options:
            if not config.get(option, None):
                raise RuntimeError(missing_config.format(option))

        # Check that options actually work, if not exceptions will be raised
        if toolkit.asbool(
                config.get('ckanext.s3filestore.check_access_on_startup',
                           True)):
            s3_uploader.BaseS3Uploader().get_s3_bucket(
                config.get('ckanext.s3filestore.aws_bucket_name'))

    # IUploader

    def get_resource_uploader(self, data_dict):
        '''Return an uploader object used to upload resource files.'''
        return s3_uploader.S3ResourceUploader(data_dict)

    def get_uploader(self, upload_to, old_filename=None):
        '''Return an uploader object used to upload general files.'''
        return s3_uploader.S3Uploader(upload_to, old_filename)

    # IRoutes
    # Ignored on CKAN >= 2.9

    def before_map(self, map):
        from routes.mapper import SubMapper

        with SubMapper(map, controller='ckanext.s3filestore.controller:S3Controller') as m:
            # Override the resource download links
            m.connect('resource_download',
                      '/dataset/{id}/resource/{resource_id}/download',
                      action='resource_download')
            m.connect('resource_download',
                      '/dataset/{id}/resource/{resource_id}/download/{filename}',
                      action='resource_download')

            # fallback controller action to download from the filesystem
            m.connect('s3_resource.filesystem_resource_download',
                      '/dataset/{id}/resource/{resource_id}/fs_download/{filename}',
                      action='filesystem_resource_download')

            # Intercept the uploaded file links (e.g. group images)
            m.connect('uploaded_file', '/uploads/{upload_to}/{filename}',
                      action='uploaded_file_redirect')

        return map

    # IBlueprint
    # Ignored on CKAN < 2.9

    def get_blueprint(self):
        from ckanext.s3filestore.views import resource, uploads
        return resource.get_blueprints() + uploads.get_blueprints()

    # IClick
    # Ignored on CKAN < 2.9

    def get_commands(self):
        from ckanext.s3filestore.click_commands import upload_resources
        return [upload_resources]
