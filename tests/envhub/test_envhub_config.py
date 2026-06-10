"""EnvHub configuration."""

from __future__ import annotations

from nepher_cli.envhub.config import DEFAULT_CONFIG, list_values, mask_secret, parse_config_value


def test_list_values_includes_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ENVHUB_API_URL", raising=False)
    monkeypatch.delenv("NEPHER_CACHE_DIR", raising=False)
    monkeypatch.setattr("nepher_cli.envhub.config.load_config_file", lambda: {})

    import builtins

    real_import = builtins.__import__

    def _import_error(name, *args, **kwargs):
        if name == "nepher.config":
            raise ImportError("nepher not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import_error)
    values = list_values()
    assert values["api_url"] == DEFAULT_CONFIG["api_url"]
    assert values["cache_dir"] == DEFAULT_CONFIG["cache_dir"]
    assert values["default_category"] is None


def test_list_values_matches_nepher_package() -> None:
    try:
        from nepher.config import get_config
    except ImportError:
        return
    cfg = get_config()
    values = list_values()
    assert values["api_url"] == cfg.get("api_url")
    assert values["cache_dir"] == cfg.get("cache_dir")
    assert values["default_category"] == cfg.get("default_category")


def test_mask_secret() -> None:
    assert mask_secret("api_key", "abcdefghij") == "abcd...ghij"
    assert mask_secret("cache_dir", "~/.nepher/cache") == "~/.nepher/cache"


def test_parse_config_value() -> None:
    assert parse_config_value("true") is True
    assert parse_config_value("42") == 42
    assert parse_config_value("1.5") == 1.5
    assert parse_config_value("navigation") == "navigation"
