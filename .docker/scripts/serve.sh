#!/usr/bin/env sh
set -e

dockerize -wait tcp://postgres:5432 -timeout 1m
dockerize -wait tcp://solr:8983 -timeout 1m

echo "Start s3 mock"
# Run s3 moto local client just in case we can't mock directly via tests
moto_server s3 &

sed -i "s@SITE_URL@${SITE_URL}@g" /app/ckan/default/production.ini

python -m smtpd -n -c DebuggingServer localhost:25 &

. /app/ckan/default/bin/activate \
    && paster serve /app/ckan/default/production.ini
