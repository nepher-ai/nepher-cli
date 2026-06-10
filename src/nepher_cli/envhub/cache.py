"""Local EnvHub bundle cache paths — aligned with the ``nepher`` CLI."""

from __future__ import annotations

import os
from pathlib import Path

from nepher_cli.envhub.config import DEFAULT_CONFIG, load_config_file

_DEFAULT_CACHE_DIR = Path.home() / ".nepher" / "cache"


def _nepher_cache_dir(category: str | None = None) -> Path | None:
    try:
        from nepher.config import get_config

        return get_config().get_cache_dir(category=category)
    except ImportError:
        return None


def resolve_cache_dir(cache_dir: str | Path | None = None, category: str | None = None) -> Path:
    """Resolve the local bundle cache directory (same rules as ``nepher``)."""
    if cache_dir:
        return Path(cache_dir).expanduser().resolve()

    nepher_dir = _nepher_cache_dir(category)
    if nepher_dir is not None:
        return nepher_dir

    env_override = os.getenv("NEPHER_CACHE_DIR")
    if env_override:
        return Path(env_override).expanduser().resolve()

    config = {**DEFAULT_CONFIG, **load_config_file()}
    if category:
        cat_config = config.get("categories", {}).get(category, {})
        path_str = cat_config.get("cache_dir") or config.get("cache_dir")
    else:
        path_str = config.get("cache_dir")

    if path_str:
        return Path(path_str).expanduser().resolve()
    return _DEFAULT_CACHE_DIR.resolve()


def is_cached_env(path: Path) -> bool:
    """Return True when ``path`` is a cached environment bundle."""
    return path.is_dir() and (path / "manifest.yaml").exists()


def list_cached_env_dirs(root: Path) -> list[Path]:
    """List cached environment directories under ``root``."""
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if is_cached_env(p))
