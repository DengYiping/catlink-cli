"""Tests for the CatLink API client."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from catlink_cli.api import CatLinkAPI, CatLinkAPIError, get_authenticated_client
from catlink_cli.const import SIGN_KEY


class TestParamsSign:
    def test_sign_empty_params(self) -> None:
        result = CatLinkAPI._params_sign({})
        expected = hashlib.md5(f"key={SIGN_KEY}".encode()).hexdigest().upper()
        assert result == expected

    def test_sign_sorts_params_alphabetically(self) -> None:
        pms = {"zebra": "1", "alpha": "2"}
        result = CatLinkAPI._params_sign(pms)
        expected_str = f"alpha=2&zebra=1&key={SIGN_KEY}"
        expected = hashlib.md5(expected_str.encode()).hexdigest().upper()
        assert result == expected

    def test_sign_is_uppercase_md5(self) -> None:
        result = CatLinkAPI._params_sign({"a": "1"})
        assert result == result.upper()
        assert len(result) == 32


class TestEncryptPassword:
    def test_encrypt_returns_base64_string(self) -> None:
        result = CatLinkAPI.encrypt_password("test123")
        assert isinstance(result, str)
        assert len(result) > 16

    def test_encrypt_is_deterministic_structure(self) -> None:
        r1 = CatLinkAPI.encrypt_password("hello")
        r2 = CatLinkAPI.encrypt_password("hello")
        assert isinstance(r1, str)
        assert isinstance(r2, str)
        assert len(r1) > 0
        assert len(r2) > 0


class TestCatLinkAPI:
    def test_api_url_construction(self) -> None:
        client = CatLinkAPI(api_base="https://example.com/api/")
        assert client._api_url("login/password") == "https://example.com/api/login/password"

    def test_api_url_preserves_full_urls(self) -> None:
        client = CatLinkAPI()
        assert client._api_url("https://other.com/test") == "https://other.com/test"

    def test_api_url_strips_trailing_slash(self) -> None:
        client = CatLinkAPI(api_base="https://example.com/api")
        assert client._api_url("test") == "https://example.com/api/test"

    @patch("catlink_cli.api.httpx.Client")
    def test_login_success(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"token": "abc123"}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        client = CatLinkAPI()
        client._client = mock_client
        token = client.login("86", "1234567890", "longencryptedpasswordvalue")
        assert token == "abc123"
        assert client.token == "abc123"

    @patch("catlink_cli.api.httpx.Client")
    def test_login_failure_raises(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"msg": "bad password", "data": {}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        client = CatLinkAPI()
        client._client = mock_client
        with pytest.raises(CatLinkAPIError, match="Login failed"):
            client.login("86", "1234567890", "longencryptedpasswordvalue")

    @patch("catlink_cli.api.httpx.Client")
    def test_get_devices(self, mock_client_cls: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "returnCode": 0,
            "data": {"devices": [{"id": "1", "deviceName": "Scooper", "deviceType": "SCOOPER"}]},
        }
        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        client = CatLinkAPI(token="tok123")
        client._client = mock_client
        devices = client.get_devices()
        assert len(devices) == 1
        assert devices[0]["deviceName"] == "Scooper"

    @patch("catlink_cli.api.httpx.Client")
    def test_check_response_error(self, mock_client_cls: MagicMock) -> None:
        client = CatLinkAPI()
        with pytest.raises(CatLinkAPIError, match="Token expired"):
            client._check_response({"returnCode": 1002})

    @patch("catlink_cli.api.httpx.Client")
    def test_check_response_ok(self, mock_client_cls: MagicMock) -> None:
        client = CatLinkAPI()
        result = client._check_response({"returnCode": 0, "data": {}})
        assert result == {"returnCode": 0, "data": {}}


class TestGetAuthenticatedClient:
    @patch("catlink_cli.api.keyring")
    def test_raises_when_no_credentials(self, mock_keyring: MagicMock) -> None:
        mock_keyring.get_password.return_value = None
        with pytest.raises(CatLinkAPIError, match="Not logged in"):
            get_authenticated_client()

    @patch("catlink_cli.api.keyring")
    def test_returns_client_with_stored_token(self, mock_keyring: MagicMock) -> None:
        def side_effect(service: str, key: str) -> str | None:
            data = {
                "token": "stored_tok",
                "phone": "123",
                "phone_iac": "86",
                "api_base": "https://example.com/api/",
            }
            return data.get(key)

        mock_keyring.get_password.side_effect = side_effect
        client = get_authenticated_client()
        assert client.token == "stored_tok"
        assert "example.com" in client.api_base
        client.close()
