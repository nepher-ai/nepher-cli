"""EnvHub local cache path resolution."""

from __future__ import annotations

from pathlib import Path

from nepher_cli.envhub.cache import is_cached_env, list_cached_env_dirs, resolve_cache_dir


def test_resolve_cache_dir_matches_nepher_package() -> None:
    try:
        from nepher.config import get_config
    except ImportError:
        return
    assert resolve_cache_dir() == get_config().get_cache_dir()


def test_resolve_cache_dir_fallback_default(monkeypatch) -> None:
    monkeypatch.delenv("NEPHER_CACHE_DIR", raising=False)
    monkeypatch.setattr("nepher_cli.envhub.cache._nepher_cache_dir", lambda _category=None: None)
    monkeypatch.setattr("nepher_cli.envhub.config.load_config_file", lambda: {})
    assert resolve_cache_dir() == Path("~/.nepher/cache").expanduser().resolve()


def test_resolve_cache_dir_cli_override(tmp_path: Path) -> None:
    custom = tmp_path / "custom-cache"
    assert resolve_cache_dir(custom) == custom.resolve()


def test_resolve_cache_dir_env_override(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "env-cache"
    monkeypatch.setenv("NEPHER_CACHE_DIR", str(custom))
    monkeypatch.setattr("nepher_cli.envhub.config.load_config_file", lambda: {})
    assert resolve_cache_dir() == custom.resolve()


def test_list_cached_env_dirs_requires_manifest(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    root.mkdir()
    (root / "valid-env").mkdir()
    (root / "valid-env" / "manifest.yaml").write_text("id: valid-env\n", encoding="utf-8")
    (root / "incomplete").mkdir()

    entries = list_cached_env_dirs(root)
    assert [p.name for p in entries] == ["valid-env"]
    assert is_cached_env(root / "valid-env")
    assert not is_cached_env(root / "incomplete")
