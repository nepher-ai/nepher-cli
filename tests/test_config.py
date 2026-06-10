"""Backend URL resolution."""

from __future__ import annotations

from nepher_cli.config import (
    ACCOUNT_BACKEND,
    DEFAULT_ACCOUNT_BACKEND,
    DEFAULT_HACKATHON_BACKEND,
    HACKATHON_BACKEND,
    resolve_backend_base,
)


def test_account_backend_constant() -> None:
    assert ACCOUNT_BACKEND == "https://account-api.nepher.ai"
    assert DEFAULT_ACCOUNT_BACKEND == ACCOUNT_BACKEND


def test_hackathon_backend_constant() -> None:
    assert HACKATHON_BACKEND == "https://api.hackathon.nepher.ai"
    assert DEFAULT_HACKATHON_BACKEND == HACKATHON_BACKEND


def test_resolve_backend_base() -> None:
    assert resolve_backend_base("account") == ACCOUNT_BACKEND
    assert resolve_backend_base("hackathon") == HACKATHON_BACKEND
