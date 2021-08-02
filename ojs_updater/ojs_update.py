#!/usr/bin/env python3
# Copyright 2019-2021, UB JCS, Goethe University Frankfurt am Main
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


"""This script tries to simplify the process of updating
OJS instances. It creates backups of both the database
and the OJS folders, carries out the actual update process
and tries to take care of all the nasty things that can
happen in between.
"""
import sys
import os
import logging

from .settings import get_settings
from .updater import Updater
from .ojsinstance import OJSInstance
from .commons import get_script_name, check_disk_usage, check_permissions, drop_privileges, ZCLock

SUPPORTED_PLATFORMS = {'posix'}

def setup_logging():
    """Setup logging."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(levelname)s:%(asctime)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def update(settings, logger):
    """ Run the update process. """
    # workaround for moving the creation of a path object inside the object
    if logger is None:
        raise NotImplementedError
    updater = Updater(settings['ojs_version_folder'], settings, logger=logger)
    locations = (os.getcwd(),
                 settings['temp_dir'],
                 settings['ojs_version_folder'],
                 settings['ojs_backup_folder'],
                 settings['ojs_backup_db'],
                 settings['ojs_backup_www']
                 )
    if not check_permissions(locations, logger=logger):
        logger.warning('Insufficient permissions, exit.')
        sys.exit(1)

    if not check_disk_usage(locations, logger=logger):
        logger.warning('Not enough free space, exit.')
        sys.exit(1)

    logger.info('Debug mode: %s' % str(settings['debug']))
    logger.info('Known OJS versions:')
    for version_number, instance in updater.iter_versions():
        logger.info(
            '-> %s (%s; %s)',
            version_number,
            instance.version_info['date'],
            instance.base_folder
        )
    logger.info('Newest OJS: %s', updater.get_newest_version())
    journal = OJSInstance(settings.args.folder, settings=settings, logger=logger)
    locations = (str(journal.base_folder),)
    if not check_permissions(locations, mode=os.W_OK, logger=logger):
        logger.warning('Insufficient permissions, exit.')
        sys.exit(1)

    logger.info('Journal folder: %s', settings.args.folder)
    logger.info('OJS Version: %s', journal.version_info['release'])
    # TODO: Option to specify target version
    updater.update(journal)
    logger.info('Done.')


def backup(settings, logger):
    """ Backup both folder and database of the given journal instances. """
    if logger is None:
        raise NotImplementedError
    # Are all reading/writing permissions given?
    locations = (settings['temp_dir'],
                 settings['ojs_backup_folder'],
                 settings['ojs_backup_db'],
                 settings['ojs_backup_www']
                 )
    if not check_permissions(locations, logger=logger):
        logger.warning('Insufficient permissions, exit.')
        sys.exit(1)
    if not check_disk_usage(locations, logger=logger):
        logger.warning('Not enough free space, exit.')
        sys.exit(1)
    logger.info('Debug mode: %s', settings['debug'])

    journal = OJSInstance(settings.args.folder, settings=settings, logger=logger)
    locations = (str(journal.base_folder),)
    if not check_permissions(locations, mode=os.R_OK, logger=logger):
        logger.warning('Insufficient permissions, exit.')
        sys.exit(1)

    logger.info('Journal folder: %s', settings.args.folder)

    # Run!
    journal.backup()


def main():
    """Where the magic begins."""
    if os.name not in SUPPORTED_PLATFORMS:
        raise NotImplementedError(f'Platform not supported: {os.name}')
    logger = setup_logging()
    settings = get_settings()
    # drop privileges
    logger.info('Current directory: %s', os.getcwd())
    with ZCLock(settings['run_dir'], filename=get_script_name(__file__)):
        if not settings.args.permissive:
            drop_privileges(settings['owner'], settings['group'], logger=logger)
        if settings.args.backup:
            backup(settings, logger)
        else:
            update(settings, logger)

    logger.info('Done.')


if __name__ == '__main__':
    main()
