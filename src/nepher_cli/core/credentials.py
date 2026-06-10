"""Persistent credential storage for npcli.

Stores API key, JWT access/refresh tokens, and user metadata in
~/.nepher/credentials.json (or %APPDATA%\\nepher\\credentials.json on Windows).

Sensitive values (tokens) are also mirrored into the system keyring when
the ``keyring`` package is available, and the JSON file contains only
non-secret metadata plus the expiry timestamp in that case.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

try:
    import keyring as _keyring

    _HAS_KEYRING = True
except ImportError:  # pragma: no cover
    _HAS_KEYRING = False

try:
    from platformdirs import user_config_dir

    def _config_dir() -> Path:
        return Path(user_config_dir("nepher", appauthor=False))

except ImportError:  # pragma: no cover
    def _config_dir() -> Path:  # type: ignore[misc]
        return Path.home() / ".nepher"


_KEYRING_SERVICE = "npcli"
_KEYRING_ACCESS = "access_token"
_KEYRING_REFRESH = "refresh_token"
_KEYRING_API_KEY = "api_key"


def _cred_path() -> Path:
    d = _config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "credentials.json"


def _read_json() -> dict[str, Any]:
    p = _cred_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(data: dict[str, Any]) -> None:
    p = _cred_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        p.chmod(0o600)
    except OSError:
        pass


def _kr_get(key: str) -> str | None:
    if not _HAS_KEYRING:
        return None
    try:
        return _keyring.get_password(_KEYRING_SERVICE, key)
    except Exception:
        return None


def _kr_set(key: str, value: str) -> bool:
    if not _HAS_KEYRING:
        return False
    try:
        _keyring.set_password(_KEYRING_SERVICE, key, value)
        return True
    except Exception:
        return False


def _kr_delete(key: str) -> None:
    if not _HAS_KEYRING:
        return
    try:
        _keyring.delete_password(_KEYRING_SERVICE, key)
    except Exception:
        pass


def save_credentials(
    *,
    api_key: str,
    access_token: str,
    refresh_token: str,
    expires_in: int,
    user: dict[str, Any],
) -> None:
    """Persist all credential material after a successful cli-login."""
    expires_at = int(time.time()) + expires_in

    stored_in_keyring = all([
        _kr_set(_KEYRING_API_KEY, api_key),
        _kr_set(_KEYRING_ACCESS, access_token),
        _kr_set(_KEYRING_REFRESH, refresh_token),
    ])

    meta: dict[str, Any] = {
        "expires_at": expires_at,
        "user": user,
        "keyring": stored_in_keyring,
    }

    if not stored_in_keyring:
        meta["api_key"] = api_key
        meta["access_token"] = access_token
        meta["refresh_token"] = refresh_token

    _write_json(meta)


def load_credentials() -> dict[str, Any] | None:
    """Return the stored credential dict or None if nothing is saved."""
    meta = _read_json()
    if not meta:
        return None

    if meta.get("keyring"):
        meta["api_key"] = _kr_get(_KEYRING_API_KEY)
        meta["access_token"] = _kr_get(_KEYRING_ACCESS)
        meta["refresh_token"] = _kr_get(_KEYRING_REFRESH)

    if not meta.get("access_token") and not meta.get("api_key"):
        return None

    return meta


def clear_credentials() -> None:
    """Delete all stored credential material."""
    _kr_delete(_KEYRING_API_KEY)
    _kr_delete(_KEYRING_ACCESS)
    _kr_delete(_KEYRING_REFRESH)
    p = _cred_path()
    if p.exists():
        p.unlink()


def _is_expired(creds: dict[str, Any]) -> bool:
    expires_at = creds.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return True
    return time.time() > (expires_at - 60)


def _refresh_access_token(refresh_token: str, account_base: str) -> dict[str, Any] | None:
    """Call /api/v1/auth/refresh and return updated token data, or None on failure."""
    url = f"{account_base.rstrip('/')}/api/v1/auth/refresh"
    try:
        r = httpx.post(url, json={"refresh_token": refresh_token}, timeout=30.0)
    except httpx.RequestError:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def get_auth_headers(
    api_key_override: str | None = None,
    *,
    account_base: str | None = None,
) -> dict[str, str]:
    """Return HTTP auth headers for a request.

    Priority:
    1. ``api_key_override`` (from ``--api-key`` flag or ``NEPHER_API_KEY`` env var)
    2. Stored JWT (auto-refreshed if expired)
    3. Stored API key (fallback when no JWT)
    4. Empty dict — command must handle the unauthenticated case.
    """
    from nepher_cli.config import ACCOUNT_BACKEND

    base = account_base or ACCOUNT_BACKEND

    if api_key_override:
        return {"X-API-Key": api_key_override}

    creds = load_credentials()
    if not creds:
        return {}

    access_token = creds.get("access_token")
    refresh_token = creds.get("refresh_token")
    api_key = creds.get("api_key")

    if access_token and not _is_expired(creds):
        return {"Authorization": f"Bearer {access_token}"}

    if refresh_token:
        refreshed = _refresh_access_token(refresh_token, base)
        if refreshed and refreshed.get("access_token"):
            new_access = refreshed["access_token"]
            expires_in = refreshed.get("expires_in", 86400)
            new_expires_at = int(time.time()) + expires_in
            meta = _read_json()
            meta["expires_at"] = new_expires_at
            if meta.get("keyring"):
                _kr_set(_KEYRING_ACCESS, new_access)
            else:
                meta["access_token"] = new_access
            _write_json(meta)
            return {"Authorization": f"Bearer {new_access}"}

    if api_key:
        return {"X-API-Key": api_key}

    return {}


def get_stored_api_key() -> str | None:
    """Return the stored raw API key, or None."""
    creds = load_credentials()
    if creds:
        return creds.get("api_key")
    return None


def whoami_from_cache() -> dict[str, Any] | None:
    """Return user metadata from the credentials cache without a network call."""
    creds = load_credentials()
    if creds:
        return creds.get("user")
    return None
