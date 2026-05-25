"""Production API base URLs for Nepher services."""

from __future__ import annotations

from typing import Literal

Service = Literal["account", "hackathon"]

ACCOUNT_BACKEND = "https://api.accounts.nepher.ai"
HACKATHON_BACKEND = "https://api.hackathon.nepher.ai"

# Backwards-compatible aliases for tests and imports.
DEFAULT_ACCOUNT_BACKEND = ACCOUNT_BACKEND
DEFAULT_HACKATHON_BACKEND = HACKATHON_BACKEND


def resolve_backend_base(service: Service) -> str:
    """Return the API base URL for the given service."""
    if service == "account":
        return ACCOUNT_BACKEND
    return HACKATHON_BACKEND
