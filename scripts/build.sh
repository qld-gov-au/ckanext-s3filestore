#!/usr/bin/env bash
##
# Build site in CI.
#
set -ex

if [ "$CKAN_VERSION" = "2.9" ]; then
    pip install "setuptools>=44.1.0,<71"
fi
if [ "$CKAN_GIT_ORG" != "ckan" ]; then
  SRC_DIR=/srv/app/src
  APP_DIR=/srv/app
#  PIP_SRC=${SRC_DIR}
  pushd ${APP_DIR}
    echo "pip install -e git+https://github.com/${CKAN_GIT_ORG}/ckan.git@${CKAN_GIT_VERSION}#egg=ckan"
    echo "update manually as its already a git pip installed module"
    git config --global --add safe.directory "$SRC_DIR/ckan"
  popd

  pushd ${SRC_DIR}/ckan

  git remote set-url origin "https://github.com/${CKAN_GIT_ORG}/ckan.git"
  time git fetch origin #could be the tag/branch only if download time is slow
  git clean -f
  git reset --hard
  find . -name '*.pyc' -delete
  git checkout "${CKAN_GIT_VERSION}"
  pip install --no-binary :all: -r requirements.txt

  popd
fi

pip install -r requirements.txt
pip install -r dev-requirements.txt
pip install -e .
# Replace default path to CKAN core config file with the one on the container
sed -i -e "s|use = config:.*|use = config:${SRC_DIR}/ckan/test-core.ini|" test.ini
