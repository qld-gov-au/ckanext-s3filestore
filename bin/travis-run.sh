#!/bin/sh -e

pytest --ckan-ini=subdir/test.ini --cov=ckanext.s3filestore --disable-warnings ckanext/s3filestore/tests
nosetests --ckan --nologcapture --with-pylons=subdir/test.ini --with-coverage --cover-package=ckanext.s3filestore --cover-inclusive --cover-erase --cover-tests

