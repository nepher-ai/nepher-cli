"""Backend base URL resolution — env presets for dev / staging / production (pip defaults: production)."""

from __future__ import annotations

import os
from typing import Literal

Service = Literal["account", "hackathon"]

# Production defaults (also used when NEPHER_CLI_ENV=production). Shipped in every PyPI release.
DEFAULT_ACCOUNT_BACKEND = "https://api.accounts.nepher.ai"
DEFAULT_HACKATHON_BACKEND = "https://api.hackathon.nepher.ai"

# Preset bundles — dev/staging/prod (see internal-docs/Hackathon/ENVIRONMENTS.md).
_PRESETS: dict[str, tuple[str, str]] = {
    "production": (DEFAULT_ACCOUNT_BACKEND, DEFAULT_HACKATHON_BACKEND),
    "staging": (
        "https://api.account-staging.nepher.ai",
        "https://api.hackathon-staging.nepher.ai",
    ),
    "development": (
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8002",
    ),
}

_ENV_ALIASES: dict[str, str] = {
    "prod": "production",
    "production": "production",
    "stage": "staging",
    "staging": "staging",
    "dev": "development",
    "development": "development",
    "local": "development",
}


def _normalize_env_name(raw: str | None) -> str:
    if not raw or not raw.strip():
        return "production"
    key = raw.strip().lower()
    return _ENV_ALIASES.get(key, key)


def resolve_backend_base(service: Service, backend_flag: str | None) -> str:
    """
    Resolve the API base URL for the given service.

    Precedence (highest first):
    1. ``--backend`` CLI flag (applies to the active command’s service)
    2. ``NEPHER_CLI_ACCOUNT_BACKEND`` or ``NEPHER_CLI_HACKATHON_BACKEND`` (per service)
    3. ``NEPHER_CLI_BACKEND`` — single URL for **both** services (legacy / quick override)
    4. Preset from ``NEPHER_CLI_ENV`` (default: **production** for pip installs)
    5. Built-in production defaults
    """
    if backend_flag:
        return backend_flag.rstrip("/")

    if service == "account":
        specific = os.environ.get("NEPHER_CLI_ACCOUNT_BACKEND")
    else:
        specific = os.environ.get("NEPHER_CLI_HACKATHON_BACKEND")
    if specific:
        return specific.rstrip("/")

    single = os.environ.get("NEPHER_CLI_BACKEND")
    if single:
        return single.rstrip("/")

    env_name = _normalize_env_name(os.environ.get("NEPHER_CLI_ENV"))
    account_url, hackathon_url = _PRESETS.get(env_name, _PRESETS["production"])
    if service == "account":
        return account_url
    return hackathon_url
