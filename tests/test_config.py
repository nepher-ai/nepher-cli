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
    assert resolve_backend_base("account", "https://flag.example") == "https://flag.example"


def test_resolve_env_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEPHER_CLI_BACKEND", "https://staging.example")
    assert resolve_backend_base("account", None) == "https://staging.example"
    assert resolve_backend_base("hackathon", None) == "https://staging.example"


def test_resolve_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    assert resolve_backend_base("account", None) == DEFAULT_ACCOUNT_BACKEND
    assert resolve_backend_base("hackathon", None) == DEFAULT_HACKATHON_BACKEND


def test_resolve_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEPHER_CLI_BACKEND", raising=False)
    assert resolve_backend_base("account", "https://x.test/") == "https://x.test"
