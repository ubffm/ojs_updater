from unittest import mock
from pathlib import Path

import pytest

from ojs_updater.ojsinstance import OJSInstance
from ojs_updater.settings import Settings

test_folder_path = Path(__file__).parent.absolute()
mock_journal_path = test_folder_path / 'mocks/journals/journal_that_needs_upgrade'


@pytest.fixture
def ojs_version_folder_path() -> Path:
    return test_folder_path / 'mocks/ojs_versions'


@pytest.fixture
def journal_instance_to_upgrade(mock_settings) -> OJSInstance:
    journal_path = mock_journal_path
    return OJSInstance(journal_path, settings=mock_settings, logger=mock.MagicMock())


@pytest.fixture
def mock_settings(ojs_version_folder_path) -> Settings:
    # Do not load any data from a file
    with mock.patch.object(Settings, 'load', spec=True):
        mock_settings = Settings()

    mock_settings.locations = ['dbscripts/xml/version.xml', 'config.inc.php']
    mock_settings.settings = {
        'config_file': 'config.inc.php',
        'custom_files': [],
        'debug': False,
        'group': 'bar',
        'locations': ['dbscripts/xml/version.xml', 'config.inc.php'],
        'lock_file': str(test_folder_path),
        'mysql_dump': 'mysql',
        'ojs_backup_db': '/ojs/foo/backup/db',
        'ojs_backup_folder': '/ojs/foo/backup',
        'ojs_backup_www': '/ojs/foo/backup/www',
        'ojs_version_folder': str(ojs_version_folder_path),
        'owner': 'foo',
        'suffix_new': '.OJSNEW',
        'timestamp': '20210604_1250',  # In the normal process, this variable is set by the Settings object
        'timestamp_format': '%Y%m%d_%H%M',
        'version_file': 'dbscripts/xml/version.xml',
        'temp_dir': '/tmp',
        'run_dir': '/tmp'
    }

    mock_settings.args = MockArguments()
    mock_settings.args.folder = str(mock_journal_path)

    return mock_settings


class MockArguments:
    def __init__(self):
        self.folder = None
