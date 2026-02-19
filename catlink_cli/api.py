"""CatLink API client."""

import base64
import hashlib
import logging
import time

import httpx
import keyring
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .const import (
    API_SERVERS,
    DEFAULT_API_BASE,
    KEYRING_API_BASE_KEY,
    KEYRING_IAC_KEY,
    KEYRING_PHONE_KEY,
    KEYRING_SERVICE,
    KEYRING_TOKEN_KEY,
    KEYRING_VERIFY_KEY,
    RSA_PUBLIC_KEY,
    SIGN_KEY,
)

logger = logging.getLogger(__name__)


class CatLinkAPIError(Exception):
    """Raised when the CatLink API returns an error."""

    def __init__(self, message: str, code: int = 0) -> None:
        self.code = code
        super().__init__(message)


class CatLinkAPI:
    """Client for the CatLink cloud API."""

    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        token: str | None = None,
        language: str = "en_GB",
        verify: bool = True,
    ) -> None:
        self.api_base = api_base.rstrip("/") + "/"
        self.token = token or ""
        self.language = language
        self.verify = verify
        self._client = httpx.Client(timeout=60.0, verify=verify)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def _api_url(self, api: str) -> str:
        if api.startswith("http"):
            return api
        return f"{self.api_base}{api.lstrip('/')}"

    @staticmethod
    def _params_sign(pms: dict) -> str:
        lst = sorted(pms.items())
        parts = [f"{k}={v}" for k, v in lst]
        parts.append(f"key={SIGN_KEY}")
        return hashlib.md5("&".join(parts).encode()).hexdigest().upper()

    @staticmethod
    def encrypt_password(pwd: str) -> str:
        """Encrypt a plaintext password for the CatLink API."""
        md5 = hashlib.md5(pwd.encode()).hexdigest().lower()
        sha = hashlib.sha1(md5.encode()).hexdigest().upper()
        pub = serialization.load_der_public_key(base64.b64decode(RSA_PUBLIC_KEY), default_backend())
        pad = padding.PKCS1v15()
        return base64.b64encode(pub.encrypt(sha.encode(), pad)).decode()

    def request(
        self,
        api: str,
        params: dict | None = None,
        method: str = "GET",
    ) -> dict:
        """Make a signed request to the CatLink API."""
        url = self._api_url(api)
        headers = {
            "language": self.language,
            "User-Agent": "okhttp/3.10.0",
            "token": self.token,
        }

        pms = dict(params) if params else {}
        pms["noncestr"] = int(time.time() * 1000)
        if self.token:
            pms["token"] = self.token
        pms["sign"] = self._params_sign(pms)

        if method.upper() == "GET":
            resp = self._client.get(url, params=pms, headers=headers)
        elif method.upper() == "POST_GET":
            resp = self._client.post(url, params=pms, headers=headers)
        else:
            resp = self._client.post(url, data=pms, headers=headers)

        result = resp.json()
        logger.debug("API %s %s -> %s", method, api, result)
        return result

    def _check_response(self, rsp: dict) -> dict:
        """Check API response for errors, re-authenticate on token expiry."""
        code = rsp.get("returnCode", 0)
        if code == 1002:
            raise CatLinkAPIError("Token expired", code=1002)
        if code and code != 0:
            msg = rsp.get("msg") or rsp.get("message") or f"Error code {code}"
            raise CatLinkAPIError(msg, code=code)
        return rsp

    def login(self, phone_iac: str, phone: str, password: str) -> str:
        """Login and return the authentication token."""
        encrypted = password if len(password) > 16 else self.encrypt_password(password)
        pms = {
            "platform": "ANDROID",
            "internationalCode": phone_iac,
            "mobile": phone,
            "password": encrypted,
        }
        self.token = ""
        rsp = self.request("login/password", pms, "POST")
        tok = rsp.get("data", {}).get("token")
        if not tok:
            msg = rsp.get("msg") or rsp.get("message") or "Login failed"
            raise CatLinkAPIError(f"Login failed: {msg}")
        self.token = tok
        return tok

    def login_auto_region(self, phone_iac: str, phone: str, password: str) -> tuple[str, str]:
        """Try all API regions and return (token, api_base) for the first success."""
        errors: list[str] = []
        for region, base_url in API_SERVERS.items():
            self.api_base = base_url
            try:
                tok = self.login(phone_iac, phone, password)
                return tok, base_url
            except (CatLinkAPIError, httpx.HTTPError) as exc:
                errors.append(f"{region}: {exc}")
                continue
        raise CatLinkAPIError(f"Login failed on all regions: {'; '.join(errors)}")

    def _request_with_reauth(
        self,
        api: str,
        params: dict | None = None,
        method: str = "GET",
    ) -> dict:
        """Make a request, re-authenticating once on token expiry."""
        rsp = self.request(api, params, method)
        code = rsp.get("returnCode", 0)
        if code == 1002:
            creds = _load_credentials()
            if creds:
                self.login(creds["phone_iac"], creds["phone"], creds["token"])
                rsp = self.request(api, params, method)
        return rsp

    def get_devices(self) -> list[dict]:
        """Get the list of devices."""
        rsp = self._request_with_reauth("token/device/union/list/sorted", {"type": "NONE"})
        self._check_response(rsp)
        return rsp.get("data", {}).get("devices") or []

    def get_device_detail(self, device_id: str, device_type: str) -> dict:
        """Get detailed info for a device."""
        api_map = {
            "SCOOPER": "token/device/info",
            "LITTER_BOX_599": "token/litterbox/info",
            "C08": "token/litterbox/info/c08",
            "FEEDER": "token/device/feeder/detail",
        }
        api = api_map.get(device_type, "token/device/info")
        rsp = self._request_with_reauth(api, {"deviceId": device_id})
        self._check_response(rsp)
        return rsp.get("data", {}).get("deviceInfo") or rsp.get("data", {})

    def change_mode(self, device_id: str, mode_code: str, device_type: str) -> dict:
        """Change the device working mode."""
        if device_type == "LITTER_BOX_599":
            api = "token/litterbox/changeMode"
        else:
            api = "token/device/changeMode"
        pms = {"workModel": mode_code, "deviceId": device_id}
        rsp = self.request(api, pms, "POST")
        self._check_response(rsp)
        return rsp

    def send_action(self, device_id: str, action_code: str, device_type: str) -> dict:
        """Send an action command to the device."""
        if device_type == "LITTER_BOX_599":
            api = "token/litterbox/actionCmd"
        else:
            api = "token/device/actionCmd"
        pms = {"cmd": action_code, "deviceId": device_id}
        rsp = self.request(api, pms, "POST")
        self._check_response(rsp)
        return rsp

    def get_device_logs(self, device_id: str, device_type: str) -> list[dict]:
        """Get recent device logs."""
        api_map = {
            "SCOOPER": "token/device/scooper/stats/log/top5",
            "LITTER_BOX_599": "token/litterbox/stats/log/top5",
        }
        api = api_map.get(device_type, "token/device/union/logs")
        rsp = self._request_with_reauth(api, {"deviceId": device_id})
        self._check_response(rsp)
        data = rsp.get("data", {})
        return data.get("scooperLogTop5") or data.get("logs") or data.get("list") or []

    def replace_garbage_bag(self, device_id: str, enable: bool = True) -> dict:
        """Trigger garbage bag replacement on a LitterBox."""
        api = "token/litterbox/replaceGarbageBagCmd"
        pms = {"enable": "1" if enable else "0", "deviceId": device_id}
        rsp = self.request(api, pms, "POST")
        self._check_response(rsp)
        return rsp

    def reset_consumable(self, device_id: str, device_type: str, consumable_type: str) -> dict:
        """Reset a consumable counter (CAT_LITTER or DEODORIZER_02)."""
        api = "token/device/union/consumableReset"
        pms = {
            "consumablesType": consumable_type,
            "deviceId": device_id,
            "deviceType": device_type,
        }
        rsp = self.request(api, pms, "POST")
        self._check_response(rsp)
        return rsp

    def get_cats(self) -> list[dict]:
        """Get the list of cats."""
        rsp = self._request_with_reauth("token/pet/health/v3/cats")
        self._check_response(rsp)
        return rsp.get("data", {}).get("cats") or []

    def get_cat_summary(self, pet_id: str, date: str) -> dict:
        """Get a cat's health summary for a given date."""
        pms = {"petId": pet_id, "date": date, "sport": 1}
        rsp = self._request_with_reauth("token/pet/health/v3/summarySimple", pms)
        self._check_response(rsp)
        return rsp.get("data") or {}


