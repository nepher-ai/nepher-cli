"""EnvHub configuration — aligned with the ``nepher`` CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "api_url": "https://api.nepher.ai/envhub",
    "api_key": None,
    "cache_dir": "~/.nepher/cache",
    "default_category": None,
    "categories": {},
}

LIST_KEYS = ("api_url", "cache_dir", "default_category")

# Older ``nepher`` releases persisted this default into config.toml; treat it as unset.
LEGACY_API_URLS = frozenset({"https://envhub-api.nepher.ai", "https://envhub-api.nepher.ai/"})

SECRET_KEYS = ("api_key",)


def find_config_file() -> Path | None:
    """Return the active nepher config file path, if any."""
    cwd_config = Path.cwd() / ".nepherrc"
    if cwd_config.exists():
        return cwd_config
    for name in ("config.toml", "config.json"):
        home_config = Path.home() / ".nepher" / name
        if home_config.exists():
            return home_config
    return None


def _load_toml(text: str) -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib.loads(text)


def load_config_file() -> dict[str, Any]:
    """Load values from the nepher config file (no defaults or env overrides)."""
    config_file = find_config_file()
    if not config_file:
        return {}

    try:
        text = config_file.read_text(encoding="utf-8")
        if config_file.suffix == ".json":
            data = json.loads(text)
        elif config_file.suffix == ".toml":
            data = _load_toml(text)
        else:
            try:
                data = _load_toml(text)
            except Exception:
                data = json.loads(text)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get("api_url") in LEGACY_API_URLS:
        data.pop("api_url")
    return data


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    merged = dict(config)
    if os.getenv("NEPHER_ENVHUB_API_URL"):
        merged["api_url"] = os.getenv("NEPHER_ENVHUB_API_URL")
    elif os.getenv("ENVHUB_API_URL"):
        merged["api_url"] = os.getenv("ENVHUB_API_URL")
    elif os.getenv("NEPHER_API_URL"):
        merged["api_url"] = f"{os.getenv('NEPHER_API_URL').rstrip('/')}/envhub"
    if os.getenv("NEPHER_API_KEY"):
        merged["api_key"] = os.getenv("NEPHER_API_KEY")
    if os.getenv("NEPHER_CACHE_DIR"):
        merged["cache_dir"] = os.getenv("NEPHER_CACHE_DIR")
    return merged


def _fallback_get(key: str, default: Any = None) -> Any:
    config = _apply_env_overrides({**DEFAULT_CONFIG, **load_config_file()})
    keys = key.split(".")
    value: Any = config
    for part in keys:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return default
    return value


def get_value(key: str, default: Any = None) -> Any:
    """Return an effective configuration value."""
    try:
        from nepher.config import get_config

        value = get_config().get(key, default)
    except ImportError:
        return _fallback_get(key, default)
    if key == "api_url" and value in LEGACY_API_URLS:
        return _fallback_get(key, default)
    return value


def get_api_url() -> str:
    """Effective EnvHub API base URL (env vars > config file > default)."""
    return str(get_value("api_url") or DEFAULT_CONFIG["api_url"]).rstrip("/")


def list_values() -> dict[str, Any]:
    """Return the standard keys shown by ``nepher config list``."""
    return {key: get_value(key) for key in LIST_KEYS}


def parse_config_value(value: str) -> Any:
    """Parse a CLI string into a config value."""
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.isdigit():
        return int(value)
    if value.replace(".", "", 1).isdigit():
        return float(value)
    return value


def set_value(key: str, value: Any) -> None:
    """Persist a configuration value."""
    if key in SECRET_KEYS:
        raise ValueError("API keys are not stored in config; use 'npcli login' or NEPHER_API_KEY.")
    try:
        from nepher.config import set_config

        set_config(key, value, save=True)
        return
    except ImportError:
        pass

    config_path = Path.home() / ".nepher" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = load_config_file()
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            nested = {}
            target[part] = nested
        target = nested
    target[parts[-1]] = value

    try:
        import tomli_w

        with open(config_path, "wb") as f:
            tomli_w.dump(data, f)
    except ImportError:
        with open(config_path.with_suffix(".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def reset_config() -> bool:
    """Delete the on-disk config file. Returns True when a file was removed."""
    try:
        from nepher.config import get_config

        config = get_config()
        config_file = getattr(config, "_config_file", None)
        if config_file and config_file.exists():
            config_file.unlink()
            return True
        return False
    except ImportError:
        pass

    removed = False
    for path in (Path.cwd() / ".nepherrc", Path.home() / ".nepher" / "config.toml"):
        if path.exists():
            path.unlink()
            removed = True
    json_path = Path.home() / ".nepher" / "config.json"
    if json_path.exists():
        json_path.unlink()
        removed = True
    return removed


def mask_secret(key: str, value: Any) -> Any:
    """Mask secret keys for display."""
    if value is None or not isinstance(value, str):
        return value
    lower = key.lower()
    if any(token in lower for token in ("api_key", "secret", "password", "token")):
        if len(value) < 8:
            return "***"
        return f"{value[:4]}...{value[-4:]}"
    return value
