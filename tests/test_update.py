import logging
from typing import List
from unittest import mock

from ojs_updater.ojs_update import update, backup
from tests.conftest import mock_journal_path

import pytest
import os
logger = logging.getLogger()

# TODO: Move all precaution testing in update() to separate function!
# TODO: Check if backup() and update() can me cut down when separating the precaution testing.


@mock.patch('ojs_updater.updater.Updater.update', spec=True)
@mock.patch('ojs_updater.ojs_update.check_permissions', spec=True)
@mock.patch('ojs_updater.ojs_update.check_disk_usage', spec=True)
class TestUpdate:
    @pytest.mark.parametrize(['disk_usage_status', 'permission_check_status', 'raised_error_type'],
                             [
                                 (True, True, None), (False, True, SystemExit), (True, False, SystemExit),
                                 (False, False, SystemExit)
                             ])
    def test_simple_update(self, mock_disk_usage, mock_permission_check, mock_updater_update, mock_settings,
                           disk_usage_status, permission_check_status, raised_error_type):
        set_mock_return_values([mock_disk_usage, mock_permission_check], [disk_usage_status, permission_check_status])

        if raised_error_type is not None:
            with pytest.raises(raised_error_type):
                update(mock_settings, logger)
        else:
            update(mock_settings, logger)
            mock_updater_update.assert_called_once()
            mock_disk_usage.assert_called_once()
            mock_permission_check.assert_called()
    
    def test_journal_folder_permissions(self, mock_disk_usage, mock_permission_check,
                                        mock_updater_update, mock_settings):
        mock_disk_usage.return_value = True
        mock_permission_check.side_effect = [True, False]
        with pytest.raises(SystemExit):
            update(settings=mock_settings, logger=logger)

        mock_permission_check.assert_called()
        mock_permission_check.assert_called_with(tuple([str(mock_journal_path)]), mode=os.W_OK, logger=logger)


@mock.patch('ojs_updater.ojsinstance.OJSInstance.backup', spec=True)
@mock.patch('ojs_updater.ojs_update.check_permissions', spec=True)
@mock.patch('ojs_updater.ojs_update.check_disk_usage', spec=True)
class TestBackup:
    @pytest.mark.parametrize(['disk_usage_status', 'permission_check_status', 'raised_error_type'],
                             [
                                 (True, True, None), (False, True, SystemExit), (True, False, SystemExit),
                                 (False, False, SystemExit)
                             ])
    def test_simple_backup(self, mock_disk_usage, mock_permission_check, mock_journal_backup, mock_settings,
                           disk_usage_status, permission_check_status, raised_error_type):
        set_mock_return_values([mock_disk_usage, mock_permission_check], [disk_usage_status, permission_check_status])

        if raised_error_type is not None:
            with pytest.raises(raised_error_type):
                backup(mock_settings, logger)
        else:
            backup(mock_settings, logger)
            mock_journal_backup.assert_called_once()
            mock_disk_usage.assert_called_once()
            mock_permission_check.assert_called()

    def test_journal_folder_permissions(self, mock_disk_usage, mock_permission_check: mock.MagicMock,
                                        mock_journal_backup, mock_settings):
        mock_disk_usage.return_value = True
        mock_permission_check.side_effect = [True, False]

        with pytest.raises(SystemExit):
            backup(mock_settings, logger)

        mock_permission_check.assert_called()
        mock_permission_check.assert_called_with(tuple([str(mock_journal_path)]), mode=os.R_OK, logger=logger)


def set_mock_return_values(list_of_mocks: List[mock.MagicMock], list_of_return_values: list):
    for mock_element, return_value in zip(list_of_mocks, list_of_return_values):
        mock_element.return_value = return_value
