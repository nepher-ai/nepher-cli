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
    if "detail" in data:
        detail = data["detail"]
        return str(detail) if detail is not None else None
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
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return client.request(method, url, json=json_body, headers=headers, timeout=120.0)


def authed_get(url: str, *, api_key: str | None = None, params: dict[str, Any] | None = None) -> httpx.Response:
    """GET with auth headers resolved from credential store or override."""
    from nepher_cli.core.credentials import get_auth_headers

    headers = get_auth_headers(api_key)
    with httpx.Client() as client:
        return client.get(url, headers=headers, params=params, timeout=60.0)


def authed_post(
    url: str,
    *,
    api_key: str | None = None,
    json_body: dict[str, Any] | None = None,
    data: dict[str, str] | None = None,
    files: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> httpx.Response:
    """POST with auth headers resolved from credential store or override."""
    from nepher_cli.core.credentials import get_auth_headers

    headers = get_auth_headers(api_key)
    with httpx.Client() as client:
        if files is not None:
            return client.post(url, headers=headers, data=data, files=files, timeout=timeout)
        return client.post(url, headers=headers, json=json_body, timeout=timeout)


def authed_delete(url: str, *, api_key: str | None = None) -> httpx.Response:
    """DELETE with auth headers resolved from credential store or override."""
    from nepher_cli.core.credentials import get_auth_headers

    headers = get_auth_headers(api_key)
    with httpx.Client() as client:
        return client.delete(url, headers=headers, timeout=30.0)
