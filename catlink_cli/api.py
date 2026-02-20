"""CatLink API client."""

import base64
import hashlib
import logging
import pathlib
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


def _region_key(key: str, region: str) -> str:
    """
    Build a region-scoped keyring key.

    Args:
        key: Base key name.
        region: Region identifier.

    Returns:
        Region-scoped key name.
    """
    return f"{key}:{region}"


def _region_from_api_base(api_base: str) -> str | None:
    """
    Resolve a region name from an API base URL.

    Args:
        api_base: API base URL to match.

    Returns:
        Region name if known, otherwise None.
    """
    normalized = api_base.rstrip("/") + "/"
    for region, base_url in API_SERVERS.items():
        if base_url == normalized:
            return region
    return None


def _merge_devices(primary: list[dict], extra: list[dict]) -> list[dict]:
    """
    Merge device lists and de-duplicate by ID.

    Args:
        primary: Primary device list.
        extra: Additional device list.

    Returns:
        Merged device list.
    """
    merged: list[dict] = []
    seen: set[str] = set()
    for dev in [*primary, *extra]:
        dev_id = dev.get("id") or dev.get("deviceId") or dev.get("mac")
        if dev_id:
            dev_id = str(dev_id)
            if dev_id in seen:
                continue
            seen.add(dev_id)
        merged.append(dev)
    return merged


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

    def login_all_regions(
        self, phone_iac: str, phone: str, password: str
    ) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
        """
        Try all API regions and return successes and errors.

        Args:
            phone_iac: Country calling code.
            phone: Phone number.
            password: Account password (plaintext or encrypted).

        Returns:
            Tuple of (successes, errors).
        """
        successes: list[tuple[str, str, str]] = []
        errors: list[tuple[str, str]] = []
        for region, base_url in API_SERVERS.items():
            self.api_base = base_url
            try:
                tok = self.login(phone_iac, phone, password)
            except (CatLinkAPIError, httpx.HTTPError) as exc:
                errors.append((region, str(exc)))
                continue
            successes.append((region, base_url, tok))
        return successes, errors

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
            region = _region_from_api_base(self.api_base)
            creds = _load_credentials(region=region)
            if creds:
                self.login(creds["phone_iac"], creds["phone"], creds["token"])
                rsp = self.request(api, params, method)
        return rsp

    def get_devices(self) -> list[dict]:
        """Get the list of devices."""
        rsp = self._request_with_reauth("token/device/union/list/sorted", {"type": "NONE"})
        self._check_response(rsp)
        devices = rsp.get("data", {}).get("devices") or []
        if not any(dev.get("deviceType") == "FEEDER" for dev in devices):
            devices = self._try_expand_devices(devices)
        return devices

    def _try_expand_devices(self, devices: list[dict]) -> list[dict]:
        """
        Attempt to expand the device list with alternate type filters.

        Args:
            devices: Existing device list.

        Returns:
            Expanded device list with duplicates removed.
        """
        expanded = list(devices)
        for device_type in ("FEEDER", "ALL"):
            try:
                rsp = self._request_with_reauth(
                    "token/device/union/list/sorted", {"type": device_type}
                )
                self._check_response(rsp)
            except (CatLinkAPIError, httpx.HTTPError):
                continue
            extra = rsp.get("data", {}).get("devices") or []
            if extra:
                expanded = _merge_devices(expanded, extra)
        return expanded

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
            "FEEDER": "token/device/feeder/stats/log/top5",
        }
        api = api_map.get(device_type, "token/device/union/logs")
        rsp = self._request_with_reauth(api, {"deviceId": device_id})
        self._check_response(rsp)
        data = rsp.get("data", {})
        return (
            data.get("scooperLogTop5")
            or data.get("feederLogTop5")
            or data.get("logs")
            or data.get("list")
            or []
        )

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

    def food_out(self, device_id: str, portions: int = 5) -> dict:
        """Manually dispense food from a feeder."""
        pms = {"footOutNum": portions, "deviceId": device_id}
        rsp = self.request("token/device/feeder/foodOut", pms, "POST")
        self._check_response(rsp)
        return rsp

    def get_cats(self, timezone_id: str | None = None) -> list[dict]:
        """Get the list of cats."""
        pms: dict[str, str] = {}
        if timezone_id:
            pms["timezoneId"] = timezone_id
        rsp = self._request_with_reauth("token/pet/health/v3/cats", pms or None)
        self._check_response(rsp)
        return rsp.get("data", {}).get("cats") or []

    def get_cat_summary(self, pet_id: str, date: str, timezone_id: str | None = None) -> dict:
        """Get a cat's health summary for a given date."""
        pms: dict[str, str | int] = {"petId": pet_id, "date": date, "sport": 1}
        if timezone_id:
            pms["timezoneId"] = timezone_id
        rsp = self._request_with_reauth("token/pet/health/v3/summarySimple", pms)
        self._check_response(rsp)
        return rsp.get("data") or {}


