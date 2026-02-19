"""Tests for the CatLink CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from catlink_cli.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestLoginCommand:
    @patch("catlink_cli.cli.save_credentials")
    @patch("catlink_cli.cli.CatLinkAPI")
    def test_login_auto_region(
        self, mock_api_cls: MagicMock, mock_save: MagicMock, runner: CliRunner
    ) -> None:
        mock_instance = MagicMock()
        mock_instance.login_auto_region.return_value = ("tok", "https://api.example.com/")
        mock_api_cls.return_value = mock_instance

        result = runner.invoke(
            cli, ["login", "--phone", "123", "--password", "pass", "--iac", "86"]
        )
        assert result.exit_code == 0
        assert "successful" in result.output
        mock_save.assert_called_once_with(
            "tok", "123", "86", "https://api.example.com/", verify=True
        )

    @patch("catlink_cli.cli.CatLinkAPI")
    def test_login_failure(self, mock_api_cls: MagicMock, runner: CliRunner) -> None:
        from catlink_cli.api import CatLinkAPIError

        mock_instance = MagicMock()
        mock_instance.login_auto_region.side_effect = CatLinkAPIError("bad creds")
        mock_api_cls.return_value = mock_instance

        result = runner.invoke(cli, ["login", "--phone", "123", "--password", "bad", "--iac", "86"])
        assert result.exit_code != 0
        assert "Error" in result.output


class TestDevicesCommand:
    @patch("catlink_cli.cli.get_authenticated_client")
    def test_lists_devices(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get_devices.return_value = [
            {"id": "1", "deviceName": "MyScooper", "deviceType": "SCOOPER", "model": "SE"}
        ]
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["devices"])
        assert result.exit_code == 0
        assert "MyScooper" in result.output
        assert "SCOOPER" in result.output

    @patch("catlink_cli.cli.get_authenticated_client")
    def test_no_devices(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get_devices.return_value = []
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["devices"])
        assert result.exit_code == 0
        assert "No devices" in result.output


class TestStatusCommand:
    @patch("catlink_cli.cli.get_authenticated_client")
    def test_shows_status(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get_device_detail.return_value = {
            "workStatus": "00",
            "workModel": "00",
            "online": True,
            "catLitterWeight": 3.5,
            "litterCountdown": 15,
            "inductionTimes": 10,
            "manualTimes": 5,
            "deodorantCountdown": 20,
            "temperature": "25",
            "humidity": "60",
        }
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["status", "123", "--type", "SCOOPER"])
        assert result.exit_code == 0
        assert "idle" in result.output
        assert "auto" in result.output
        assert "3.5" in result.output
        assert "15" in result.output


class TestCleanCommand:
    @patch("catlink_cli.cli.get_authenticated_client")
    def test_clean_scooper(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.send_action.return_value = {"returnCode": 0}
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["clean", "123"])
        assert result.exit_code == 0
        assert "Cleaning started" in result.output
        mock_client.send_action.assert_called_once_with("123", "01", "SCOOPER")


class TestPauseCommand:
    @patch("catlink_cli.cli.get_authenticated_client")
    def test_pause(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.send_action.return_value = {"returnCode": 0}
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["pause", "123"])
        assert result.exit_code == 0
        assert "paused" in result.output


class TestCatsCommand:
    @patch("catlink_cli.cli.get_authenticated_client")
    def test_lists_cats(self, mock_get_client: MagicMock, runner: CliRunner) -> None:
        mock_client = MagicMock()
        mock_client.get_cats.return_value = [
            {"name": "Whiskers", "id": "42", "weight": "4.2", "breedName": "Tabby"}
        ]
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["cats"])
        assert result.exit_code == 0
        assert "Whiskers" in result.output
        assert "Tabby" in result.output
