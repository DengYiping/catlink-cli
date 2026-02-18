"""Constants for the CatLink CLI."""

DEFAULT_API_BASE = "https://app.catlinks.cn/api/"

API_SERVERS: dict[str, str] = {
    "global": "https://app.catlinks.cn/api/",
    "china": "https://app-sh.catlinks.cn/api/",
    "usa": "https://app-usa.catlinks.cn/api/",
    "singapore": "https://app-sgp.catlinks.cn/api/",
}

SIGN_KEY = "00109190907746a7ad0e2139b6d09ce47551770157fe4ac5922f3a5454c82712"

RSA_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCCA9I+iEl2AI8dnhdwwxPxHVK8iNAt6aTq6UhNsLsguWS5qtbLnuGz2RQdfNS"
    "aKSU2B6D/vE2gb1fM6f1A5cKndqF/riWGWn1EfL3FFQZduOTxoA0RTQzhrTa5LHcJ/an/NuHUwShwIOij0Mf4g8faTe4FT7/HdA"
    "oK7uW0cG9mZwIDAQAB"
)

DEVICE_MODES: dict[str, dict[str, str]] = {
    "SCOOPER": {
        "00": "auto",
        "01": "manual",
        "02": "time",
        "03": "empty",
    },
    "LITTER_BOX_599": {
        "00": "auto",
        "01": "manual",
        "02": "time",
    },
}

DEVICE_ACTIONS: dict[str, dict[str, str]] = {
    "SCOOPER": {
        "00": "pause",
        "01": "start",
    },
    "LITTER_BOX_599": {
        "01": "clean",
        "00": "pause",
    },
}

WORK_STATUSES: dict[str, str] = {
    "00": "idle",
    "01": "running",
    "02": "need_reset",
}

KEYRING_SERVICE = "catlink-cli"
KEYRING_TOKEN_KEY = "token"
KEYRING_PHONE_KEY = "phone"
KEYRING_IAC_KEY = "phone_iac"
KEYRING_API_BASE_KEY = "api_base"
