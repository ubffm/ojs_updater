# Copyright 2019-2021, UB JCS, Goethe University Frankfurt am Main
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


"""Shared functions."""
import sys
import os
import pathlib
import grp
import pwd
import shutil
import subprocess
import tempfile
import zc.lockfile


try:
    from lxml import etree as et
except ImportError:
    from xml.etree import ElementTree as et

from .settings import get_settings


class UpdateError(Exception):
    """Update Exception."""
    pass


def check_permissions(locations, logger=None, mode=os.F_OK | os.R_OK | os.W_OK):
    """Check all permissions at the given locations."""
    for location in locations:
        allowed = os.access(location, mode)
        if logger is not None:
            logger.info('Check permissions (%s) for "%s"\t\t[%s]',
                        mode,
                        location,
                        {True: 'Ok', False: 'Not okay'}[allowed]
                        )
        if not allowed:
            return False
    return True


def check_disk_usage(locations, logger=None, minimum=10**9):
    """Check, if there is enough free disk space at each location.
    (default=1gb/10**9 bytes.)"""
    for location in locations:
        if shutil.disk_usage(location).free <= minimum:
            if logger is not None:
                logger.warning('Insufficient free disk space at %s', location)
            return False
    return True


def drop_privileges(owner, group, logger=None):
    """Adjust privileges."""
    # TODO: set umask
    # TODO: Make it 'sudo-aware'
    if not os.geteuid() == 0 or not os.getegid() == 0:
        print('Program has to run as root.')
        sys.exit(1)
    owner_info, group_info = get_system_data_on_user_and_group(owner, group)
    if logger is not None:
        logger.info('Change user to: %s, change group to: %s', owner, group)
    set_user_and_group_for_running_process(owner_info, group_info)


def get_system_data_on_user_and_group(user_name: str, group_name: str):
    """Get user and group."""
    return pwd.getpwnam(user_name), grp.getgrnam(group_name)


def set_user_and_group_for_running_process(user_data, group_data):
    """Set user and group."""
    os.setgid(group_data.gr_gid)
    os.setuid(user_data.pw_uid)


def get_script_name(script=__file__, no_ext=True):
    """The script's name."""
    tmp = pathlib.Path(script)
    if no_ext:
        tmp = tmp.stem
        assert tmp
    else:
        tmp = tmp.name
    return tmp


def is_ojs(folder, expected_files):
    """ Check if a certain folder looks as if it contains an ojs instance.
        :param folder: The path to the potential OJS folder.
        :param expected_files: A container holding the files that are expected in an OJS folder.

        This is currently achieved by looking for certain characteristic
        files and folders.
    """
    folder = pathlib.Path(folder)
    return all((folder / expected_file).exists() for expected_file in expected_files)


def is_ojs_plugin(folder):
    """Check if a folder looks like it contains an ojs plugin."""
    folder = pathlib.Path(folder)
    locations = [
        'version.xml'
    ]
    return all((folder / location).exists() for location in locations)


def read_ojs_version_file(ojs_version_xml_file_path=None):
    """ Read an ojs version.xml file and return its contents as a dictionary. """
    file = get_settings()['version_file'] if ojs_version_xml_file_path is None \
        else ojs_version_xml_file_path
    tree = et.parse(str(file))
    result = dict()
    for item in tree.getroot():
        tag, content = item.tag, item.text
        if tag == "patch":
            continue
        if tag in result:
            raise ValueError('Malformed version file')
        result[tag] = content
    return result


def mysql_dump(database, host, username, password, logger=None):
    """ Create a dump of a mysql database.
        Returns the dump as a string.
    """
    settings = get_settings()
    with tempfile.NamedTemporaryFile('w') as option_file:
        print('[client]', file=option_file)
        print('password', password, file=option_file, sep="=")
        option_file.flush()
        args = [str(settings['mysql_dump']),
                f'--defaults-extra-file={option_file.name}',
                '--single-transaction',
                '--user', username,
                '--host', host,
                database]

        try:
            return subprocess.check_output(args)
        except subprocess.CalledProcessError as error:
            if logger is not None:
                logger.warning('The OJS database could not be backup-ed!')
            raise OSError('Connection to the database failed!') from error


def mysql_restore(data, database, host, username, password, logger=None):
    """ Drops the 'old' database and reimports the journal backup into
     the database."""
    # TODO: resolve path to mysql
    with tempfile.NamedTemporaryFile('w') as option_file:
        print('[client]', file=option_file)
        print('password', password, file=option_file, sep='=')
        option_file.flush()
        args_drop = ['mysql',
                     f'--defaults-extra-file={option_file.name}',
                     '--host', host,
                     '--user', username,
                     '-e',
                     'DROP DATABASE {0}; CREATE DATABASE {0};'.format(database)]

        args_import = ['mysql',
                       f'--defaults-extra-file={option_file.name}',
                       '--host', host,
                       '--user', username,
                       '-e',
                       'USE {}; SOURCE {};'.format(database, data)]

        try:
            subprocess.check_output(args_drop)
            subprocess.check_output(args_import)
        except subprocess.CalledProcessError as error:
            if logger is not None:
                logger.warning('The database reimport failed!')
            raise OSError('Connection to the database failed!') from error


DUMPERS = {
    'mysql': mysql_dump,
    'mysqli': mysql_dump
}

DATABASE_IMPORT = {
    'mysql': mysql_restore,
    'mysqli': mysql_restore
}


def run_php(cmd, args, interpreter=None):
    """Run a php script."""
    settings = get_settings()
    php_interpreter = settings['php_interpreter'] if interpreter is None else interpreter
    result = subprocess.check_call([str(php_interpreter), cmd, args], stderr=subprocess.STDOUT)
    return result


class ZCLock:
    """This class implements a  simple file based lock."""
    def __init__(self, directory, filename=get_script_name()):
        self.path = pathlib.Path(directory) / filename
        self._lock = None

    def __enter__(self):
        self.acquire()

    def __exit__(self, *args):
        self.release()

    def __str__(self):
        return str(self.path)

    def acquire(self):
        """Acquire a lock."""
        self._lock = zc.lockfile.LockFile(str(self.path))

    def release(self):
        """Release the lock."""
        if self._lock is None:
            raise ValueError('There is no lock to be released for: {}'.format(self.path))
        self._lock.close()
