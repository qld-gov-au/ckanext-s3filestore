.. You should enable this project on travis-ci.org and coveralls.io to make
   these badges work. The necessary Travis and Coverage config files have been
   generated for you.

.. image:: https://travis-ci.org/okfn/ckanext-s3filestore.svg?branch=master
    :target: https://travis-ci.org/okfn/ckanext-s3filestore


.. image:: https://coveralls.io/repos/okfn/ckanext-s3filestore/badge.svg
  :target: https://coveralls.io/r/okfn/ckanext-s3filestore


===================
ckanext-s3filestore
===================

.. Put a description of your extension here:

Use Amazon S3 or Minio<https://minio.io/> as a filestore for resources.


------------
Requirements
------------

Requires CKAN 2.8+


------------
Installation
------------

.. Add any additional install steps to the list below.
   For example installing any non-Python dependencies or adding any required
   config settings.

To install ckanext-s3filestore:

1. Activate your CKAN virtual environment, for example::

     . /usr/lib/ckan/default/bin/activate

2. Install the ckanext-s3filestore Python package into your virtual environment::

     pip install ckanext-s3filestore

3. Add ``s3filestore`` to the ``ckan.plugins`` setting in your CKAN
   config file (by default the config file is located at
   ``/etc/ckan/default/production.ini``).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu::

     sudo service apache2 reload


---------------
Config Settings
---------------

Required::


    ckanext.s3filestore.aws_bucket_name = a-bucket-to-store-your-stuff
    ckanext.s3filestore.host_name = host-to-S3-cloud storage 
    ckanext.s3filestore.region_name = region-name
    ckanext.s3filestore.signature_version = signature (s3v4)

Conditional:

   ckanext.s3filestore.aws_access_key_id = Your-Access-Key-ID
   ckanext.s3filestore.aws_secret_access_key = Your-Secret-Access-Key

   Or:

   ckanext.s3filestore.aws_use_ami_role = true

Optional::

    # An optional path to prepend to keys
    ckanext.s3filestore.aws_storage_path = my-site-name

    # An optional setting to fallback to filesystem for downloads
    ckanext.s3filestore.filesystem_download_fallback = true
    # The ckan storage path option must also be set correctly for the fallback to work
    ckan.storage_path = path/to/storage/directory

    # To change the acl of the uploaded file. Default is public-read.
    ckanext.s3filestore.acl = private


------------------------
Development Installation
------------------------

To install ckanext-s3filestore for development, activate your CKAN virtualenv and
do::

    git clone https://github.com/okfn/ckanext-s3filestore.git
    cd ckanext-s3filestore
    python setup.py develop
    pip install -r dev-requirements.txt
    pip install -r requirements.txt


-----------------
Running the Tests
-----------------

To run the tests, do::

    nosetests --ckan --nologcapture --with-pylons=test.ini

To run the tests and produce a coverage report, first make sure you have
coverage installed in your virtualenv (``pip install coverage``) then run::

    nosetests --ckan --nologcapture --with-pylons=test.ini --with-coverage --cover-package=ckanext.s3filestore --cover-inclusive --cover-erase --cover-tests

------------------------
Docker environment setup
------------------------

docker start up

    docker run -it -v "`pwd`":/build ubuntu:bionic /bin/bash

commands before travis setup
cd /build
apt-get update
apt-get install sudo systemd postgresql-10 git python python-pip

export PGVERSION=10 && export CKAN_BRANCH=qgov-master && export CKAN_GIT_REPO=qld-gov-au/ckan
cd /build
bash bin/travis-build.bash
nosetests --ckan  --with-pylons=subdir/test.ini --with-coverage --cover-package=ckanext.s3filestore --cover-inclusive --cover-erase --cover-tests

---------------------------------------
Registering ckanext-s3filestore on PyPI
---------------------------------------

ckanext-s3filestore should be available on PyPI as
https://pypi.python.org/pypi/ckanext-s3filestore. If that link doesn't work, then
you can register the project on PyPI for the first time by following these
steps:

1. Create a source distribution of the project::

     python setup.py sdist

2. Register the project::

     python setup.py register

3. Upload the source distribution to PyPI::

     python setup.py sdist upload

4. Tag the first release of the project on GitHub with the version number from
   the ``setup.py`` file. For example if the version number in ``setup.py`` is
   0.0.1 then do::

       git tag 0.0.1
       git push --tags


----------------------------------------------
Releasing a New Version of ckanext-s3filestore
----------------------------------------------

ckanext-s3filestore is available on PyPI as https://pypi.python.org/pypi/ckanext-s3filestore.
To publish a new version to PyPI follow these steps:

1. Update the version number in the ``setup.py`` file.
   See `PEP 440 <http://legacy.python.org/dev/peps/pep-0440/#public-version-identifiers>`_
   for how to choose version numbers.

2. Create a source distribution of the new version::

     python setup.py sdist

3. Upload the source distribution to PyPI::

     python setup.py sdist upload

4. Tag the new release of the project on GitHub with the version number from
   the ``setup.py`` file. For example if the version number in ``setup.py`` is
   0.0.2 then do::

       git tag 0.0.2
       git push --tags

-----------
Change Log
-----------

0.3.0
   Update from boto to boto3
   Update to Ckan version 2.8+

0.2.0
   Support for AMI Roles
   ACL for uploaded file can be configured
   don't assume that error codes are numeric
   fix filesystem fallback, resolves #28
   set explicit ContentType on boto Put command and store the mimetype in CKAN resource table

0.1.1
   Support for Flask-based requests

0.1.0
   Fix downloading large files

0.0.9
   Add populating of resources' last_modified field

0.0.8
   Add option for fallback to local filesytem from s3

0.0.7
   redirect always get string intead of unicode

0.0.6
   Allow minio s3 like datastore

0.0.5
   Add boto to install requires

0.0.4
    Avoid exception when resources marked for clearing but not yet exist
    New, not yet created resources can be marked for deletion (with `clear_upload`) if the user cancels an upload and enters a URL instead. Check if resources have an id or if an old name is provided before trying to clear a file.

0.0.3
   Requires CKAN 2.5+ as IUploader now in CKAN2.5

0.0.2
   Change the resource file names to lower case

0.0.1
   Alpha release of plugin