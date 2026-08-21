"""Production API base URLs for Nepher services."""

from __future__ import annotations

import os

# Unified public API host (embedded product mounts). SimStore stays separate.
DEFAULT_WEBSITE_API = "https://api.nepher.ai"
SIMSTORE_BACKEND_DEFAULT = "https://api.simstore.nepher.ai"


def website_api_base() -> str:
    """Return the unified API root, overridable via NEPHER_API_URL."""
    return (os.environ.get("NEPHER_API_URL") or DEFAULT_WEBSITE_API).rstrip("/")


def _mount(path: str) -> str:
    return f"{website_api_base()}/{path.strip('/')}"


WEBSITE_API = website_api_base()
ACCOUNT_BACKEND = os.environ.get("NEPHER_ACCOUNT_API_URL") or _mount("account")
HACKATHON_BACKEND = os.environ.get("NEPHER_HACKATHON_API_URL") or _mount("hackathon")
ENVHUB_BACKEND = (
    os.environ.get("NEPHER_ENVHUB_API_URL")
    or os.environ.get("ENVHUB_API_URL")
    or _mount("envhub")
)
TOURNAMENT_BACKEND = os.environ.get("NEPHER_TOURNAMENT_API_URL") or _mount("tournament")
SIMSTORE_BACKEND = os.environ.get("NEPHER_SIMSTORE_API_URL") or SIMSTORE_BACKEND_DEFAULT

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
        "website": WEBSITE_API,
    }
    return mapping.get(service, ACCOUNT_BACKEND)
