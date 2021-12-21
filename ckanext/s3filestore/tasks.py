#!/usr/bin/env python
# encoding: utf-8


import os
from ckan import plugins as p
from ckanext.s3filestore import plugin
from six.moves.urllib import parse as urlparse
import routes

import logging
toolkit = p.toolkit
config = toolkit.config
log = logging.getLogger(__name__)

def s3_afterUpdatePackage(ckan_ini_filepath, visibility_level, pkg_id, pkg_dict):
    '''
       Archive a package.
       '''
    load_config(ckan_ini_filepath)

    log.info('Starting s3_afterUpdatePackage task: package_id=%r, visibility_level=%s', pkg_id, visibility_level)

    # Do all work in a sub-routine since it can then be tested without celery.
    # Also put try/except around it is easier to monitor ckan's log rather than
    # celery's task status.
    try:
        plugin.after_update_resource_list_update(visibility_level, pkg_id, pkg_dict)
    except Exception as e:
        if os.environ.get('DEBUG'):
            raise
        # Any problem at all is logged and reraised so that celery can log it
        # too
        log.error('Error occurred during s3_afterUpdatePackage: %s\nPackage: %s',
                  e, pkg_id)
        raise

def load_config(ckan_ini_filepath):
    if ckan_ini_filepath:
        toolkit.load_config(ckan_ini_filepath)

    # give routes enough information to run url_for
    parsed = urlparse.urlparse(config.get('ckan.site_url', 'http://0.0.0.0'))
    request_config = routes.request_config()
    request_config.host = parsed.netloc + parsed.path
    request_config.protocol = parsed.scheme