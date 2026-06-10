"""Production API base URLs for Nepher services."""

from __future__ import annotations

ACCOUNT_BACKEND = "https://account-api.nepher.ai"
HACKATHON_BACKEND = "https://api.hackathon.nepher.ai"
ENVHUB_BACKEND = "https://envhub-api.nepher.ai"
TOURNAMENT_BACKEND = "https://tournament-api.nepher.ai"
SIMSTORE_BACKEND = "https://api.simstore.nepher.ai"  # future

# Backwards-compatible aliases for tests and imports.
DEFAULT_ACCOUNT_BACKEND = ACCOUNT_BACKEND
DEFAULT_HACKATHON_BACKEND = HACKATHON_BACKEND


def resolve_backend_base(service: str) -> str:
    """Return the API base URL for a given service name (backwards compat)."""
    mapping = {
        "account": ACCOUNT_BACKEND,
        "hackathon": HACKATHON_BACKEND,
        "envhub": ENVHUB_BACKEND,
        "tournament": TOURNAMENT_BACKEND,
        "simstore": SIMSTORE_BACKEND,
    }
    return mapping.get(service, ACCOUNT_BACKEND)
