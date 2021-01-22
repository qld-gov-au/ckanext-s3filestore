#!/bin/bash
set -ex

echo "Installing ckanext-s3filestore and its requirements..."
python setup.py develop
pip install -r requirements.txt
pip install -r dev-requirements.txt
