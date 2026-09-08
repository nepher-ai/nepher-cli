"""Backend URL resolution."""

from __future__ import annotations

from nepher_cli.config import (
    ACCOUNT_BACKEND,
    DEFAULT_ACCOUNT_BACKEND,
    DEFAULT_HACKATHON_BACKEND,
    DEFAULT_WEBSITE_API,
    ENVHUB_BACKEND,
    HACKATHON_BACKEND,
    TOURNAMENT_BACKEND,
    WEBSITE_API,
    resolve_backend_base,
)


def test_website_api_constant() -> None:
    assert WEBSITE_API == DEFAULT_WEBSITE_API
    assert DEFAULT_WEBSITE_API == "https://api.nepher.ai"


def test_account_backend_constant() -> None:
    assert ACCOUNT_BACKEND == "https://api.nepher.ai/account"
    assert DEFAULT_ACCOUNT_BACKEND == ACCOUNT_BACKEND


def test_hackathon_backend_constant() -> None:
    assert HACKATHON_BACKEND == "https://api.nepher.ai/hackathon"
    assert DEFAULT_HACKATHON_BACKEND == HACKATHON_BACKEND


def test_tournament_and_envhub_backends() -> None:
    assert TOURNAMENT_BACKEND == "https://api.nepher.ai/tournament"
    assert ENVHUB_BACKEND == "https://api.nepher.ai/envhub"


def test_resolve_backend_base() -> None:
    assert resolve_backend_base("account") == ACCOUNT_BACKEND
    assert resolve_backend_base("hackathon") == HACKATHON_BACKEND
    assert resolve_backend_base("tournament") == TOURNAMENT_BACKEND
    assert resolve_backend_base("envhub") == ENVHUB_BACKEND
    assert resolve_backend_base("website") == WEBSITE_API
