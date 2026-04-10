"""Backend base URL resolution (per internal CLI spec)."""

from __future__ import annotations

import os
from typing import Literal

Service = Literal["account", "hackathon"]

# Production defaults (ship in every PyPI release).
DEFAULT_ACCOUNT_BACKEND = "https://api.accounts.nepher.ai"
DEFAULT_HACKATHON_BACKEND = "https://api.hackathon.nepher.ai"


def resolve_backend_base(service: Service, backend_flag: str | None) -> str:
    """Resolve order: --backend > NEPHER_CLI_BACKEND > per-service default."""
    if backend_flag:
        return backend_flag.rstrip("/")
    env = os.environ.get("NEPHER_CLI_BACKEND")
    if env:
        return env.rstrip("/")
    if service == "account":
        return DEFAULT_ACCOUNT_BACKEND
    return DEFAULT_HACKATHON_BACKEND
