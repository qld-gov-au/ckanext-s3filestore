#!/bin/bash
set -ex

echo "Start s3 mock"
# Run s3 moto local client just in case we can't mock direclty via tests
pip install wheel
pip install "moto[server]"
moto_server s3 &