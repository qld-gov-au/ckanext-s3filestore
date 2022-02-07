# encoding: utf-8

import click

from ckanext.s3filestore.cli_commands import S3FilestoreCommands


@click.group()
def s3():
    """ S3 Filestore commands
    """
    pass


@s3.command(short_help=u'CKAN S3 FileStore utilities')
def check_config():
    S3FilestoreCommands().check_config()


@s3.command()
@click.argument(u'identifier', default='all')
def upload(identifier):
    commands = S3FilestoreCommands()
    if identifier == 'all':
        commands.upload_all()
    elif identifier == 'pairtree':
        commands.upload_pairtree()
    else:
        commands.upload_single(identifier)


@s3.command(short_help=u'Updates the visibility of all existing S3 objects to match current config')
def update_all_visibility():
    S3FilestoreCommands().update_all_visibility()
