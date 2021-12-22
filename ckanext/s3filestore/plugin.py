# encoding: utf-8
import os
import logging

from routes.mapper import SubMapper
from ckan import plugins

from ckanext.s3filestore import uploader as s3_uploader
from ckanext.s3filestore.views import\
    resource as resource_view, uploads as uploads_view
from ckan.lib.uploader import ResourceUpload as DefaultResourceUpload,\
    get_resource_uploader

from ckanext.s3filestore.tasks import s3_afterUpdatePackage

LOG = logging.getLogger(__name__)
toolkit = plugins.toolkit


class S3FileStorePlugin(plugins.SingletonPlugin):

    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.IUploader)
    plugins.implements(plugins.IPackageController, inherit=True)

    if toolkit.check_ckan_version(min_version='2.8.0'):
        plugins.implements(plugins.IBlueprint)
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

    # IPackageController

    def after_update(self, context, pkg_dict):
        ''' Update the access of each S3 object to match the package.
                '''
        pkg_id = pkg_dict['id']
        is_private = pkg_dict.get('private', False)
        LOG.debug("after_update: Package %s has been updated, notifying resources", pkg_id)

        if 'resources' not in pkg_dict:
            pkg_dict = toolkit.get_action('package_show')(
                context=context, data_dict={'id': pkg_id})

        visibility_level = 'private' if is_private else 'public-read'
        try:
            self.enqueue_resource_visibility_update_job(visibility_level, pkg_id, pkg_dict)
        except Exception as e:
            LOG.debug("after_update: Could not enqueue due to %s, doing inline", e)
            self.after_update_resource_list_update(visibility_level, pkg_id, pkg_dict)

    def after_update_resource_list_update(self, visibility_level, pkg_id, pkg_dict):

        LOG.debug("after_update_resource_list_update: Package %s has been updated, notifying resources", pkg_id)
        for resource in pkg_dict['resources']:
            uploader = get_resource_uploader(resource)
            if hasattr(uploader, 'update_visibility'):
                uploader.update_visibility(
                    resource['id'],
                    target_acl=visibility_level)
        LOG.debug("after_update_resource_list_update: Package %s has been updated, notifying resources finished", pkg_id)

    def enqueue_resource_visibility_update_job(self, visibility_level, pkg_id, pkg_dict):
        ckan_ini_filepath = os.path.abspath(toolkit.config['__file__'])
        resources = pkg_dict
        args = [ckan_ini_filepath, visibility_level, resources]
        kwargs = {
            'args': args,
            'title': "s3_afterUpdatePackage: setting " + visibility_level + " on " + pkg_id
        }
        # Optional variable, if not set, default queue is used
        queue = toolkit.config.get('ckanext.s3filestore.queue', None)
        if queue:
            kwargs['queue'] = queue

        toolkit.enqueue_job(s3_afterUpdatePackage, **kwargs)
        LOG.debug("enqueue_resource_visibility_update_job: Package %s has been enqueued",
                  pkg_id)

    # IRoutes
    # Ignored on CKAN >= 2.8

    def before_map(self, map):
        with SubMapper(map, controller='ckanext.s3filestore.controller:S3Controller') as m:
            # Override the resource download links
            if not hasattr(DefaultResourceUpload, 'download'):
                m.connect('resource_download',
                          '/dataset/{id}/resource/{resource_id}/download',
                          action='resource_download')
                m.connect('resource_download',
                          '/dataset/{id}/resource/{resource_id}/download/{filename}',
                          action='resource_download')

            # fallback controller action to download from the filesystem
            m.connect('filesystem_resource_download',
                      '/dataset/{id}/resource/{resource_id}/fs_download/{filename}',
                      action='filesystem_resource_download')

            # Allow fallback to access old files
            use_filename = toolkit.asbool(toolkit.config.get('ckanext.s3filestore.use_filename', False))
            if not use_filename:
                m.connect('resource_download',
                          '/dataset/{id}/resource/{resource_id}/orig_download/{filename}',
                          action='resource_download')

            # Intercept the uploaded file links (e.g. group images)
            m.connect('uploaded_file', '/uploads/{upload_to}/{filename}',
                      action='uploaded_file_redirect')

        return map

    # IBlueprint
    # Ignored on CKAN < 2.8

    def get_blueprint(self):
        return resource_view.get_blueprints() + uploads_view.get_blueprints()
