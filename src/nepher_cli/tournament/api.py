"""Tournament submission API calls — httpx only, no external dependencies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from nepher_cli.core.http import parse_error_body

_DEFAULT_TIMEOUT = 30.0
_UPLOAD_TIMEOUT = 600.0  # 10 min — large agent ZIPs can be slow


def _json_headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _raise_for_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    msg = (
        parse_error_body(response.text)
        or response.text.strip()
        or f"HTTP {response.status_code}"
    )
    raise RuntimeError(msg)


async def request_upload_token(
    *,
    api_key: str,
    api_url: str,
    miner_hotkey: str,
    public_key: str,
    file_info: str,
    signature: str,
    file_size: int,
    tournament_id: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/agents/upload/verify → parsed JSON token dict.

    The returned dict contains at least ``upload_token`` and ``tournament_id``.
    """
    body: dict[str, Any] = {
        "miner_hotkey": miner_hotkey,
        "public_key": public_key,
        "file_info": file_info,
        "signature": signature,
        "file_size": file_size,
    }
    if tournament_id is not None:
        body["tournament_id"] = tournament_id

    url = f"{api_url.rstrip('/')}/api/v1/agents/upload/verify"
    async with httpx.AsyncClient(
        timeout=_DEFAULT_TIMEOUT,
        headers=_json_headers(api_key),
    ) as client:
        response = await client.post(url, json=body)
    _raise_for_error(response)
    return response.json()


async def upload_agent(
    *,
    api_key: str,
    api_url: str,
    tournament_id: str,
    upload_token: str,
    miner_hotkey: str,
    content_hash: str,
    file_path: Path,
) -> str:
    """POST /api/v1/agents/upload/{tournament_id} (multipart) → agent_id string."""
    url = f"{api_url.rstrip('/')}/api/v1/agents/upload/{tournament_id}"
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "X-Upload-Token": upload_token,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(_UPLOAD_TIMEOUT)) as client:
        with open(file_path, "rb") as fh:
            response = await client.post(
                url,
                files={"file": (file_path.name, fh, "application/zip")},
                data={"miner_hotkey": miner_hotkey, "content_hash": content_hash},
                headers=headers,
            )
    _raise_for_error(response)
    data = response.json()
    agent_id = data.get("id") or data.get("agent_id")
    if not agent_id:
        raise RuntimeError(f"No agent ID in upload response: {data}")
    return str(agent_id)
