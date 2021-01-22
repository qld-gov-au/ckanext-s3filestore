#!/bin/bash
set -ex

echo "This is travis-build.bash..."

echo "Installing the packages that CKAN requires..."
apt-get update -qq
#software-properties-common not installed on slim
apt-get install software-properties-common -y -qqq
wget -qO - https://adoptopenjdk.jfrog.io/adoptopenjdk/api/gpg/key/public | apt-key add -
add-apt-repository --yes https://adoptopenjdk.jfrog.io/adoptopenjdk/deb/

apt-get update -qq
#man folder needs to be available for adoptopenjdk-8 to finish configuring
mkdir -p /usr/share/man/man1/
apt-get install adoptopenjdk-8-hotspot -y -qq

#ensure openjdk-8-jdk is found for some installations, thanks b8kich for the virtual wrapper
curl https://gitlab.com/b8kich/adopt-openjdk-8-jdk/-/raw/master/adopt-openjdk-8-jdk_0.1_all.deb?inline=false -o adopt-openjdk-8-jdk_0.1_all.deb
dpkg -i adopt-openjdk-8-jdk_0.1_all.deb

# todo make this dynamic on where which java points to
export JAVA_HOME="/usr/lib/jvm/adoptopenjdk-8-hotspot-amd64/"

apt-get install systemd git python-pip postgresql-$PGVERSION solr-jetty libcommons-fileupload-java:amd64 redis-server -y -qq
echo "Start postgres"
service postgresql start

echo "Creating the PostgreSQL user and database..."
su - postgres -c "psql -c \"CREATE USER ckan_default WITH PASSWORD 'pass';\""
su - postgres -c "psql -c 'CREATE DATABASE ckan_test WITH OWNER ckan_default;'"


echo "Start redis"
service redis-server start

echo "Start s3 mock"
# Run s3 moto local client just in case we can't mock direclty via tests
pip install "moto[server]"
moto_server s3 &

echo "setup solr"
# Fix solr-jetty starting issues https://stackoverflow.com/a/56007895
# https://github.com/Zharktas/ckanext-report/blob/py3/bin/travis-run.bash
mkdir -p /etc/systemd/system/jetty9.service.d
printf "[Service]\nReadWritePaths=/var/lib/solr" | tee /etc/systemd/system/jetty9.service.d/solr.conf
sed '16,21d' /etc/solr/solr-jetty.xml | tee /etc/solr/solr-jetty.xml
printf "NO_START=0\nJETTY_HOST=127.0.0.1\nJETTY_ARGS=\"jetty.http.port=8983\"\nJAVA_HOME=$JAVA_HOME" | tee /etc/default/jetty9


echo "Moving test.ini into a subdir..."
# unsure why we do this
mkdir -p subdir
cp test.ini subdir

echo "build.bash is done."