def save_credentials(
    token: str, phone: str, phone_iac: str, api_base: str, verify: bool = True
) -> None:
    """
    Persist authentication credentials in the system keyring.

    Args:
        token: Authentication token.
        phone: Phone number used to authenticate.
        phone_iac: Country calling code used to authenticate.
        api_base: API base URL for the region.
        verify: Whether SSL certificate verification is enabled.

    Returns:
        None.
    """
    keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, token)
    keyring.set_password(KEYRING_SERVICE, KEYRING_PHONE_KEY, phone)
    keyring.set_password(KEYRING_SERVICE, KEYRING_IAC_KEY, phone_iac)
    keyring.set_password(KEYRING_SERVICE, KEYRING_API_BASE_KEY, api_base)
    keyring.set_password(KEYRING_SERVICE, KEYRING_VERIFY_KEY, str(verify))
    region = _region_from_api_base(api_base)
    if region:
        keyring.set_password(KEYRING_SERVICE, _region_key(KEYRING_TOKEN_KEY, region), token)
        keyring.set_password(KEYRING_SERVICE, _region_key(KEYRING_PHONE_KEY, region), phone)
        keyring.set_password(KEYRING_SERVICE, _region_key(KEYRING_IAC_KEY, region), phone_iac)
        keyring.set_password(KEYRING_SERVICE, _region_key(KEYRING_API_BASE_KEY, region), api_base)
        keyring.set_password(KEYRING_SERVICE, _region_key(KEYRING_VERIFY_KEY, region), str(verify))


def _load_credentials_for_region(region: str) -> dict | None:
    """
    Load stored credentials for a specific region.

    Args:
        region: Region identifier.

    Returns:
        Stored credential dictionary, or None if missing.
    """
    token = keyring.get_password(KEYRING_SERVICE, _region_key(KEYRING_TOKEN_KEY, region))
    if not token:
        return None
    verify_str = keyring.get_password(KEYRING_SERVICE, _region_key(KEYRING_VERIFY_KEY, region))
    if verify_str is None:
        verify_str = keyring.get_password(KEYRING_SERVICE, KEYRING_VERIFY_KEY)
    return {
        "token": token,
        "phone": keyring.get_password(
            KEYRING_SERVICE, _region_key(KEYRING_PHONE_KEY, region)
        )
        or keyring.get_password(KEYRING_SERVICE, KEYRING_PHONE_KEY)
        or "",
        "phone_iac": keyring.get_password(
            KEYRING_SERVICE, _region_key(KEYRING_IAC_KEY, region)
        )
        or keyring.get_password(KEYRING_SERVICE, KEYRING_IAC_KEY)
        or "86",
        "api_base": keyring.get_password(
            KEYRING_SERVICE, _region_key(KEYRING_API_BASE_KEY, region)
        )
        or API_SERVERS.get(region, DEFAULT_API_BASE),
        "verify": verify_str != "False" if verify_str is not None else True,
    }


