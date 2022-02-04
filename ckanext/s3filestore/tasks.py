# encoding: utf-8

import logging
import os

from ckan import plugins as p

toolkit = p.toolkit
log = logging.getLogger(__name__)


def s3_afterUpdatePackage(ckan_ini_filepath, visibility_level, pkg_id, pkg_dict=None):
    '''
    Archive a package.
    '''
    if ckan_ini_filepath:
        toolkit.load_config(ckan_ini_filepath)

    log.info('Starting s3_afterUpdatePackage task: package_id=%r, visibility_level=%s', pkg_id, visibility_level)

    # Do all work in a sub-routine so it can be tested without a job queue.
    # Also put try/except around it, as it is easier to monitor CKAN's log
    # rather than a queue's task status.
    try:
        pkg_dict = toolkit.get_action('package_show')({'ignore_auth': True}, {'id': pkg_id})

        plugin = p.get_plugin("s3filestore")
        plugin.after_update_resource_list_update(visibility_level, pkg_id, pkg_dict)
        log.info('Finished s3_afterUpdatePackage task: package_id=%r, visibility_level=%s', pkg_id, visibility_level)

    except Exception as e:
        if os.environ.get('DEBUG'):
            raise
        # Any problem at all is logged and reraised so that the job queue
        # can log it too
        log.error('Error s3_afterUpdatePackage task: Error occurred package_id=%r, visibility_level=%s: %s',
                  pkg_id, visibility_level, e)
        raise
