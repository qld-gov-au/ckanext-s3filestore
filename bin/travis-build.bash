#!/bin/bash
set -e

echo "This is travis-build.bash..."

echo "Installing the packages that CKAN requires..."
sudo apt-get update -qq
sudo apt-get install postgresql-$PGVERSION solr-jetty openjdk-8-jdk libcommons-fileupload-java:amd64 redis-server
echo "Start postgres"
sudo service postgresql start

echo "Start redis"
sudo service redis-server start

echo "Start s3 mock"
# Run s3 moto local client just in case we can't mock direclty via tests
pip install "moto[server]"
moto_server s3 &

echo "Installing CKAN and its Python dependencies..."
git clone https://github.com/$CKAN_GIT_REPO
cd ckan
git checkout $CKAN_BRANCH
python setup.py develop
pip install -r requirements.txt
pip install -r dev-requirements.txt
cd -

echo "start solr"
# Fix solr-jetty starting issues https://stackoverflow.com/a/56007895
# https://github.com/Zharktas/ckanext-report/blob/py3/bin/travis-run.bash
sudo mkdir /etc/systemd/system/jetty9.service.d
printf "[Service]\nReadWritePaths=/var/lib/solr" | sudo tee /etc/systemd/system/jetty9.service.d/solr.conf
sed '16,21d' /etc/solr/solr-jetty.xml | sudo tee /etc/solr/solr-jetty.xml
sudo systemctl daemon-reload

printf "NO_START=0\nJETTY_HOST=127.0.0.1\nJETTY_ARGS=\"jetty.http.port=8983\"\nJAVA_HOME=$JAVA_HOME" | sudo tee /etc/default/jetty9
sudo cp ckan/ckan/config/solr/schema.xml /etc/solr/conf/schema.xml
sudo service jetty9 restart

# Wait for jetty9 to start
timeout 20 bash -c 'while [[ "$(curl -s -o /dev/null -I -w %{http_code} http://localhost:8983)" != "200" ]]; do sleep 2;done'

echo "Creating the PostgreSQL user and database..."
sudo -u postgres psql -c "CREATE USER ckan_default WITH PASSWORD 'pass';"
sudo -u postgres psql -c 'CREATE DATABASE ckan_test WITH OWNER ckan_default;'

echo "Initialising the database..."
cd ckan
paster db init -c test-core.ini
cd -

echo "Installing ckanext-s3filestore and its requirements..."
python setup.py develop
pip install -r requirements.txt
pip install -r dev-requirements.txt

echo "Moving test.ini into a subdir..."
mkdir subdir
mv test.ini subdir



echo "travis-build.bash is done."

