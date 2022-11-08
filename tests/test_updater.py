import errno
import logging
import os
import shutil
from pathlib import Path
from unittest import mock

import pytest
from checksumdir import dirhash
from packaging.version import Version

from ojs_updater.ojsinstance import OJSInstance
from ojs_updater.updater import Updater
from tests.conftest import test_folder_path

# TODO: Run tests with logger = None -> Fails currently! Same for OJSInstance!
# TODO: Refactor Updater.update -> Too big -> Split! Same applies for Updater.upgrade_journal_folder
# TODO: To force a downgrade, the parameter 'force' only needs to be present in the 'settings'.
#  But what if it was set in the config file to 'False'?
# TODO: The parameter 'force' should be renamed to 'force_downgrade' or similar! At some point a parameter 'force' may
#  appear in the OJS config file, which would be bad.
# DONE: Pytest gives a warning that logger.warn is deprecated. -> Change to logger.warning
# TODO: The key 'custom_files' has to be set. This should be optional!


@pytest.fixture
def updater(mock_settings, ojs_version_folder_path) -> Updater:
    logger = logging.getLogger()
    updater = Updater(str(ojs_version_folder_path), mock_settings, logger)

    return updater


@pytest.fixture
def add_empty_file_to_directory(request):
    """ Adds a file to a given directory and removes it after the scope ends. """
    file_path = test_folder_path / request.param
    if file_path.exists():
        raise FileExistsError(f'The given file name already exists in "{request.directory_path}"!')

    with open(file_path, 'w') as ifile:
        pass

    yield

    os.remove(file_path)


custom_files_config = [
    (
        {
            'journal_that_needs_upgrade': [
                'plugins/generic/plugin1/', 'plugins/generic/plugin2', 'plugins/generic/theme.php']
        },
        {'plugins/generic/plugin1/', 'plugins/generic/plugin2', 'plugins/generic/theme.php'},   # expected
        {'plugins/generic/plugin3/'}                                                            # not expected
    ),
    (
        {
            'journal_that_needs_upgrade': ['plugins/generic/plugin2'],
            'all': ['plugins/generic/theme.php', 'plugins/generic/plugin1/']
        },
        {'plugins/generic/plugin1/', 'plugins/generic/plugin2', 'plugins/generic/theme.php'},
        {'plugins/generic/plugin3/'}
    ),
    (
        {'all': ['plugins/generic/theme.php', 'plugins/generic/plugin1/']},
        {'plugins/generic/plugin1/', 'plugins/generic/theme.php'},
        {'plugins/generic/plugin3/', 'plugins/generic/plugin2'}
    )
]


class TestUpdater:
    def test_get_newest_version(self, updater):
        newest_version = updater.get_newest_version()
        assert newest_version == Version('3.3.0.1')

    def test_read_version_folder(self, updater):
        available_ojs_versions = updater._read_version_folder()
        assert len(available_ojs_versions) == 3
        assert set(available_ojs_versions.keys()) == {Version('2.4.8'), Version('3.3.0.1'), Version('3.3.0.0')}
        assert all(isinstance(ojs_instance, OJSInstance) for ojs_instance in available_ojs_versions.values())

    def test_upgrade_to_non_available_ojs_version(self, updater, journal_instance_to_upgrade):
        with pytest.raises(ValueError):
            updater.update(journal_instance_to_upgrade, new_version='1.2.3.4')

    def test_journal_folder_does_not_exist(self, updater, journal_instance_to_upgrade):
        with pytest.raises(AttributeError):
            updater.upgrade_journal_folder(journal_instance_to_upgrade, None)

        with pytest.raises(AttributeError):
            updater.upgrade_journal_folder(None, None)

        journal_instance_to_upgrade.base_folder = journal_instance_to_upgrade.base_folder.parent / 'foo'
        ojs_version_to_install = get_update_instance(updater)

        with pytest.raises(FileNotFoundError):
            updater.upgrade_journal_folder(journal_instance_to_upgrade, ojs_version_to_install)

        with pytest.raises(FileNotFoundError):
            updater.upgrade_journal_folder(None, ojs_version_to_install)


