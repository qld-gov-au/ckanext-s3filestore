#!/usr/bin/env bash

pytest -vv --ckan-ini=test.ini --cov=ckanext.s3filestore --junit-xml=/tmp/junit/results.xml
