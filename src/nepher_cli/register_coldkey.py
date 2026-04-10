"""register-coldkey — challenge, btcli sign, verify."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any

import httpx
from rich.console import Console

from nepher_cli.http_util import parse_error_body, request_json

console = Console(stderr=True)


def _api_paths(base: str) -> tuple[str, str]:
    b = base.rstrip("/")
    return (
        f"{b}/api/v1/account/coldkey/challenge",
        f"{b}/api/v1/account/coldkey/verify",
    )


def validate_api_key_format(api_key: str) -> None:
    if not api_key.startswith("nepher_"):
        console.print(
            "[red]invalid api key format[/red] — keys must start with [bold]nepher_[/bold]. "
            "Copy the key from your Nepher account settings."
        )
        raise SystemExit(1)


def run_btcli_sign(wallet_name: str, message: str) -> dict[str, Any]:
    """Run btcli wallet sign; inherit stdin/stderr so password prompts work."""
    btcli = shutil.which("btcli")
    if not btcli:
        console.print(
            "[red]btcli not found[/red] — install Bittensor ([code]pip install bittensor[/code]) "
            "and ensure [bold]btcli[/bold] is on your PATH."
        )
        raise SystemExit(1)

    cmd = [
        btcli,
        "wallet",
        "sign",
        "--wallet-name",
        wallet_name,
        "--message",
        message,
        "--json-output",
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdin=sys.stdin,
            stderr=sys.stderr,
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as e:
        console.print(f"[red]btcli signing failed[/red] — could not run btcli: {e}")
        raise SystemExit(1) from e

    if proc.returncode != 0:
        out = (proc.stdout or "").strip()
        if "not found" in out.lower() or "does not exist" in out.lower():
            console.print(
                "[red]btcli signing failed — wallet not found[/red]. "
                "Check the wallet name; run [code]btcli wallet list[/code]."
            )
        elif proc.returncode != 0:
            console.print(
                "[red]btcli signing failed[/red] — wrong password or signing error. "
                "Re-run and enter the correct wallet password."
            )
        raise SystemExit(1)

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        console.print("[red]btcli signing failed[/red] — could not parse JSON from btcli stdout.")
        raise SystemExit(1) from None

    for key in ("message", "address", "signature"):
        if key not in data:
            console.print(f"[red]btcli output missing '{key}'[/red]")
            raise SystemExit(1)
    return data


def register_coldkey(wallet: str, api_key: str, base_url: str) -> int:
    validate_api_key_format(api_key)
    challenge_url, verify_url = _api_paths(base_url)

    console.print("Checking your API key and registration status...")
    with httpx.Client() as client:
        try:
            r = request_json(client, "POST", challenge_url, json_body={"api_key": api_key})
        except httpx.RequestError as e:
            console.print(
                "[red]Unable to reach the Nepher backend[/red]. "
                f"Check your network connection. ({e})"
            )
            return 1

    if r.status_code == 200:
        try:
            body = r.json()
        except json.JSONDecodeError:
            console.print("[red]Unexpected response from account backend[/red] (invalid JSON).")
            return 1
        if isinstance(body, dict) and body.get("status") == "already_registered":
            ck = body.get("coldkey", "?")
            console.print(
                f"[green]A coldkey is already registered for this account.[/green]\n"
                f"  Coldkey: [bold]{ck}[/bold]"
            )
            return 0
        msg = body.get("message") if isinstance(body, dict) else None
        if not msg or not isinstance(msg, str):
            console.print("[red]Unexpected challenge response[/red] (missing message).")
            return 1
    else:
        err = parse_error_body(r.text) or r.text.strip() or f"HTTP {r.status_code}"
        console.print(f"[red]{err}[/red]")
        return 1

    console.print(f"Signing with wallet [bold]{wallet}[/bold]...")
    console.print(
        "[dim]btcli may prompt for your wallet password — enter it when asked.[/dim]"
    )
    signed = run_btcli_sign(wallet, msg)

    console.print("Submitting to backend...")
    payload = {"api_key": api_key, "signed_payload": signed}
    with httpx.Client() as client:
        try:
            vr = request_json(client, "POST", verify_url, json_body=payload)
        except httpx.RequestError as e:
            console.print(
                "[red]Unable to reach the Nepher backend[/red]. "
                f"Check your network connection. ({e})"
            )
            return 1

    if vr.status_code == 200:
        try:
            vb = vr.json()
        except json.JSONDecodeError:
            console.print("[red]Unexpected response[/red] from verify (invalid JSON).")
            return 1
        if isinstance(vb, dict):
            st = vb.get("status")
            ck = vb.get("coldkey", "?")
            if st in ("registered", "already_registered"):
                console.print("[green]Coldkey registered successfully.[/green]")
                console.print(f"  Coldkey: [bold]{ck}[/bold]")
                return 0

    err = parse_error_body(vr.text) or vr.text.strip() or f"HTTP {vr.status_code}"
    low = err.lower()
    if "already" in low and "registered" in low:
        console.print(f"[green]{err}[/green]")
        return 0
    console.print(f"[red]{err}[/red]")
    return 1