@mock.patch.object(OJSInstance, 'backup')
@mock.patch.object(Updater, 'upgrade_journal_folder')
@mock.patch.object(Updater, 'upgrade_journal_database')
class TestUpdating:
    @pytest.fixture(autouse=True)
    def maintain_ojs_test_config_file_consistency(self, updater):
        """ Guarantees that the config files are unchanged after a test.
            This applies even if the tests fails or raises an exception. Hence, this fixture is called before
             and after EVERY test.
        """
        ojs_instances = updater.versions
        config_file_contents = {version: read_ojs_config_file_from_journal(ojs_instance)
                                for version, ojs_instance in ojs_instances.items()}

        yield  # Run test

        for version, ojs_instance in ojs_instances.items():
            config_file_content = config_file_contents[version]
            write_ojs_config_file_from_journal(ojs_instance, config_file_content)

    @pytest.mark.parametrize(['new_version', 'expected_version'], [(None, '3.3.0.1'), ('3.3.0.0', '3.3.0.0')])
    def test_update_journal(self, upgrade_db_mock, upgrade_folder_mock, backup_mock,
                            updater, journal_instance_to_upgrade, new_version, expected_version):
        assert check_journal_config_for_setting(journal_instance_to_upgrade, 'installed', 'on')
        updater.update(journal_instance_to_upgrade, new_version)
        assert check_journal_config_for_setting(journal_instance_to_upgrade, 'installed', 'on')

        backup_mock.assert_called()
        upgrade_folder_mock.assert_called()
        upgrade_db_mock.assert_called()

        assert upgrade_folder_mock.call_args[0][1].version == Version(expected_version)

    def test_force_update_to_lower_version(self, upgrade_db_mock, upgrade_folder_mock, backup_mock, updater):
        journal_to_update = get_update_instance(updater, version='3.3.0.1')

        updater.update(journal_to_update, new_version='3.3.0.0')
        upgrade_db_mock.assert_not_called()
        upgrade_folder_mock.assert_not_called()
        backup_mock.assert_not_called()

        updater.settings.settings['force'] = True
        updater.update(journal_to_update, new_version='3.3.0.0')
        upgrade_db_mock.assert_called()
        upgrade_folder_mock.assert_called()
        backup_mock.assert_called()

        assert upgrade_folder_mock.call_args[0][1].version == Version('3.3.0.0')


class TestJournalFolderUpgrading:
    OJS_VERSIONS_BACKUP_PATH = Path(__file__).parent.absolute() / 'mocks/ojs_versions_backup'

    @pytest.fixture(scope='class', autouse=True)
    def cleanup(self):
        """ Cleans the test directory after all tests in this class ran. """

        yield

        if self.OJS_VERSIONS_BACKUP_PATH.exists():
            shutil.rmtree(self.OJS_VERSIONS_BACKUP_PATH)

    @pytest.fixture(autouse=True)
    def maintain_ojs_version_folder_consistency(self):
        ojs_versions_backup_path = self.OJS_VERSIONS_BACKUP_PATH
        path_to_be_backuped = Path(__file__).parent.absolute() / 'mocks/journals'

        if not ojs_versions_backup_path.exists():
            copy_directory_and_files_recursively(path_to_be_backuped, ojs_versions_backup_path)
        ojs_versions_hash_before_test = dirhash(path_to_be_backuped)

        yield

        ojs_versions_hash_after_test = dirhash(path_to_be_backuped)

        if ojs_versions_hash_before_test != ojs_versions_hash_after_test:
            replace_ojs_versions_folder_with_backup(path_to_be_backuped, ojs_versions_backup_path)

    def test_upgrade_journal_folder(self, updater, journal_instance_to_upgrade):
        ojs_version_to_install = get_update_instance(updater)

        journal_base_path = journal_instance_to_upgrade.base_folder
        journal_version_file = journal_base_path / 'dbscripts/xml/version.xml'
        assert_file_not_exists(journal_base_path / 'public/index.html')
        assert_string_is_in_file_content('<release>2.4.8</release>', journal_version_file)

        updater.upgrade_journal_folder(journal_instance_to_upgrade, ojs_version_to_install)

        assert_is_upgraded_journal(journal_base_path)
        assert_file_not_exists(journal_base_path / 'public/index.html')
        assert_file_exists(journal_base_path / 'public/test.txt')
        assert_file_exists(f'{journal_base_path}_20210604_1250')

    @pytest.mark.parametrize(['custom_files_settings', 'expected_files', 'not_expected_files'], custom_files_config)
    def test_migration_of_custom_plugins(self, updater, journal_instance_to_upgrade, custom_files_settings,
                                         expected_files, not_expected_files):
        updater.settings.settings['custom_files'] = custom_files_settings
        ojs_version_to_install = get_update_instance(updater)

        journal_base_path = journal_instance_to_upgrade.base_folder
        journal_plugin_path = journal_base_path / 'plugins/generic'

        assert_file_exists(journal_plugin_path / 'plugin1')
        assert_file_exists(journal_plugin_path / 'plugin2')
        assert_file_exists(journal_plugin_path / 'plugin3')
        assert_file_exists(journal_plugin_path / 'theme.php')

        updater.upgrade_journal_folder(journal_instance_to_upgrade, ojs_version_to_install)

        assert_is_upgraded_journal(journal_base_path)

        assert_files_exists(expected_files, journal_base_path)
        assert_files_not_exist(not_expected_files, journal_base_path)

    @pytest.mark.parametrize(['file_to_migrate', 'expected_files_in_upgraded_journal'],
                             [('plugins/generic/theme.php', {'plugins/generic/theme.php'}),
                              ('plugins/generic/another-theme.php', {'plugins/generic/another-theme.php',
                                                                     'plugins/generic/another-theme.php.OJSNEW'})
                              ])
    def test_migrate_single_file(self, updater, journal_instance_to_upgrade, file_to_migrate,
                                 expected_files_in_upgraded_journal):
        updater.settings.settings['custom_files'] = {'journal_that_needs_upgrade': [file_to_migrate]}
        ojs_version_to_install = get_update_instance(updater)

        journal_base_path = journal_instance_to_upgrade.base_folder
        file_path_to_migrate = journal_base_path / file_to_migrate
        assert_file_exists(file_path_to_migrate)

        updater.upgrade_journal_folder(journal_instance_to_upgrade, ojs_version_to_install)

        assert_is_upgraded_journal(journal_base_path)
        assert_files_exists(expected_files_in_upgraded_journal, journal_base_path)

    @pytest.mark.parametrize('add_empty_file_to_directory',
                             ['mocks/ojs_versions/valid_version_folder_3_3_0_1/public/should-not-be-there.txt'],
                             indirect=True)
    def test_copy_public_folder(self, updater, journal_instance_to_upgrade, add_empty_file_to_directory):
        ojs_version_to_install = get_update_instance(updater)

        with pytest.raises(ValueError):
            updater.upgrade_journal_folder(journal_instance_to_upgrade, ojs_version_to_install)


