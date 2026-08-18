"""account command group — login, API keys, and coldkey registration.

All commands talk to the account backend (account-api.nepher.ai).
"""

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

import click
import httpx
from rich.console import Console
from rich.table import Table

from nepher_cli.config import ACCOUNT_BACKEND
from nepher_cli.core.credentials import (
    clear_credentials,
    get_auth_headers,
    get_stored_api_key,
    load_credentials,
    save_credentials,
    whoami_from_cache,
)
from nepher_cli.core.http import parse_error_body, request_json

console = Console(stderr=True)

BTCLI_SIGN_TIMEOUT_SECONDS = 120

_WALLET_INSTALL_HINT = (
    "Install the wallet library:\n"
    "  [bold]pip install bittensor-wallet[/bold]\n"
    "  [bold]pip install \"nepher-cli[bittensor]\"[/bold]"
)

_SCALECODEC_CONFLICT_HINT = (
    "[red]btcli cannot start[/red] — [bold]scalecodec[/bold] (py-scale-codec) and "
    "[bold]cyscale[/bold] are both installed and share the same Python namespace.\n\n"
    "This is a known Bittensor CLI conflict. Fix it in this venv:\n\n"
    "  [bold]pip uninstall scalecodec cyscale bt-decode -y[/bold]\n"
    "  [bold]pip install -U cyscale --force-reinstall[/bold]\n\n"
    "If [bold]btcli --version[/bold] still fails:\n\n"
    "  [bold]pip uninstall scalecodec cyscale bt-decode bittensor bittensor-cli -y[/bold]\n"
    "  [bold]pip install -U \"bittensor[cli]\" --force-reinstall[/bold]\n\n"
    "npcli itself only needs [bold]bittensor-wallet[/bold] to sign. Prefer:\n"
    "  [bold]pip install bittensor-wallet[/bold]"
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_auth(api_key: str | None) -> dict[str, str]:
    headers = get_auth_headers(api_key)
    if not headers:
        console.print("[yellow]Not logged in.[/yellow] Run [bold]npcli account login[/bold] first.")
        raise SystemExit(1)
    return headers


def _print_user(user: dict[str, Any]) -> None:
    for label, key in [("Name", "fullname"), ("Email", "email"), ("Role", "role"), ("Status", "status")]:
        val = user.get(key)
        if val:
            console.print(f"  {label}: {val}")
    coldkey = user.get("coldkey")
    if coldkey:
        console.print(f"  Coldkey: {coldkey}")


# ---------------------------------------------------------------------------
# Coldkey core logic
# ---------------------------------------------------------------------------


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


def _installed_distribution_names() -> set[str]:
    try:
        from importlib.metadata import distributions
    except ImportError:  # pragma: no cover
        return set()
    names: set[str] = set()
    for dist in distributions():
        raw = dist.metadata.get("Name") or dist.metadata.get("name") or ""
        if raw:
            names.add(raw.lower().replace("_", "-"))
    return names


def has_scalecodec_cyscale_conflict(names: set[str] | None = None) -> bool:
    """True when both SCALE codec packages occupy the ``scalecodec`` namespace."""
    installed = names if names is not None else _installed_distribution_names()
    has_legacy = "scalecodec" in installed or "py-scale-codec" in installed
    return has_legacy and "cyscale" in installed


def _looks_like_scalecodec_conflict(text: str) -> bool:
    low = text.lower()
    return "conflict detected" in low and "scalecodec" in low and "cyscale" in low


def _signature_to_hex(sig: Any) -> str:
    if isinstance(sig, (bytes, bytearray)):
        return bytes(sig).hex()
    text = str(sig).strip()
    if text.startswith(("0x", "0X")):
        return text[2:]
    return text


def _sign_with_bittensor_wallet(wallet_name: str, message: str) -> dict[str, Any] | None:
    """Sign with ``bittensor_wallet`` (no btcli / ASI import). None if not installed."""
    try:
        from bittensor_wallet import Wallet  # type: ignore[import-untyped]
    except ImportError:
        return None
    except RuntimeError as e:
        if _looks_like_scalecodec_conflict(str(e)):
            console.print(_SCALECODEC_CONFLICT_HINT)
            raise SystemExit(1) from e
        raise

    wallet = Wallet(name=wallet_name)
    if not wallet.coldkey_file.exists_on_device():
        console.print(
            f"[red]Coldkey not found[/red] for wallet [bold]{wallet_name}[/bold]. "
            "Check the name with [bold]btcli wallet list[/bold]."
        )
        raise SystemExit(1)

    console.print("[dim]Enter the coldkey password if prompted.[/dim]")
    try:
        keypair = wallet.coldkey
    except Exception as e:
        console.print(
            f"[red]Could not unlock coldkey[/red] for wallet [bold]{wallet_name}[/bold]: {e}"
        )
        raise SystemExit(1) from e

    sig_hex = _signature_to_hex(keypair.sign(message.encode("utf-8")))
    return {
        "message": message,
        "address": keypair.ss58_address,
        "signature": sig_hex,
    }


def sign_coldkey_challenge(wallet_name: str, message: str) -> dict[str, Any]:
    """Sign a coldkey challenge with bittensor_wallet, falling back to btcli."""
    signed = _sign_with_bittensor_wallet(wallet_name, message)
    if signed is not None:
        return signed
    return run_btcli_sign(wallet_name, message)


def run_btcli_sign(wallet_name: str, message: str) -> dict[str, Any]:
    """Run btcli wallet sign; inherit stdin/stderr so password prompts work."""
    btcli = shutil.which("btcli")
    if not btcli:
        console.print(
            "[red]bittensor-wallet not installed[/red] and [bold]btcli[/bold] is not on PATH.\n\n"
            f"{_WALLET_INSTALL_HINT}"
        )
        raise SystemExit(1)

    if has_scalecodec_cyscale_conflict():
        console.print(_SCALECODEC_CONFLICT_HINT)
        raise SystemExit(1)

    cmd = [btcli, "wallet", "sign", "--wallet-name", wallet_name, "--message", message, "--json-output"]
    try:
        proc = subprocess.Popen(cmd, stdin=sys.stdin, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=False)
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

    err = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    if proc.returncode != 0:
        if _looks_like_scalecodec_conflict(out + err):
            console.print(_SCALECODEC_CONFLICT_HINT)
        raise SystemExit(1)

    data = _extract_btcli_payload(out, message)
    if data is None:
        raise SystemExit(1)

    for key in ("message", "address", "signature"):
        if key not in data:
            raise SystemExit(1)
    return data


def register_coldkey(wallet: str, api_key: str, base_url: str) -> int:
    """Execute the coldkey challenge/sign/verify flow. Returns exit code."""
    validate_api_key_format(api_key)
    challenge_url, verify_url = _api_paths(base_url)

    console.print("Checking your API key and registration status...")
    with httpx.Client() as client:
        try:
            r = request_json(client, "POST", challenge_url, json_body={"api_key": api_key})
        except httpx.RequestError as e:
            console.print(f"[red]Unable to reach the Nepher backend[/red]. Check your network connection. ({e})")
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
    try:
        signed = sign_coldkey_challenge(wallet, msg)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — coldkey registration was not completed.[/yellow]")
        return 130

    console.print("Submitting to backend...")
    payload = {"api_key": api_key, "signed_payload": signed}
    with httpx.Client() as client:
        try:
            vr = request_json(client, "POST", verify_url, json_body=payload)
        except httpx.RequestError as e:
            console.print(f"[red]Unable to reach the Nepher backend[/red]. Check your network connection. ({e})")
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
                console.print("[green]Coldkey updated successfully.[/green]" if replaced else "[green]Coldkey registered successfully.[/green]")
                console.print(f"  Coldkey: [bold]{ck}[/bold]")
                return 0
            if st == "already_registered":
                console.print(f"[green]This coldkey is already registered on your account.[/green]\n  Coldkey: [bold]{ck}[/bold]")
                return 0

    err = parse_error_body(vr.text) or vr.text.strip() or f"HTTP {vr.status_code}"
    low = err.lower()
    if "already" in low and "registered" in low:
        console.print(f"[green]{err}[/green]")
        return 0
    console.print(f"[red]{err}[/red]")
    return 1


# ---------------------------------------------------------------------------
# Click command group
# ---------------------------------------------------------------------------


@click.group("account")
def account() -> None:
    """Manage your Nepher account — login, API keys, and coldkey registration."""


# ── Auth ────────────────────────────────────────────────────────────────────


@account.command("login")
@click.option(
    "--api-key", "api_key",
    default=None, envvar="NEPHER_API_KEY",
    help="Nepher API key (nepher_...). Prompted if omitted.",
)
def cmd_login(api_key: str | None) -> None:
    """Log in with a Nepher API key and store credentials locally.

    Credentials are saved to ~/.nepher/credentials.json (tokens are stored in
    the system keyring when available). After login, all npcli commands
    authenticate automatically without requiring --api-key on every call.
    """
    if not api_key:
        api_key = click.prompt("Nepher API key", hide_input=True)
    api_key = (api_key or "").strip()

    if not api_key.startswith("nepher_"):
        console.print("[red]Invalid API key format[/red] — keys must start with [bold]nepher_[/bold].")
        raise SystemExit(1)

    console.print("Authenticating...")
    url = f"{ACCOUNT_BACKEND.rstrip('/')}/api/v1/auth/cli-login"
    try:
        r = httpx.post(url, json={"api_key": api_key}, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Unable to reach the Nepher backend[/red] ({e}).")
        raise SystemExit(1) from e

    if r.status_code != 200:
        err = parse_error_body(r.text) or r.text.strip() or f"HTTP {r.status_code}"
        console.print(f"[red]{err}[/red]")
        raise SystemExit(1)

    try:
        body = r.json()
    except Exception:
        console.print("[red]Unexpected response from account backend (invalid JSON).[/red]")
        raise SystemExit(1)

    save_credentials(
        api_key=api_key,
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        expires_in=body.get("expires_in", 86400),
        user=body.get("user", {}),
    )

    user = body.get("user", {})
    console.print("[green]Logged in successfully.[/green]")
    if user.get("fullname"):
        console.print(f"  Name:  [bold]{user['fullname']}[/bold]")
    if user.get("email"):
        console.print(f"  Email: {user['email']}")
    if user.get("role"):
        console.print(f"  Role:  {user['role']}")


@account.command("logout")
def cmd_logout() -> None:
    """Clear locally stored credentials."""
    clear_credentials()
    console.print("[green]Logged out — credentials cleared.[/green]")


@account.command("whoami")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY", help="Override stored credentials.")
def cmd_whoami(api_key: str | None) -> None:
    """Show the currently authenticated user.

    Uses cached user data when available; falls back to a live API call.
    """
    if not api_key:
        cached = whoami_from_cache()
        if cached:
            console.print("[bold]Current user (cached)[/bold]")
            _print_user(cached)
            return

    headers = _require_auth(api_key)
    url = f"{ACCOUNT_BACKEND.rstrip('/')}/api/v1/users/me"
    try:
        r = httpx.get(url, headers=headers, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Unable to reach the Nepher backend[/red] ({e}).")
        raise SystemExit(1) from e

    if r.status_code != 200:
        console.print(f"[red]{parse_error_body(r.text) or f'HTTP {r.status_code}'}[/red]")
        raise SystemExit(1)

    try:
        user = r.json()
    except Exception:
        console.print("[red]Unexpected response (invalid JSON).[/red]")
        raise SystemExit(1)

    console.print("[bold]Current user[/bold]")
    _print_user(user)


# ── API keys ─────────────────────────────────────────────────────────────────


@account.group("api-keys")
def api_keys() -> None:
    """Manage Nepher API keys."""


@api_keys.command("list")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY")
def api_keys_list(api_key: str | None) -> None:
    """List your API keys."""
    headers = _require_auth(api_key)
    url = f"{ACCOUNT_BACKEND.rstrip('/')}/api/v1/api-keys"
    try:
        r = httpx.get(url, headers=headers, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e

    if r.status_code != 200:
        console.print(f"[red]{parse_error_body(r.text) or r.text.strip() or f'HTTP {r.status_code}'}[/red]")
        raise SystemExit(1)

    data = r.json()
    keys: list[dict[str, Any]] = data if isinstance(data, list) else data.get("api_keys", [])

    if not keys:
        console.print("[dim]No API keys found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Platforms")
    table.add_column("Expires")
    table.add_column("Active")

    for k in keys:
        platforms = ", ".join(k.get("platforms") or []) or "all"
        active = "[green]yes[/green]" if k.get("is_active") else "[red]no[/red]"
        table.add_row(str(k.get("id", "")), k.get("name") or "", platforms, str(k.get("expires_at") or "never"), active)

    from rich import print as rprint
    rprint(table)


@api_keys.command("create")
@click.option("--name", required=True, help="Human-readable label for the key.")
@click.option(
    "--platform", "platforms", multiple=True,
    help="Platform access to grant (envhub, tournament, hackertone, simstore). Repeat for multiple. Omit for all.",
)
@click.option("--expires-at", default=None, help="Expiry in ISO 8601 (e.g. 2027-01-01T00:00:00Z).")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY")
def api_keys_create(name: str, platforms: tuple[str, ...], expires_at: str | None, api_key: str | None) -> None:
    """Create a new API key."""
    headers = _require_auth(api_key)
    payload: dict[str, Any] = {"name": name}
    if platforms:
        payload["platforms"] = list(platforms)
    if expires_at:
        payload["expires_at"] = expires_at

    url = f"{ACCOUNT_BACKEND.rstrip('/')}/api/v1/api-keys"
    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e

    if r.status_code not in (200, 201):
        console.print(f"[red]{parse_error_body(r.text) or r.text.strip() or f'HTTP {r.status_code}'}[/red]")
        raise SystemExit(1)

    body = r.json()
    console.print("[green]API key created.[/green]")
    console.print(f"  Key: [bold]{body.get('api_key') or body.get('key', '?')}[/bold]")
    console.print("  [dim]Copy this key — it will not be shown again.[/dim]")
    if body.get("id"):
        console.print(f"  ID: {body['id']}")


@api_keys.command("revoke")
@click.argument("key_id")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY")
def api_keys_revoke(key_id: str, api_key: str | None) -> None:
    """Revoke (delete) an API key by its ID."""
    headers = _require_auth(api_key)
    url = f"{ACCOUNT_BACKEND.rstrip('/')}/api/v1/api-keys/{key_id}"
    try:
        r = httpx.delete(url, headers=headers, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e

    if r.status_code in (200, 204):
        console.print("[green]API key revoked.[/green]")
    else:
        console.print(f"[red]{parse_error_body(r.text) or r.text.strip() or f'HTTP {r.status_code}'}[/red]")
        raise SystemExit(1)


# ── Coldkey ──────────────────────────────────────────────────────────────────


@account.command("register-coldkey")
@click.option("--wallet", required=True, metavar="NAME", help="Bittensor wallet name. Must exist in your local btcli wallet.")
@click.option(
    "--api-key", "--apikey", "api_key",
    default=None, envvar="NEPHER_API_KEY", metavar="KEY",
    help="Nepher API key (nepher_...). Falls back to stored credentials.",
)
def cmd_register_coldkey(wallet: str, api_key: str | None) -> None:
    """Bind or replace the Bittensor coldkey on your Nepher account.

    Requires bittensor-wallet (or btcli on PATH). Run the same command
    with a different --wallet to replace an existing coldkey.
    """
    resolved_key = api_key or get_stored_api_key()
    if not resolved_key:
        raise SystemExit("No API key available. Pass --api-key or run 'npcli account login' first.")
    raise SystemExit(register_coldkey(wallet, resolved_key, ACCOUNT_BACKEND))
