"""Shared HTTP helpers."""

from __future__ import annotations

import json
from typing import Any

import httpx


def parse_error_body(text: str) -> str | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("message"):
        return str(data["message"])
    if "error" in data:
        err = data["error"]
        if err == "http_error" and data.get("message"):
            return str(data["message"])
        return str(err) if err is not None else None
    return None


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    return client.request(method, url, json=json_body, timeout=120.0)