def save_credentials(
    token: str, phone: str, phone_iac: str, api_base: str, verify: bool = True
) -> None:
    """Persist authentication credentials in the system keyring."""
    keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, token)
    keyring.set_password(KEYRING_SERVICE, KEYRING_PHONE_KEY, phone)
    keyring.set_password(KEYRING_SERVICE, KEYRING_IAC_KEY, phone_iac)
    keyring.set_password(KEYRING_SERVICE, KEYRING_API_BASE_KEY, api_base)
    keyring.set_password(KEYRING_SERVICE, KEYRING_VERIFY_KEY, str(verify))


def _load_credentials() -> dict | None:
    """Load stored credentials from the system keyring."""
    token = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
    if not token:
        return None
    verify_str = keyring.get_password(KEYRING_SERVICE, KEYRING_VERIFY_KEY)
    return {
        "token": token,
        "phone": keyring.get_password(KEYRING_SERVICE, KEYRING_PHONE_KEY) or "",
        "phone_iac": keyring.get_password(KEYRING_SERVICE, KEYRING_IAC_KEY) or "86",
        "api_base": keyring.get_password(KEYRING_SERVICE, KEYRING_API_BASE_KEY) or DEFAULT_API_BASE,
        "verify": verify_str != "False",
    }


def get_authenticated_client() -> CatLinkAPI:
    """Return a CatLinkAPI client using stored credentials, or raise."""
    creds = _load_credentials()
    if not creds:
        raise CatLinkAPIError("Not logged in. Run 'catlink login' first.")
    return CatLinkAPI(api_base=creds["api_base"], token=creds["token"], verify=creds["verify"])
