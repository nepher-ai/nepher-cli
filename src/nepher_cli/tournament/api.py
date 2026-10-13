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


class UploadChargeError(RuntimeError):
    """Raised when upload fails due to payment / platform balance."""

    def __init__(self, message: str, *, status_code: int = 402):
        super().__init__(message)
        self.status_code = status_code


def _raise_for_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    msg = (
        parse_error_body(response.text)
        or response.text.strip()
        or f"HTTP {response.status_code}"
    )
    if response.status_code == 402:
        raise UploadChargeError(msg, status_code=402)
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
    seal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /api/v1/agents/upload/verify → parsed JSON token dict.

    The returned dict contains at least ``upload_token`` and ``tournament_id``.
    *seal* is sent only for Hugging Face custody tournaments.
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
    if seal is not None:
        body["seal"] = seal

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
    weights_fingerprint: str | None = None,
) -> dict[str, Any]:
    """POST /api/v1/agents/upload/{tournament_id} (multipart) → response dict.

    Returns at least ``agent_id``; may include ``submission_fee_tao``.
    """
    url = f"{api_url.rstrip('/')}/api/v1/agents/upload/{tournament_id}"
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json",
        "X-Upload-Token": upload_token,
    }
    form = {"miner_hotkey": miner_hotkey, "content_hash": content_hash}
    if weights_fingerprint is not None:
        form["weights_fingerprint"] = weights_fingerprint
    async with httpx.AsyncClient(timeout=httpx.Timeout(_UPLOAD_TIMEOUT)) as client:
        with open(file_path, "rb") as fh:
            response = await client.post(
                url,
                files={"file": (file_path.name, fh, "application/zip")},
                data=form,
                headers=headers,
            )
    _raise_for_error(response)
    data = response.json()
    agent_id = data.get("id") or data.get("agent_id")
    if not agent_id:
        raise RuntimeError(f"No agent ID in upload response: {data}")
    return {
        "agent_id": str(agent_id),
        "submission_fee_tao": data.get("submission_fee_tao"),
        "raw": data,
    }


async def fetch_submission_policy(
    *,
    api_key: str,
    api_url: str,
    tournament_id: str | None = None,
) -> dict[str, Any]:
    """Return ``tournament_id``, ``submission_mode`` and ``base_weight_sha256``.

    Without *tournament_id* the single active tournament is used, matching the
    backend's own auto-selection. ``submission_mode`` is ``inline`` when the
    backend does not send it.
    """
    base = api_url.rstrip("/")
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, headers=_json_headers(api_key)) as client:
        if tournament_id is not None:
            response = await client.get(f"{base}/api/v1/tournaments/{tournament_id}")
            _raise_for_error(response)
            data = response.json()
        else:
            response = await client.get(
                f"{base}/api/v1/tournaments/active/list", params={"subnet": "true"}
            )
            _raise_for_error(response)
            payload = response.json()
            items = payload.get("tournaments", []) if isinstance(payload, dict) else payload
            if len(items) != 1:
                raise RuntimeError(
                    f"{len(items)} active tournaments; pass --tournament-id to choose one"
                )
            data = items[0]
    return {
        "tournament_id": str(data.get("id") or tournament_id or ""),
        "submission_mode": data.get("submission_mode") or "inline",
        "base_weight_sha256": [str(d).lower() for d in data.get("base_weight_sha256") or []],
    }
