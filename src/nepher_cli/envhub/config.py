"""EnvHub configuration — aligned with the ``nepher`` CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "api_url": "https://envhub-api.nepher.ai",
    "api_key": None,
    "cache_dir": "~/.nepher/cache",
    "default_category": None,
    "categories": {},
}

LIST_KEYS = ("api_url", "cache_dir", "default_category")


def find_config_file() -> Path | None:
    """Return the active nepher config file path, if any."""
    cwd_config = Path.cwd() / ".nepherrc"
    if cwd_config.exists():
        return cwd_config
    home_config = Path.home() / ".nepher" / "config.toml"
    if home_config.exists():
        return home_config
    return None


def load_config_file() -> dict[str, Any]:
    """Load values from the nepher config file (no defaults or env overrides)."""
    config_file = find_config_file()
    if not config_file:
        return {}

    try:
        if config_file.suffix == ".toml":
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    return {}
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
                return data if isinstance(data, dict) else {}
        if config_file.suffix == ".json" or config_file.name == ".nepherrc":
            with open(config_file, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    merged = dict(config)
    if os.getenv("ENVHUB_API_URL"):
        merged["api_url"] = os.getenv("ENVHUB_API_URL")
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

        return get_config().get(key, default)
    except ImportError:
        return _fallback_get(key, default)


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
