.. You should enable this project on coveralls.io to make these badges work.
   The necessary Travis and Coverage config files have been generated for you.

.. image:: https://github.com/keitaroinc/ckanext-s3filestore/workflows/CI/badge.svg
    :target: https://github.com/keitaroinc/ckanext-s3filestore/actions


.. image:: https://coveralls.io/repos/github/keitaroinc/ckanext-s3filestore/badge.svg?branch=main
     :target: https://coveralls.io/github/keitaroinc/ckanext-s3filestore?branch=main

.. image:: https://img.shields.io/badge/python-3.8-blue.svg
    :target: https://www.python.org/downloads/release/python-384/

.. image:: https://img.shields.io/pypi/v/ckanext-s3filestore
    :target: https://pypi.org/project/ckanext-s3filestore



===================
ckanext-s3filestore
===================

.. Put a description of your extension here:

Use Amazon S3 or Minio<https://minio.io/> as a filestore for resources.


------------
Requirements
------------

Requires CKAN 2.9+

When installing this extension on CKAN versions prior 2.9 please use `ckan-2.8 <https://github.com/keitaroinc/ckanext-s3filestore/tree/ckan-2.8>`_ branch.

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
   ``/etc/ckan/default/ckan.ini``).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu::

     sudo service apache2 reload


---------------
Config Settings
---------------

Required::

    ckanext.s3filestore.aws_bucket_name = a-bucket-to-store-your-stuff
    ckanext.s3filestore.region_name = region-name
    ckanext.s3filestore.signature_version = s3v4

Conditional::

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

    # An optional setting to change the acl of the uploaded files. Default public-read.
    ckanext.s3filestore.acl = private

    # An optional setting to specify which addressing style to use.
    # This controls whether the bucket name is in the hostname or is
    # part of the URL path. Options are 'path', 'virtual', and 'auto';
    # default is 'auto'.
    ckanext.s3filestore.addressing_style = path

    # Set this parameter only if you want to use a provider like Minio
    # as a filestore service instead of S3.
    ckanext.s3filestore.host_name = http://minio-service.com

    # To mask the S3 endpoint with your own domain/endpoint when serving URLs to end users.
    # This endpoint should be capable of serving S3 objects as if it were an actual bucket.
    # The real S3 endpoint will still be used for uploading files.
    ckanext.s3filestore.download_proxy = https://example.com/my-bucket

    # Defines how long a signed URL is valid (default 1 hour).
    ckanext.s3filestore.signed_url_expiry = 3600

    # Don't check for access on each startup
    ckanext.s3filestore.check_access_on_startup = false


-----------------
CLI
-----------------

To upload all local resources located in `ckan.storage_path` location dir to the configured S3 bucket use::

    ckan -c /etc/ckan/default/ckan.ini s3-upload


------------------------
Development Installation
------------------------

To install ckanext-s3filestore for development, activate your CKAN virtualenv and
do::

    git clone https://github.com/keitaroinc/ckanext-s3filestore.git
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
