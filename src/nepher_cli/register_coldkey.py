"""register-coldkey — challenge, btcli sign, verify."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from typing import Any

import httpx
from rich.console import Console

from nepher_cli.http_util import parse_error_body, request_json

console = Console(stderr=True)
BTCLI_SIGN_TIMEOUT_SECONDS = 120


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


def _extract_btcli_payload(stdout_text: str, original_message: str) -> dict[str, Any] | None:
    """Parse btcli output across json/dict variants and normalize keys."""
    data: dict[str, Any] | None = None

    try:
        parsed = json.loads(stdout_text or "{}")
        if isinstance(parsed, dict):
            data = parsed
    except json.JSONDecodeError:
        data = None

    if data is None:
        try:
            parsed = ast.literal_eval(stdout_text.strip())
            if isinstance(parsed, dict):
                data = parsed
        except (SyntaxError, ValueError):
            data = None

    if data is None:
        matches = list(re.finditer(r"\{.*?\}", stdout_text, flags=re.DOTALL))
        for m in reversed(matches):
            blob = m.group(0)
            try:
                parsed = json.loads(blob)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(blob)
                except (SyntaxError, ValueError):
                    continue
            if isinstance(parsed, dict):
                data = parsed
                break

    if data is None:
        # Fallback for btcli text that mixes prompts and wraps values across lines.
        sig_m = re.search(
            r"""['"]signed_message['"]\s*:\s*['"]([0-9a-fA-F\s]+)['"]""",
            stdout_text,
            flags=re.DOTALL,
        )
        addr_m = re.search(
            r"""['"]signer_address['"]\s*:\s*['"]([1-9A-HJ-NP-Za-km-z]+)['"]""",
            stdout_text,
            flags=re.DOTALL,
        )
        if sig_m and addr_m:
            # Some terminal outputs insert hard wraps in long hex payloads.
            signed_message = re.sub(r"\s+", "", sig_m.group(1))
            data = {
                "signed_message": signed_message,
                "signer_address": addr_m.group(1).strip(),
            }

    if not data:
        return None

    if "signature" not in data and "signed_message" in data:
        data["signature"] = data["signed_message"]
    if "address" not in data and "signer_address" in data:
        data["address"] = data["signer_address"]
    if "message" not in data:
        data["message"] = original_message
    return data


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
        proc = subprocess.Popen(
            cmd,
            stdin=sys.stdin,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=False,
        )
    except OSError as e:
        console.print(f"[red]btcli signing failed[/red] — could not run btcli: {e}")
        raise SystemExit(1) from e

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    def _pump(pipe: Any, sink: list[bytes], echo: bool) -> None:
        if pipe is None:
            return
        try:
            fd = pipe.fileno()
            while True:
                chunk = os.read(fd, 1024)
                if not chunk:
                    break
                sink.append(chunk)
                if echo:
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
        finally:
            pipe.close()

    t_out = threading.Thread(target=_pump, args=(proc.stdout, stdout_chunks, True), daemon=True)
    t_err = threading.Thread(target=_pump, args=(proc.stderr, stderr_chunks, True), daemon=True)
    t_out.start()
    t_err.start()

    try:
        proc.wait(timeout=BTCLI_SIGN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        t_out.join(timeout=1)
        t_err.join(timeout=1)
        raise SystemExit(1)

    t_out.join(timeout=2)
    t_err.join(timeout=2)
    out = b"".join(stdout_chunks).decode("utf-8", errors="replace")

    if proc.returncode != 0:
        raise SystemExit(1)

    data = _extract_btcli_payload(out, message)
    if data is None:
        raise SystemExit(1)

    for key in ("message", "address", "signature"):
        if key not in data:
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
        "[dim]Passing through btcli output and prompts below. "
        "Respond directly in this terminal when btcli asks for input.[/dim]"
    )
    try:
        signed = run_btcli_sign(wallet, msg)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — coldkey registration was not completed.[/yellow]")
        return 130

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
            replaced = vb.get("replaced") is True
            if st == "registered":
                if replaced:
                    console.print("[green]Coldkey updated successfully.[/green]")
                else:
                    console.print("[green]Coldkey registered successfully.[/green]")
                console.print(f"  Coldkey: [bold]{ck}[/bold]")
                return 0
            if st == "already_registered":
                console.print(
                    "[green]This coldkey is already registered on your account.[/green]\n"
                    f"  Coldkey: [bold]{ck}[/bold]"
                )
                return 0

    err = parse_error_body(vr.text) or vr.text.strip() or f"HTTP {vr.status_code}"
    low = err.lower()
    if "already" in low and "registered" in low:
        console.print(f"[green]{err}[/green]")
        return 0
    console.print(f"[red]{err}[/red]")
    return 1