def assert_files_exists(list_of_files: set, base_path: str):
    base_path = Path(base_path)
    for expected_file in list_of_files:
        assert_file_exists(base_path / expected_file)


def assert_file_exists(file_path: str, negate: bool = False):
    file_path = Path(file_path)

    if negate:
        result = not file_path.exists()
    else:
        result = file_path.exists()

    assert result


def assert_files_not_exist(list_of_files: set, base_path: str):
    base_path = Path(base_path)
    for not_expected_file in list_of_files:
        assert_file_not_exists(base_path / not_expected_file)


def assert_file_not_exists(file_path: str):
    assert_file_exists(file_path, negate=True)


def assert_string_is_in_file_content(string_to_check: str, file_path: str):
    with open(str(file_path), 'r') as in_file:
        file_content = in_file.read()

    assert string_to_check in file_content


def assert_is_upgraded_journal(journal_path: Path, expected_version='3.3.0.1'):
    assert_file_exists(str(journal_path / 'config.inc.php.OJSNEW'))
    assert_string_is_in_file_content(f'<release>{expected_version}</release>',
                                     str(journal_path / 'dbscripts/xml/version.xml'))


def check_journal_config_for_setting(journal_instance: OJSInstance, setting_name: str, expected_value: str):
    config_file_content = read_ojs_config_file_from_journal(journal_instance)
    return f'{setting_name.lower()} = {expected_value.lower()}' in config_file_content.lower()


def read_ojs_config_file_from_journal(journal_instance) -> str:
    with open(str(journal_instance.base_folder / journal_instance.settings['config_file']), 'r') as in_file:
        file_content = in_file.read()

    return file_content


def write_ojs_config_file_from_journal(journal_instance, content):
    with open(str(journal_instance.base_folder / journal_instance.settings['config_file']), 'w') as out_file:
        out_file.write(content)


def get_update_instance(updater, version: str = None):
    version = Version('3.3.0.1') if version is None else Version(version)
    journal = updater.versions[version]
    journal.logger = logging.getLogger()

    return journal


def copy_directory_and_files_recursively(source, destination):
    try:
        shutil.copytree(source, destination)
    except OSError as err:
        # error caused if the source was not a directory
        if err.errno == errno.ENOTDIR:
            shutil.copy2(source, destination)
        else:
            print("Error: % s" % err)


def replace_ojs_versions_folder_with_backup(ojs_versions_folder_path, backup_path):
    path_to_remove = str(ojs_versions_folder_path)
    if backup_path.exists():
        shutil.rmtree(str(path_to_remove))
        os.rename(str(backup_path), str(path_to_remove))
    else:
        raise ValueError(f'The given file path {ojs_versions_folder_path} will NOT be removed!')
