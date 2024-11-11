#!/usr/bin/env bash

pytest -vv --ckan-ini=test.ini --cov=ckanext.s3filestore