def _load_legacy_credentials() -> dict | None:
    """
    Load legacy (non-region-scoped) credentials.

    Returns:
        Stored credential dictionary, or None if missing.
    """
    token = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
    if not token:
        return None
    api_base = keyring.get_password(KEYRING_SERVICE, KEYRING_API_BASE_KEY) or DEFAULT_API_BASE
    verify_str = keyring.get_password(KEYRING_SERVICE, KEYRING_VERIFY_KEY)
    return {
        "token": token,
        "phone": keyring.get_password(KEYRING_SERVICE, KEYRING_PHONE_KEY) or "",
        "phone_iac": keyring.get_password(KEYRING_SERVICE, KEYRING_IAC_KEY) or "86",
        "api_base": api_base,
        "verify": verify_str != "False" if verify_str is not None else True,
    }


def _load_credentials(*, region: str | None = None) -> dict | None:
    """
    Load stored credentials from the system keyring.

    Args:
        region: Optional region identifier to select region-scoped credentials.

    Returns:
        Stored credential dictionary, or None if missing.
    """
    if region:
        return _load_credentials_for_region(region)
    api_base = keyring.get_password(KEYRING_SERVICE, KEYRING_API_BASE_KEY)
    if api_base:
        region_name = _region_from_api_base(api_base)
        if region_name:
            creds = _load_credentials_for_region(region_name)
            if creds:
                return creds
    return _load_legacy_credentials()


def _load_all_credentials() -> list[tuple[str, dict]]:
    """
    Load credentials for all regions that have stored tokens.

    Returns:
        List of (region, credential dict) tuples.
    """
    creds: list[tuple[str, dict]] = []
    for region in API_SERVERS:
        region_creds = _load_credentials_for_region(region)
        if region_creds:
            creds.append((region, region_creds))
    if creds:
        return creds
    legacy = _load_legacy_credentials()
    if legacy:
        region_name = _region_from_api_base(legacy["api_base"]) or "default"
        return [(region_name, legacy)]
    return []


def clear_credentials() -> None:
    """
    Remove all stored credentials from the system keyring.

    Returns:
        None.
    """
    keys = [
        KEYRING_TOKEN_KEY,
        KEYRING_PHONE_KEY,
        KEYRING_IAC_KEY,
        KEYRING_API_BASE_KEY,
        KEYRING_VERIFY_KEY,
    ]
    for region in API_SERVERS:
        keys.extend(
            [
                _region_key(KEYRING_TOKEN_KEY, region),
                _region_key(KEYRING_PHONE_KEY, region),
                _region_key(KEYRING_IAC_KEY, region),
                _region_key(KEYRING_API_BASE_KEY, region),
                _region_key(KEYRING_VERIFY_KEY, region),
            ]
        )
    for key in keys:
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


def get_system_timezone() -> str:
    """Detect the system IANA timezone, falling back to UTC."""
    tz_path = pathlib.Path("/etc/localtime")
    if tz_path.is_symlink():
        resolved = str(tz_path.resolve())
        marker = "zoneinfo/"
        idx = resolved.find(marker)
        if idx != -1:
            return resolved[idx + len(marker) :]
    return "UTC"


def get_authenticated_client(*, region: str | None = None) -> CatLinkAPI:
    """
    Return a CatLinkAPI client using stored credentials, or raise.

    Args:
        region: Optional region identifier to select region-scoped credentials.

    Returns:
        Authenticated CatLinkAPI client.
    """
    creds = _load_credentials(region=region)
    if not creds:
        raise CatLinkAPIError("Not logged in. Run 'catlink login' first.")
    return CatLinkAPI(api_base=creds["api_base"], token=creds["token"], verify=creds["verify"])


def get_authenticated_clients(*, region: str | None = None) -> list[tuple[str, CatLinkAPI]]:
    """
    Return CatLinkAPI clients for one or more regions.

    Args:
        region: Optional region identifier to select a single region client.

    Returns:
        List of (region, CatLinkAPI) tuples.
    """
    if region:
        return [(region, get_authenticated_client(region=region))]
    creds_list = _load_all_credentials()
    if not creds_list:
        raise CatLinkAPIError("Not logged in. Run 'catlink login' first.")
    clients: list[tuple[str, CatLinkAPI]] = []
    for region_name, creds in creds_list:
        clients.append(
            (
                region_name,
                CatLinkAPI(
                    api_base=creds["api_base"],
                    token=creds["token"],
                    verify=creds["verify"],
                ),
            )
        )
    return clients
