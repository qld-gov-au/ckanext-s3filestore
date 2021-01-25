#!/bin/bash
set -ex

echo "Installing CKAN and its Python dependencies..."
if [ ! -d ckan ]; then
  git clone https://github.com/$CKAN_GIT_REPO
fi
cd ckan
git checkout $CKAN_BRANCH


#work around for easy_install not having write permissions on image which needs to run sudo on python setup.
python setup.py develop
pip install -r requirements.txt
pip install -r dev-requirements.txt
cd -

echo "copy solr schema over"
sudo cp ckan/ckan/config/solr/schema.xml /etc/solr/conf/schema.xml

echo "start solr"
sudo /usr/share/jetty9/bin/jetty.sh restart

# Wait for jetty9 to start
timeout 20 bash -c 'while [[ "$(curl -s -o /dev/null -I -w %{http_code} http://localhost:8983)" != "200" ]]; do sleep 2;done'


echo "Initialising the database..."
cd ckan
paster db init -c test-core.ini
cd -