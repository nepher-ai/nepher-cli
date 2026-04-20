"""Backend URL resolution."""

from __future__ import annotations

import pytest

from nepher_cli.config import (
    DEFAULT_ACCOUNT_BACKEND,
    DEFAULT_HACKATHON_BACKEND,
    resolve_backend_base,
)


def test_resolve_flag_overrides_env_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEPHER_CLI_BACKEND", "https://env.example")
    monkeypatch.setenv("NEPHER_CLI_ENV", "development")
    assert resolve_backend_base("account", "https://flag.example") == "https://flag.example"


def test_resolve_single_backend_env_overrides_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_ACCOUNT_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_HACKATHON_BACKEND", raising=False)
    monkeypatch.setenv("NEPHER_CLI_BACKEND", "https://staging.example")
    monkeypatch.setenv("NEPHER_CLI_ENV", "production")
    assert resolve_backend_base("account", None) == "https://staging.example"
    assert resolve_backend_base("hackathon", None) == "https://staging.example"


def test_resolve_per_service_env_overrides_single_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEPHER_CLI_BACKEND", "https://legacy.example")
    monkeypatch.setenv("NEPHER_CLI_ACCOUNT_BACKEND", "https://account-only.example")
    assert resolve_backend_base("account", None) == "https://account-only.example"
    assert resolve_backend_base("hackathon", None) == "https://legacy.example"


def test_resolve_per_service_hackathon_overrides_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEPHER_CLI_BACKEND", "https://legacy.example")
    monkeypatch.setenv("NEPHER_CLI_HACKATHON_BACKEND", "https://hackathon-only.example")
    assert resolve_backend_base("account", None) == "https://legacy.example"
    assert resolve_backend_base("hackathon", None) == "https://hackathon-only.example"


def test_resolve_defaults_production(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "NEPHER_CLI_BACKEND",
        "NEPHER_CLI_ACCOUNT_BACKEND",
        "NEPHER_CLI_HACKATHON_BACKEND",
        "NEPHER_CLI_ENV",
    ):
        monkeypatch.delenv(key, raising=False)
    assert resolve_backend_base("account", None) == DEFAULT_ACCOUNT_BACKEND
    assert resolve_backend_base("hackathon", None) == DEFAULT_HACKATHON_BACKEND


def test_resolve_explicit_production_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_ACCOUNT_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_HACKATHON_BACKEND", raising=False)
    monkeypatch.setenv("NEPHER_CLI_ENV", "production")
    assert resolve_backend_base("account", None) == DEFAULT_ACCOUNT_BACKEND


def test_resolve_development_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_ACCOUNT_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_HACKATHON_BACKEND", raising=False)
    monkeypatch.setenv("NEPHER_CLI_ENV", "development")
    assert resolve_backend_base("account", None) == "http://127.0.0.1:8001"
    assert resolve_backend_base("hackathon", None) == "http://127.0.0.1:8002"


def test_resolve_dev_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_ACCOUNT_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_HACKATHON_BACKEND", raising=False)
    monkeypatch.setenv("NEPHER_CLI_ENV", "dev")
    assert resolve_backend_base("account", None) == "http://127.0.0.1:8001"


def test_resolve_staging_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_ACCOUNT_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_HACKATHON_BACKEND", raising=False)
    monkeypatch.setenv("NEPHER_CLI_ENV", "staging")
    assert resolve_backend_base("account", None) == "https://api.account-staging.nepher.ai"
    assert resolve_backend_base("hackathon", None) == "https://api.hackathon-staging.nepher.ai"


def test_resolve_unknown_env_falls_back_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_ACCOUNT_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_HACKATHON_BACKEND", raising=False)
    monkeypatch.setenv("NEPHER_CLI_ENV", "not-a-real-env")
    assert resolve_backend_base("account", None) == DEFAULT_ACCOUNT_BACKEND


def test_resolve_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_ACCOUNT_BACKEND", raising=False)
    monkeypatch.delenv("NEPHER_CLI_HACKATHON_BACKEND", raising=False)
    assert resolve_backend_base("account", "https://x.test/") == "https://x.test"
