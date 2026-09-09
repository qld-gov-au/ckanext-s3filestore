# encoding: utf-8

import logging
import six

from ckan import plugins
import ckantoolkit as toolkit
from ckanext.s3filestore import uploader as s3_uploader
from ckan.lib.uploader import get_resource_uploader as core_get_uploader

import ckanext.s3filestore.tasks as tasks

from ckanext.s3filestore.redis_helper import RedisHelper

LOG = logging.getLogger(__name__)


class S3FileStorePlugin(plugins.SingletonPlugin):

    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigurable)
    plugins.implements(plugins.IUploader)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IResourceController, inherit=True)

    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IClick)

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

        self.async_visibility_update = toolkit.asbool(config.get(
            'ckanext.s3filestore.acl.async_update', 'True'))

    # IUploader

    def get_resource_uploader(self, resource_dict):
        '''Return an uploader object used to upload resource files.'''
        return s3_uploader.S3ResourceUploader(resource_dict)

    def get_uploader(self, upload_to, old_filename=None):
        '''Return an uploader object used to upload general files.'''
        return s3_uploader.S3Uploader(upload_to, old_filename)

    # IPackageController

    def after_dataset_update(self, context, pkg_dict):
        ''' Update the access of each S3 object to match the package.
        '''
        pkg_id = pkg_dict['id']
        LOG.debug("after_dataset_update: Package %s has been updated, notifying resources", pkg_id)

        is_private = pkg_dict.get('private', False)
        is_private_str = six.text_type(is_private)

        redis = RedisHelper()
        cache_private = redis.get(pkg_id + '/private')
        redis.put(pkg_id + '/private', is_private_str, expiry=86400)
        # compare current and previous 'private' flags so we know
        # if visibility has changed
        if cache_private is not None and cache_private == is_private_str:
            LOG.debug("Package %s privacy is unchanged", pkg_id)
            return

        # visibility has changed; update associated S3 objects
        visibility_level = 'private' if is_private else 'public-read'
        async_update = self.async_visibility_update
        if async_update:
            try:
                self.enqueue_resource_visibility_update_job(visibility_level, pkg_id)
            except Exception as e:
                LOG.debug("after_dataset_update: Failed to enqueue, updating inline. Error: [%s]", e)
                async_update = False
        if not async_update:
            if 'resources' not in pkg_dict:
                pkg_dict = toolkit.get_action('package_show')(
                    context=context, data_dict={'id': pkg_id})
            self.after_update_resource_list_update(visibility_level, pkg_id, pkg_dict)

    def after_update_resource_list_update(self, visibility_level, pkg_id, pkg_dict):

        LOG.debug("after_update_resource_list_update: Package %s has been updated, notifying resources", pkg_id)
        for resource in pkg_dict['resources']:
            if 'id' not in resource:
                # skip new resources as they would already have correct visibility
                continue
            uploader = core_get_uploader(resource)
            if hasattr(uploader, 'update_visibility'):
                uploader.update_visibility(
                    resource['id'],
                    target_acl=visibility_level)
        LOG.debug("after_update_resource_list_update: Package %s has been updated, notifying resources finished", pkg_id)

    def enqueue_resource_visibility_update_job(self, visibility_level, pkg_id):

        enqueue_args = {
            'fn': tasks.s3_afterUpdatePackage,
            'title': "s3_afterUpdatePackage: setting {} on {}".format(visibility_level, pkg_id),
            'kwargs': {'visibility_level': visibility_level, 'pkg_id': pkg_id},
        }
        ttl = 24 * 60 * 60  # 24 hour ttl.
        rq_kwargs = {
            'ttl': ttl,
            'failure_ttl': ttl
        }
        enqueue_args['rq_kwargs'] = rq_kwargs

        # Optional variable, if not set, default queue is used
        queue = toolkit.config.get('ckanext.s3filestore.queue', None)
        if queue:
            enqueue_args['queue'] = queue

        toolkit.enqueue_job(**enqueue_args)
        LOG.debug("enqueue_resource_visibility_update_job: Package %s has been enqueued",
                  pkg_id)

    # IResourceController

    def before_resource_update(self, context, current, resource):
        """
        Ensure that we have cached the resource visibility if needed.
        """
        if current['url_type'] == 'upload' and 'upload' in resource:
            uploader = s3_uploader.S3ResourceUploader(current)
            try:
                uploader.is_key_public(uploader.get_path(current['id']))
            except Exception:
                # if we can't update the cache, then we don't need it.
                pass

    def before_resource_delete(self, context, resource_id_dict, resources):
        """
        Delete the stored file from S3 when the CKAN resource is deleted.

        Ideally this would occur after the CKAN deletion is complete,
        but the 'after_resource_delete' hook doesn't give us the ID.
        """
        resource_id = resource_id_dict.get('id')
        for resource in resources:
            if resource.get('id') == resource_id:
                s3_uploader.S3ResourceUploader(resource).delete(resource_id)
                return
        else:
            LOG.error("Unable to find target resource [%s] for deletion", resource_id)

    # IBlueprint

    def get_blueprint(self):
        from ckanext.s3filestore.views import\
            resource, uploads
        return resource.get_blueprints() + uploads.get_blueprints()

    # IClick

    def get_commands(self):
        from ckanext.s3filestore import click_commands
        return [click_commands.s3]
