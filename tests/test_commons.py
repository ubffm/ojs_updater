import os
from unittest import mock
import pytest
from ojs_updater import commons
import logging
from tests.conftest import mock_journal_path

logger = logging.getLogger()

# DONE: The function drop_privileges() applies os.setgid() and os.setuid(), both being available only on UNIX!
#  Hence, either mention in the README that the script only runs on UNIX platforms or add a check for the OS!
# DONE: In commons also many functions have an optional parameter 'logger', but the implementation makes it mandatory!

class DiskSpace:
    def __init__(self, free_space):
        self.free = free_space


class TestCommons:
    @mock.patch('os.access')
    @pytest.mark.parametrize(['locations', 'mode', 'permission_value', 'expected_call_mode', 'expected_permission'],
                             [
                                 (['/foo/bar'], None, [True], os.R_OK | os.W_OK | os.F_OK, True),
                                 (['/foo/bar', '/bar/foo'], None, [True, False], os.R_OK | os.W_OK | os.F_OK, False),
                                 (['/foo/bar'], os.R_OK, [False], os.R_OK, False),
                                 (['/foo/bar'], os.F_OK, [False], os.F_OK, False),
                                 (['/foo/bar'], os.W_OK, [False], os.W_OK, False),
                                 (['/foo/bar'], os.R_OK, [True], os.R_OK, True),
                                 (['/foo/bar'], os.F_OK, [True], os.F_OK, True),
                                 (['/foo/bar'], os.W_OK, [True], os.W_OK, True)
                             ]
                             )
    def test_check_permissions(self, mock_access, locations, mode, permission_value, expected_call_mode,
                               expected_permission):
        mock_access.side_effect = permission_value
        mode_default = os.R_OK | os.F_OK | os.W_OK

        if mode is not None:
            permission = commons.check_permissions(locations=locations, mode=mode, logger=logger)
        else:
            mode = mode_default
            permission = commons.check_permissions(locations=locations, logger=logger)

        assert permission == expected_permission
        mock_access.assert_called()
        for location in locations:
            mock_access.assert_any_call(location, mode)

    @mock.patch('shutil.disk_usage', spec=True)
    @pytest.mark.parametrize('locations', [['/foo/bar', '/bar/foo']])
    @pytest.mark.parametrize(['free_space', 'expected_result'], [
        ([DiskSpace(free_space=10 ** 10), DiskSpace(free_space=10 ** 11)], True),
        ([DiskSpace(free_space=10 ** 7), DiskSpace(free_space=10 ** 11)], False),
        ([DiskSpace(free_space=10 ** 11), DiskSpace(free_space=10 ** 6)], False)
    ])
    def test_disk_usage(self, mock_disk_usage: mock.MagicMock, locations, free_space, expected_result):
        mock_disk_usage.side_effect = free_space
        is_enough_space_free = commons.check_disk_usage(locations)

        mock_disk_usage.assert_called()
        assert is_enough_space_free == expected_result

    @mock.patch('os.getegid', spec=True)
    @mock.patch('os.geteuid', spec=True)
    def test_drop_privileges_with_non_root(self, mock_getuid, mock_getgid):
        mock_getuid.return_value = 1000
        mock_getgid.return_value = 1000

        with pytest.raises(SystemExit):
            commons.drop_privileges('foo', 'bar')

        mock_getuid.assert_called()

    @mock.patch('ojs_updater.commons.get_system_data_on_user_and_group')
    @mock.patch('os.setgid', spec=True)
    @mock.patch('os.setuid', spec=True)
    @mock.patch('os.getegid', spec=True)
    @mock.patch('os.geteuid', spec=True)
    def test_drop_privileges(self, mock_geteuid, mock_getegid, mock_setuid, mock_setgid, mock_system_data):
        set_root_as_mock_user(mock_geteuid, mock_getegid)
        mock_group_data = mock.MagicMock()
        mock_user_data = mock.MagicMock()
        mock_group_data.gr_gid = mock_user_data.pw_uid = 1000
        mock_system_data.return_value = (mock_user_data, mock_group_data)

        commons.drop_privileges('foo', 'bar', logger=logger)

        mock_setuid.assert_called_once_with(1000)
        mock_setgid.assert_called_once_with(1000)

    @pytest.mark.parametrize(['plugin_folder', 'expected_result'],
                             [('plugins/generic/plugin1', True), ('plugins/generic/plugin2', False)])
    def test_is_ojs_plugin(self, plugin_folder, expected_result):
        plugin_path = mock_journal_path / plugin_folder
        assert commons.is_ojs_plugin(plugin_path) == expected_result


def set_root_as_mock_user(mock_getuid, mock_getgid):
    mock_getgid.return_value = 0
    mock_getuid.return_value = 0
