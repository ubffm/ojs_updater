# Copyright 2019-2021, UB JCS, Goethe University Frankfurt am Main
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


"""The journal object."""
import re
import configparser
import tarfile
import shutil
import pathlib
import tempfile
from io import BytesIO
from functools import partial
from contextlib import contextmanager
from packaging import version
from .commons import is_ojs, read_ojs_version_file, run_php, DUMPERS, DATABASE_IMPORT

CONFIG_PATTERN = re.compile(r'^\s*;\s*')


class OJSInstance:
    """One single OJS instance, defined by a folder.

        Attributes:
            base_folder (Path): The path to the given journal folder
            logger (Logger):    The logger, should be obvious
            [...]
            backup_file_name (str): The name used for all backup files.
            backups (dict): A dictionary, containing the paths to the created backups.
    """

    def __init__(self, folder, settings, logger=None, strict=True, reference=False):
        """reference: Journal is merely a non-installed copy of ojs (e.g. a freshly
        downloaded and unzipped one.)
        """
        self.base_folder = pathlib.Path(folder)
        self.settings = settings
        if strict:
            if not is_ojs(folder, settings['locations']):
                raise ValueError('No OJS instance.')
        if logger is None:
            # TODO: implement proper instantiation of a logger if none is passed
            raise NotImplementedError
            # self.logger = logging.getLogger(__name__)
            # self.logger.add_handler(logging.NullHandler())
        else:
            self.logger = logger
        self.version_info = read_ojs_version_file(
            (self.base_folder / str(self.settings['version_file']))
        )
        self.config = None
        self.reload_config()
        self.reference = reference
        self.backup_file_name = self.base_folder.name
        self.backups = {}
        self.tools = self._get_tools()
        self.version = version.Version(self.version_info['release'])
        self.name = self.base_folder.name

    def _get_tools(self, extensions=('.php',)):
        """Get the php tools inside of OJS."""
        tools_path = self.base_folder / 'tools'
        tools = dict()
        for item in tools_path.glob('*'):
            if item.name.endswith(extensions):
                tools[item.name] = partial(run_php, cmd=str(item))
        return tools

    def reload_config(self):
        """(re)load the config file."""
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read(
            str(self.base_folder / str(self.settings['config_file']))
        )
        try:
            self.config['database']['host'] = self.config['database']['host'].strip('"')
        except KeyError:
            self.logger.warning('No host.')
            raise ValueError from KeyError

    def is_installed(self):
        """Check if the ojs instance is installed as per config file."""
        return self.config['general']['installed'].lower() == 'on'

    def set_config(self, section, key, value):
        """Set a specific config value and write it back to the file."""
        if not self.config:
            raise ValueError('No configuration.')
        self.config[section][key] = value
        # config parser doesn't preserve comments (and configobj currently doesn't
        # allow for ";" comment markers. Thus, the following hack is needed.
        with open(str(self.base_folder / self.settings['config_file']), 'w') as file_handle:
            self.config.write(file_handle)
        self.reload_config()

    def toggle_installed(self):
        """This is a work-around to toggle the installed setting since
        configparser swallows comments."""
        # THIS METHOD IS VERY (!) CRAPPY...
        with tempfile.TemporaryFile('w+') as out_file:
            with open(str(self.base_folder / self.settings['config_file']), 'r') as in_file:
                for line in in_file:
                    tmp_line = line
                    if re.match(r'^\s*installed\s*=\s*on', line.lower()):
                        tmp_line = 'installed = Off\n'
                    elif re.match(r'^\s*installed\s*=\s*off', line.lower()):
                        tmp_line = 'installed = On\n'
                    out_file.write(tmp_line)
            out_file.seek(0)
            with open(str(self.base_folder / self.settings['config_file']), 'w') as in_file:
                shutil.copyfileobj(out_file, in_file)
        self.reload_config()

    def backup(self):
        """High level interface for doing a full backup of an ojs instance."""
        self.logger.info('Create backup.')
        self.archive_files(self.settings['ojs_backup_www'])
        self.dump_database(self.settings['ojs_backup_db'])

    def archive_files(self, destination, file_format='bztar'):
        """Compile all files of an ojs instance into a compressed tar ball
        and save it to destination."""
        destination = pathlib.Path(destination)
        if not destination.exists():
            raise FileNotFoundError('No such folder: {}'.format(destination))
        backup_file = "{}_{}".format(
            str(destination / self.backup_file_name),
            self.settings['timestamp']
        )
        self.logger.info('Backup archive: %s', backup_file)
        backup_file_name = shutil.make_archive(
            base_name=str(backup_file),
            format=file_format,
            root_dir=str(self.base_folder.parent),
            base_dir=self.base_folder.name,
            dry_run=self.settings['debug'],
            logger=self.logger
            )

        self.backups[pathlib.Path(self.settings['ojs_backup_www']).name] = str(
            destination / backup_file_name
        )
        self.logger.info('Backup created.')

    def dump_database(self, destination, file_format='bz2'):
        """ Create a database dump to destination, by using the database
            information stated in the config file.

            Args:
                destination (str): String of the destination path.
                file_format (str): Compression format for the dump.
                    Formats available are:
                        'gz':   gzip compressed
                        'bz2':  bzip2 compressed
                        'xz': 	lzma compressed
        """

        # Check if the destination directory exists
        destination = pathlib.Path(destination)
        if not destination.exists():
            raise FileNotFoundError('No such folder: {}'.format(destination))

        # Create dump
        driver = self.config['database']['driver']
        self.logger.info('Creating database backup with driver: %s', driver)
        try:
            dumper = DUMPERS[driver]
        except KeyError:
            raise NotImplementedError('No dumper for: {}'.format(driver)) from KeyError
        dump = dumper(
            self.config['database']['name'],
            self.config['database']['host'],
            self.config['database']['username'],
            self.config['database']['password'],
            self.logger
        )

        # Write dump to destination...
        backup_file_name = '{}_{}.tar.bz2'.format(
            self.backup_file_name,
            self.settings['timestamp']
        )
        tar_file_path = destination / backup_file_name

        self.logger.info('Writing database dump to %s', tar_file_path)

        # ... in a compressed tar file
        if not self.settings['debug']:
            mode = 'w:%s' % file_format
            with tarfile.open(name=str(tar_file_path), mode=mode) as tar:
                file = BytesIO(dump)
                info = tarfile.TarInfo(
                    name='{}_{}.sql'.format(
                        self.config['database']['name'],
                        self.settings['timestamp']
                    )
                )
                info.size = len(dump)
                tar.addfile(tarinfo=info, fileobj=file)

        self.backups[pathlib.Path(self.settings['ojs_backup_db']).name] = str(tar_file_path)

    def lock_website(self):
        """Manually lock an ojs instance."""
        self.logger.info('Locking website')


    def unlock_website(self):
        """Manually unlock an ojs instance."""
        self.logger.info('Unlocking website')

    def _rewind(self):
        """Rewind a journal back to it's initial state after a failed update attempt."""
        if not self.backups:
            self.logger.warning(
                'No backup file references found!\nProbably you are screwed!')
        else:
            self.logger.info('Rewinding to original state')

            db_backup = self.backups[pathlib.Path(self.settings['ojs_backup_db']).name]
            www_backup = self.backups[pathlib.Path(self.settings['ojs_backup_www']).name]

            # Restore database
            db_data = pathlib.Path('/tmp/')
            if db_backup.endswith('.bz2'):
                with tarfile.open(str(db_backup), mode='r:bz2') as db_tar:
                    # actually there is only one file, but this is more convenient
                    # TODO: This could iterate multiple files, but the next if-statement
                    #  only checks for the existence of one of these files. Is this safe?
                    for db in db_tar:
                        db_tar.extract(db, path=str(db_data))
                        db_data = db_data / db_tar.getnames()[0]

            if db_data.exists():
                self.logger.info('Resetting database...')

                driver = self.config['database']['driver']
                try:
                    restore_func = DATABASE_IMPORT[driver]
                except KeyError:
                    raise NotImplementedError(
                        'No database import function for: {}'.format(
                            driver
                        )
                    ) from KeyError

                restore_func(db_data,
                             self.config['database']['name'],
                             self.config['database']['host'],
                             self.config['database']['username'],
                             self.config['database']['password'],
                             self.logger
                             )

            # Restore journal folder
            # Remove the existing journal folder, if there is one
            self.logger.info('Resetting journal folder')
            if self.base_folder.exists():
                shutil.rmtree(str(self.base_folder), ignore_errors=True)

            if www_backup.endswith('.bz2'):
                with tarfile.open(str(www_backup), mode='r:bz2') as www_tar:
                    self.logger.info('Extract to: %s', self.base_folder.parent)
                    www_tar.extractall(path=self.base_folder.parent)

    @contextmanager
    def lock(self):
        """OJS locking via a context manager. That's the prefered way."""
        # TODO: This needs refactoring.
        try:
            self.lock_website()
            yield
            self.unlock_website()
        except Exception as error:
            self.logger.critical(
                'While upgrading the journal %s a critical error occurred with '
                'the message:\n\t %s', self.base_folder, error)
            if not self.settings['debug']:
                # Rewind the journal to the original state
                self._rewind()
