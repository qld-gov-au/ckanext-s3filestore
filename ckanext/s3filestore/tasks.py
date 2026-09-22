# encoding: utf-8

import logging
import os

from ckan import plugins as p

from . import uploader as s3_uploader

toolkit = p.toolkit
log = logging.getLogger(__name__)


def s3_afterUpdatePackage(visibility_level=None, pkg_id=None):
    u'''
    After Update a package.

    :param boolean visibility_level: what visibility should be set

    :param string pkg_id: package id for resources to update

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


def s3_afterUpdateResource(resource_id=None):
    u'''
    After updating a resource, set S3 object visibility to match.

    :param string resource_id: resource id to update

    :raises Exception: if job has failure.
    '''

    log.info('Starting s3_afterUpdateResource task: resource_id=%r', resource_id)

    # Do all work in a sub-routine so it can be tested without a job queue.
    # Also put try/except around it, as it is easier to monitor CKAN's log
    # rather than a queue's task status.
    try:
        s3_uploader.update_visibility(resource_id)
        log.info('Finished s3_afterUpdateResource task: resource_id=%r', resource_id)

    except Exception as e:
        if os.environ.get('DEBUG'):
            raise
        # Any problem at all is logged and reraised so that the job queue
        # can log it too
        log.error('Error s3_afterUpdateResource task: resource_id=%r stackTrace: %s',
                  resource_id, e)
        raise
