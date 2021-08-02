import configparser
import logging
from pathlib import Path
from unittest import mock

import pytest

from tests.conftest import mock_journal_path, test_folder_path

logger = logging.getLogger()

# TODO: Although the function dump_database() suggests that one can change the backup suffix, this is not completely
#       implemented and probably will cause errors/problems.
# TODO: If the backup suffix is another than .bz2, the rollback after an exception will not work! This has to be
#       implemented!
# TODO: There should be a check, when getting data from DUMPERS, that there is a corresponding entry in DATABASE_IMPORT.
#       Otherwise, the rollback may fail (e.g. because of a typo).
# TODO: To access the database importer and exporter functions (i.e. DUMPERS and DATABASE_IMPORT),
#       there should be a function an not a direct call to the dicts!
# TODO: The rollback will fail on Windows machines, because there is no '/tmp/' directory for the backups to be
#       extracted to. This path should either be customizable in the settings or set to a path that is guaranteed
#       to exists (i.e. a path within the ojs_updater).
# TODO: As another precaution, it should be checked that the backup folder for the database and for the OJS directory
#       are not the same. Otherwise, one backup overwrites the other!
# TODO: Implement settings['temp_dir'] in tests instead of hardcoded '/tmp'

class TestOJSInstance:
    @pytest.fixture(autouse=True)
    def maintain_config_file_consistency(self, journal_instance_to_upgrade):
        config_file_path = journal_instance_to_upgrade.base_folder / 'config.inc.php'
        config_parser = configparser.ConfigParser()
        config_parser.read(config_file_path)

        yield

        with open(config_file_path, 'w') as configfile:
            config_parser.write(configfile)

    @pytest.fixture(autouse=True)
    def assert_debug_is_off(self, journal_instance_to_upgrade):
        """ Otherwise some tests may pass for the wrong reason. """
        assert journal_instance_to_upgrade.settings['debug'] is False

    def test_reload_config(self, journal_instance_to_upgrade):
        assert journal_instance_to_upgrade.config['database']['host'] == 'localhost'

        modify_settings_in_journal_config_file(journal_instance_to_upgrade.base_folder, 'database', 'host', '127.0.0.1')
        journal_instance_to_upgrade.reload_config()

        assert journal_instance_to_upgrade.config['database']['host'] == '127.0.0.1'

    def test_is_installed(self, journal_instance_to_upgrade):
        assert journal_instance_to_upgrade.is_installed() is True

        modify_settings_in_journal_config_file(journal_instance_to_upgrade.base_folder, 'general', 'installed', 'Off')
        journal_instance_to_upgrade.reload_config()

        assert journal_instance_to_upgrade.is_installed() is False

    def test_toggle_installed(self, journal_instance_to_upgrade):
        comment_string = 'This is some comment that should be preserved!'
        assert journal_instance_to_upgrade.is_installed() is True
        add_comment_to_config_file(journal_instance_to_upgrade.base_folder, comment_string)

        journal_instance_to_upgrade.toggle_installed()

        assert journal_instance_to_upgrade.is_installed() is False

        with open(get_config_file_path(journal_instance_to_upgrade.base_folder), 'r') as configfile:
            config_file_content = configfile.read()
            assert comment_string.lower() in config_file_content
            assert 'installed = Off' in config_file_content

    def test_archive_files_destination_does_not_exist(self, journal_instance_to_upgrade):
        with pytest.raises(FileNotFoundError):
            journal_instance_to_upgrade.archive_files('does/not/exist')

    @mock.patch('shutil.make_archive', spec=True)
    def test_archive_files(self, mock_make_archive: mock.MagicMock, journal_instance_to_upgrade):
        backup_file_path = '/ojs/foo/backup/www/journal_that_needs_upgrade_20210604_1250.gz'
        mock_make_archive.return_value = backup_file_path
        journal_instance_to_upgrade.archive_files(destination='.', file_format='gz')

        mock_make_archive.assert_called_once_with(
            base_name='journal_that_needs_upgrade_20210604_1250',
            format='gz',
            root_dir=str(mock_journal_path.parent),
            base_dir='journal_that_needs_upgrade',
            dry_run=False,
            logger=journal_instance_to_upgrade.logger)

        assert journal_instance_to_upgrade.backups == {'www': backup_file_path}

    def test_dump_database_destination_does_not_exist(self, journal_instance_to_upgrade):
        with pytest.raises(FileNotFoundError):
            journal_instance_to_upgrade.dump_database(destination='does/not/exist')

    @mock.patch.dict('ojs_updater.commons.DUMPERS', {}, clear=True)
    def test_dump_database_no_database_dumping_function_available(self, journal_instance_to_upgrade):
        with pytest.raises(NotImplementedError):
            journal_instance_to_upgrade.dump_database(destination='.')

    @mock.patch('tarfile.open', spec=True)
    def test_dump_database(self, tarfile_context_manager, journal_instance_to_upgrade):
        backup_file_path = str(test_folder_path / 'journal_that_needs_upgrade_20210604_1250.tar.bz2')
        tarfile_context_manager.return_value.__enter__.return_value = mock.MagicMock()
        database_dumper_mock = mock.MagicMock(return_value=b'test')

        with mock.patch.dict('ojs_updater.commons.DUMPERS', {'mysqli': database_dumper_mock}, clear=True):
            journal_instance_to_upgrade.dump_database(destination=test_folder_path, file_format='gz')

        tarfile_context_manager.assert_called_once_with(name=str(test_folder_path / 'journal_that_needs_upgrade_20210604_1250.tar.bz2'),
                                                        mode='w:gz')

        database_dumper_mock.assert_called_once_with('ojs', 'localhost', 'ojs', 'ojspwd', mock.ANY)
        assert journal_instance_to_upgrade.backups == {'db': backup_file_path}

    def test_lock(self, journal_instance_to_upgrade):
        with journal_instance_to_upgrade.lock():
            pass

    def test_lock_with_exception_and_no_backups(self, journal_instance_to_upgrade):
        journal_instance_to_upgrade.backups = {}

        with journal_instance_to_upgrade.lock():
            raise Exception

        journal_instance_to_upgrade.logger.critical.assert_called_once()

    @mock.patch('tarfile.open', spec=True)
    @mock.patch('shutil.rmtree', spec=True)
    def test_lock_with_exception_and_rollback(self, mock_remove_directory, mock_tarfile_context_manager: mock.MagicMock,
                                              journal_instance_to_upgrade):
        journal_backup_file_path_string = '/ojs/foo/backup/db/journal_backup_20210609_0712.tar.bz2'
        db_backup_file_path_string = '/ojs/foo/backup/www/journal_backup_20210609_0712.tar.bz2'
        journal_instance_to_upgrade.backups['www'] = journal_backup_file_path_string
        journal_instance_to_upgrade.backups['db'] = db_backup_file_path_string
        mock_tarfile = mock.MagicMock()
        mock_tarfile.__iter__.return_value = iter([mock.MagicMock()])
        mock_tarfile.getnames.return_value = ['']
        mock_tarfile_context_manager.return_value.__enter__.return_value = mock_tarfile
        database_dumper_mock = mock.MagicMock(return_value=b'test')

        with mock.patch.dict('ojs_updater.commons.DATABASE_IMPORT', {'mysqli': database_dumper_mock}, clear=True):
            with journal_instance_to_upgrade.lock():
                raise Exception

        mock_tarfile_context_manager.assert_any_call(db_backup_file_path_string, mode=mock.ANY)
        mock_tarfile_context_manager.assert_any_call(journal_backup_file_path_string, mode=mock.ANY)

        mock_tarfile.extract.assert_called_once_with(mock.ANY, path='/tmp')
        mock_tarfile.extractall.assert_called_once_with(path=journal_instance_to_upgrade.base_folder.parent)
        database_dumper_mock.assert_called_once_with(Path('/tmp'), 'ojs', 'localhost', 'ojs', 'ojspwd', mock.ANY)
        mock_remove_directory.assert_called_once_with(str(journal_instance_to_upgrade.base_folder), ignore_errors=True)


def modify_settings_in_journal_config_file(journal_path: Path, section: str, key: str, value):
    config_parser = get_config_parser_for_path(journal_path)
    config_parser.set(section, key, value)
    write_to_config_file(journal_path, config_parser)


def add_comment_to_config_file(journal_path: Path, comment: str):
    comment = comment if comment.startswith(';') else f'; {comment}'
    modify_settings_in_journal_config_file(journal_path, 'general', comment, None)


def get_config_parser_for_path(journal_path):
    config_parser = configparser.ConfigParser(allow_no_value=True)
    config_file_path = get_config_file_path(journal_path)

    config_parser.read(config_file_path)

    return config_parser


def write_to_config_file(journal_path, config_parser):
    config_file_path = get_config_file_path(journal_path)

    with open(config_file_path, 'w') as configfile:
        config_parser.write(configfile)


def get_config_file_path(journal_path):
    return journal_path / 'config.inc.php'

