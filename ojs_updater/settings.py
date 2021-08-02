# Copyright 2019-2021, UB JCS, Goethe University Frankfurt am Main
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


"""Settings"""
import os
import argparse
import pathlib
import shutil
import datetime
from tempfile import gettempdir
import yaml
from schema import Schema, Optional, Or


SETTING_FILENAME = 'ojs_updater_settings.yml'
SETTING_SCHEMA = Schema(
            {
                'config_file': str,
                'custom_files': {
                    Optional(str): Or([str], None)
                },
                'debug': bool,
                'group': str,
                'owner': str,
                'locations': [str],
                Optional('mysql_dump'): str,
                'ojs_backup_db': str,
                'ojs_backup_folder': str,
                'ojs_backup_www': str,
                'ojs_version_folder': str,
                Optional('php_interpreter'): str,
                'run_dir': str,
                'suffix_new': str,
                'temp_dir': str,
                'timestamp': str,
                'timestamp_format': str,
                'version_file': str
            })

LOCK_DIRS = ('/run/lock/',
        '/var/lock/',
        '/run',
        '/var/run',
        '/tmp',
        '/dev/shm'
        )

## This is not the best place for it, but it's here for now to avoid circular imports
def _get_lock_dir():
    """Get an appropriate dir of the lock."""
    lockdir = None
    for folder in LOCK_DIRS:
        if os.path.exists(folder):
            lockdir = folder
            break
    def inner():
        return lockdir
    return inner


get_lock_dir = _get_lock_dir()


def parse_args():
    """CLI interface."""
    parser = argparse.ArgumentParser(description="OJS update helper.")
    parser.add_argument(
        'folder',
        help="Path to the OJS instance to be upgraded."
    )
    parser.add_argument(
        '--permissive',
        action='store_true',
        help='If set, root privileges are not dropped (no warranty; use with caution).'
    )
    # TODO: add dry-run/test parameter
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode.'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Enforce upgrade, even if the target OJS version is equal. '
             'This skips all version number checks.'
    )
    parser.add_argument(
        '-o', '--owner',
        type=str,
        help='After dropping root privileges, run as this user. '
             '(This should usually be the web server user).'
    )
    parser.add_argument(
        '-g', '--group',
        type=str,
        help='After dropping root privileges, run with this group. '
        '(This should usually be the web server group).'
    )

    # Backup switch
    parser.add_argument(
        '--backup',
        action='store_true',
        help='Run only (!) the backup routine.'
    )

    return parser.parse_args()


class Settings:
    """Gather settings."""
    def __init__(self, args_func=None, setting_filename=SETTING_FILENAME):
        self.file_name = setting_filename
        self.locations = [os.getcwd()]
        try:
            file_path = pathlib.Path(__file__)
            self.locations.append(str(file_path.resolve().parent))
        except NameError:
            pass
        self.locations.extend(['/usr/local/etc', '/etc'])
        self.settings_file = None
        self.settings = self.load()
        if args_func is not None:
            self.args = args_func()
            self.apply_args()
        else:
            self.args = None

    def __contains__(self, key):
        return key in self.settings

    def __getitem__(self, key):
        return self.settings[key]

    def apply_args(self):
        """Override config options with cli parameters."""
        for item in vars(self.args):
            value = getattr(self.args, item)
            if value:
                self.settings[item] = value

    def load(self):
        """Load the settings."""
        settings_file = None
        for location in self.locations:
            path = pathlib.Path(location) / self.file_name
            if path.exists():
                settings_file = path
                break
        if settings_file is None or not settings_file:
            raise FileNotFoundError('No settings file found.')
        with open(str(settings_file)) as file_handle:
            settings = yaml.safe_load(file_handle)
        if 'mysql_dump' not in settings:
            mysql_dump_path = shutil.which('mysqldump')
            if not mysql_dump_path:
                raise FileNotFoundError("'mysqldump' could not be found.")
            settings['mysql_dump'] = mysql_dump_path
        if 'php_interpreter' not in settings:
            php_path = shutil.which('php')
            if not php_path:
                raise FileNotFoundError("'php' could not be found.")
            settings['php_interpreter'] = php_path
        settings['timestamp'] = datetime.datetime.now().strftime(settings['timestamp_format'])
        if 'temp_dir' not in settings:
            settings['temp_dir'] = gettempdir()
        if 'run_dir' not in settings:
            settings['run_dir'] = get_lock_dir()
        SETTING_SCHEMA.validate(settings)
        return settings


class SettingsCreator:
    """Create a Settings singleton that can be used throughout the code."""
    def __init__(self, **kwargs):
        self.obj = None
        self.kwargs = kwargs

    def __call__(self, **kwargs):
        if not self.obj:
            self.obj = Settings(**self.kwargs)
        return self.obj


settings_singleton = SettingsCreator(args_func=parse_args)


def get_settings():
    """Just get the settings singleton."""
    return settings_singleton()
