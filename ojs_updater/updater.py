# Copyright 2019-2021, UB JCS, Goethe University Frankfurt am Main
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


"""The updater object."""
import os
import pathlib
import shutil
from packaging import version
from .commons import is_ojs
from .ojsinstance import OJSInstance


class Updater:
    """This class implements the main updating functionality and provides a
    high level interface for managing all known ojs versions.
    """
    def __init__(self, ojs_version_folder, settings, logger=None):
        self.ojs_version_folder = pathlib.Path(ojs_version_folder)
        self.settings = settings
        if logger is None:
            raise NotImplementedError
        self.logger = logger
        if not self.ojs_version_folder.exists():
            raise FileNotFoundError('No such path: {}'.format(self.ojs_version_folder))
        self.versions = self._read_version_folder()

    def _read_version_folder(self):
        """Internal method for retrieving all the versions."""
        versions = dict()
        for item in self.ojs_version_folder.glob('*'):
            if item.is_dir():
                if is_ojs(item, self.settings['locations']):
                    instance = OJSInstance(
                        item, settings=self.settings,
                        logger=self.logger,
                        reference=True
                    )
                    versions[instance.version] = instance
        return versions

    def get_newest_version(self):
        """Return the newest known version."""
        if not self.versions:
            raise ValueError('No local ojs versions found.')
        return max(self.versions)

    def iter_versions(self):
        """Iterate over all known versions in ascending order."""
        for key, value in sorted(self.versions.items()):
            yield key, value

    @staticmethod
    def backup(journal):
        """Initiate a backup of the journal."""
        journal.backup()

    def update(self, journal, new_version=None):
        """High-level interface for updating an ojs instance to either the newest
         or a specific version."""
        # Version handling
        if not new_version:
            new_version = self.get_newest_version()
        else:
            new_version = version.Version(new_version)
        if not new_version or new_version not in self.versions:
            raise ValueError('No such version: {}.'.format(str(new_version)))
        assert isinstance(journal, OJSInstance)
        if journal.version >= new_version:
            self.logger.warning(
                'No need to update. Journal version: %s, target version: %s',
                journal.version,
                new_version
            )
            if 'force' not in self.settings:
                return
            self.logger.warning('Enforce upgrade.')
        new_instance = self.versions.get(new_version)
        if not new_instance.reference:
            raise ValueError('Instance: {} is no reference.'.format(str(new_version)))
        self.logger.info('Update started.')
        journal.backup()
        with journal.lock():
            self.logger.info('Upgrading journal folder.')
            self.upgrade_journal_folder(journal, new_instance)
            self.logger.info('Set journal to uninstalled.')
            # journal.set_config('general', 'installed', 'Off')
            # Temporary workaround
            journal.toggle_installed()
            self.logger.info('Upgrading database.')
            self.logger.info('--- PHP Output start.')
            self.upgrade_journal_database(journal)
            self.logger.info('--- PHP Output stop.')
            self.logger.info('Set journal to installed.')
            #journal.set_config('general', 'installed', 'On')
            journal.toggle_installed()

    def upgrade_journal_folder(self, journal, source):
        # TODO: This method needs reactoring!
        """ Replaces the original journal folder with the given upgraded folder.

            Raises:
                FileNotFoundError: If the given source folder or the given journal does not exists.
                In either case, nothing happens.
        """
        ojs_upgrade_folder = source.base_folder

        # Make sure that the given upgrade folder exists before doing anything stupid!
        if ojs_upgrade_folder.exists() and journal is not None:
            self.logger.info('Replacing old journal folder')
            old_journal_folder = pathlib.Path(
                '{}_{}'.format(
                    journal.base_folder,
                    self.settings['timestamp']
                )
            )

            # Rename old journal folder
            shutil.move(str(journal.base_folder), str(old_journal_folder))

            # Introduce the upgraded folder
            shutil.copytree(str(ojs_upgrade_folder), str(journal.base_folder))

            # TODO: When are we reloading the config?

            # Get public folder
            self.logger.info('Copy: "%s" to "%s"',
                             old_journal_folder/'public',
                             journal.base_folder)
            # TODO: Better handling of existing folders
            if (journal.base_folder/'public').exists():
                files = list((journal.base_folder/'public/').glob('*'))
                if len(files) > 1:
                    raise ValueError('New public folder not empty.')
                elif files[0].name != 'index.html':
                    raise ValueError('New public folder not empty.')
                else:
                    shutil.rmtree(str(journal.base_folder/'public'))

            shutil.copytree(str(old_journal_folder/'public'),
                            str(journal.base_folder/'public'))

            # Backup new config, get old
            config_file = journal.base_folder/self.settings['config_file']
            config_backup = config_file.with_suffix(
                '{}{}'.format(config_file.suffix, self.settings['suffix_new'])
                )
            self.logger.info('Rename: "%s" to "%s"', config_file, config_backup)
            shutil.move(
                str(config_file),
                str(config_backup)
                )
            self.logger.info('Copy: "%s" to "%s"',
                             str(old_journal_folder/self.settings['config_file']),
                             str(journal.base_folder))
            shutil.copy(
                str(old_journal_folder/self.settings['config_file']),
                str(journal.base_folder)
            )

            # Copy custom plugins
            plugin_path_list = []
            if 'all' in self.settings['custom_files'] and self.settings['custom_files']['all']:
                plugin_path_list += self.settings['custom_files']['all']
            if journal.name in self.settings['custom_files'] and self.settings['custom_files'][journal.name]:
                plugin_path_list += self.settings['custom_files'][journal.name]

            if plugin_path_list:
                self.logger.info('Copy custom plugins.')

                plugin_path_list = list(set(plugin_path_list))

                for folder in plugin_path_list:
                    src = old_journal_folder / folder
                    dst = journal.base_folder / folder

                    try:
                        self.logger.info('-> Copy \"{}\"'.format(src))

                        dst_bck = pathlib.Path(
                            '/'.join(dst.parts) +
                            self.settings['suffix_new']
                        )
                        copy = shutil.copy

                        if src.is_dir():
                            # Copy a directory
                            copy = shutil.copytree

                        if dst.exists():
                            shutil.move(
                                str(dst),
                                str(dst_bck)
                            )
                        elif src.is_file() and not dst.parent.exists():
                            parent_directory_path = dst.parent
                            self.logger.info('Create directory path \"{}\" for file \"{}\"'.format(
                                parent_directory_path, dst.name))
                            os.makedirs(dst.parent)

                        copy(
                            str(src),
                            str(dst)
                        )

                    except FileNotFoundError:
                        # In case a file does not exist do not interrupt but only warn
                        self.logger.warning(
                            'The file "{}" could not be found and will be skipped.'.format(src)
                        )
        else:
            if not ojs_upgrade_folder.exists():
                raise FileNotFoundError(
                    'The folder with the name or path "{}" does not exist!'.format(source.base_folder)
                )
            if journal is None:
                raise FileNotFoundError('The journal does not exist!')

    @staticmethod
    def upgrade_journal_database(journal):
        """Run the upgrade script."""
        journal.tools['upgrade.php'](args='upgrade')
