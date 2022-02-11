# encoding: utf-8

import logging
import os

from ckan import plugins as p

toolkit = p.toolkit
log = logging.getLogger(__name__)


def s3_afterUpdatePackage(ckan_ini_filepath=None, visibility_level=None, pkg_id=None, pkg_dict=None):
    u'''
    After Update a package.

    :param string ckan_ini_filepath: Deprecated, will be removed version+1 release so that in situ jobs are not lost.

    :param boolean visibility_level: what visibility should be set

    :param string pkg_id: package id for resources to update

    :param dict pkg_dic: Deprecated, will be removed version+1 release so that in situ jobs are not lost.

    :raises Exception: if job has failure.
    '''

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
        log.error('Error s3_afterUpdatePackage task: package_id=%r, visibility_level=%s stackTrace: %s',
                  pkg_id, visibility_level, e)
        raise
