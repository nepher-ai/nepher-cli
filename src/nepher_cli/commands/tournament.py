"""tournament command group — list, submit-agent, leaderboard, status."""

from __future__ import annotations

import json
from typing import Any

import click
import httpx
from rich.console import Console
from rich.table import Table

from nepher_cli.config import TOURNAMENT_BACKEND
from nepher_cli.credentials import get_auth_headers, get_stored_api_key
from nepher_cli.http_util import parse_error_body

console = Console(stderr=True)


def _base() -> str:
    return TOURNAMENT_BACKEND.rstrip("/")


def _optional_headers() -> dict[str, str]:
    """Use stored credentials when logged in; public endpoints work without auth."""
    h = get_auth_headers(None)
    if not h:
        ak = get_stored_api_key()
        if ak:
            h = {"X-API-Key": ak}
    return h


def _tournament_title(t: dict[str, Any]) -> str:
    return t.get("title") or t.get("subtitle") or t.get("name") or "—"


def _tournament_task_name(t: dict[str, Any]) -> str:
    return t.get("task_name") or "—"


def _tournament_versions(t: dict[str, Any]) -> str:
    task_v = t.get("task_version")
    tourn_v = t.get("tournament_version")
    if task_v is not None and tourn_v is not None:
        return f"{task_v}.{tourn_v}"
    if task_v is not None:
        return str(task_v)
    if tourn_v is not None:
        return str(tourn_v)
    return "—"


@click.group("tournament")
def tournament() -> None:
    """Browse tournaments, check leaderboards, and submit agents."""


@tournament.command("list")
@click.option("--active-only", is_flag=True, help="Show only active tournaments.")
@click.option("--limit", type=int, default=50, show_default=True, help="Maximum tournaments to return.")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
def tournament_list(active_only: bool, limit: int, output_json: bool) -> None:
    """List tournaments.

    Public endpoint — no login required. Stored credentials are used automatically
    when present (e.g. to include admin-only tournaments).
    """
    headers = _optional_headers()
    params: dict[str, Any] = {"limit": limit}
    if active_only:
        params["status"] = "active"
    else:
        params["include_active"] = "true"

    url = f"{_base()}/api/v1/tournaments/list"
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e

    if r.status_code != 200:
        console.print(f"[red]{parse_error_body(r.text) or r.text.strip() or f'HTTP {r.status_code}'}[/red]")
        raise SystemExit(1)

    try:
        data = r.json()
    except Exception:
        console.print("[red]Invalid JSON response.[/red]")
        raise SystemExit(1)

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    items: list[dict[str, Any]] = (
        data if isinstance(data, list) else data.get("tournaments", data.get("results", []))
    )

    if not items:
        console.print("[dim]No tournaments found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title")
    table.add_column("Task", style="dim", no_wrap=True)
    table.add_column("Versions", justify="right", no_wrap=True)
    table.add_column("Status")

    for t in items:
        tid = str(t.get("id", ""))
        table.add_row(
            tid,
            _tournament_title(t),
            _tournament_task_name(t),
            _tournament_versions(t),
            t.get("status") or "—",
        )

    from rich import print as rprint
    rprint(table)
    console.print(f"\n[dim]{len(items)} tournament(s) listed.[/dim]")


@tournament.command("status")
@click.argument("tournament_id")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
def tournament_status(tournament_id: str, output_json: bool) -> None:
    """Show the current status and configuration of a tournament."""
    headers = _optional_headers()
    url = f"{_base()}/api/v1/tournaments/{tournament_id}"
    try:
        r = httpx.get(url, headers=headers, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e

    if r.status_code != 200:
        console.print(f"[red]{parse_error_body(r.text) or r.text.strip() or f'HTTP {r.status_code}'}[/red]")
        raise SystemExit(1)

    try:
        data = r.json()
    except Exception:
        console.print("[red]Invalid JSON response.[/red]")
        raise SystemExit(1)

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    console.print(f"[bold]Tournament:[/bold] {data.get('id', '?')}")
    for label, key in [
        ("Task", "task_name"),
        ("Status", "status"),
        ("Network", "network"),
        ("Subnet UID", "subnet_uid"),
        ("Created at", "created_at"),
    ]:
        val = data.get(key)
        if val is not None:
            console.print(f"  {label}: {val}")


@tournament.command("leaderboard")
@click.argument("tournament_id")
@click.option("--limit", type=int, default=20, show_default=True, help="Number of entries to show.")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
def tournament_leaderboard(tournament_id: str, limit: int, output_json: bool) -> None:
    """Show the score leaderboard for a tournament."""
    headers = _optional_headers()
    url = f"{_base()}/api/v1/scores/leaderboard/{tournament_id}"
    params: dict[str, Any] = {"limit": limit}
    try:
        r = httpx.get(url, headers=headers, params=params, timeout=30.0)
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e

    if r.status_code != 200:
        console.print(f"[red]{parse_error_body(r.text) or r.text.strip() or f'HTTP {r.status_code}'}[/red]")
        raise SystemExit(1)

    try:
        data = r.json()
    except Exception:
        console.print("[red]Invalid JSON response.[/red]")
        raise SystemExit(1)

    if output_json:
        click.echo(json.dumps(data, indent=2))
        return

    scores: list[dict[str, Any]] = (
        data if isinstance(data, list)
        else data.get("entries", data.get("scores", data.get("results", [])))
    )

    if not scores:
        console.print("[dim]No scores found for this tournament.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("Rank", justify="right")
    table.add_column("Miner Hotkey")
    table.add_column("Score", justify="right")
    table.add_column("Agent ID")

    for s in scores[:limit]:
        rank = s.get("rank", "—")
        hotkey = s.get("miner_hotkey") or s.get("hotkey") or "—"
        raw_score = s.get("aggregated_score", s.get("score", 0))
        score = str(round(float(raw_score or 0), 4))
        agent_id = str(s.get("agent_id", "—"))
        table.add_row(str(rank), hotkey, score, agent_id)

    from rich import print as rprint
    rprint(table)


@tournament.command("submit-agent")
@click.option("--path", "agent_path", type=click.Path(), required=True, help="Path to agent directory.")
@click.option("--wallet-name", default="miner", show_default=True)
@click.option("--wallet-hotkey", default="default", show_default=True)
@click.option("--tournament-id", default=None, help="Target tournament ID (required when multiple are active).")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY")
@click.option("--skip-validation", is_flag=True, help="Skip local agent structure validation.")
@click.option("--verbose", "-v", is_flag=True)
def tournament_submit_agent(
    agent_path: str,
    wallet_name: str,
    wallet_hotkey: str,
    tournament_id: str | None,
    api_key: str | None,
    skip_validation: bool,
    verbose: bool,
) -> None:
    """Submit an agent to a tournament (alias for [bold]npcli subnet submit[/bold]).

    Requires [bold]nepher-subnet[/bold] (and bittensor) to be installed.
    """
    from nepher_cli.commands.subnet import subnet_submit
    from click.testing import CliRunner

    args = ["--path", agent_path, "--wallet-name", wallet_name, "--wallet-hotkey", wallet_hotkey]
    if tournament_id:
        args += ["--tournament-id", tournament_id]
    if api_key:
        args += ["--api-key", api_key]
    if skip_validation:
        args.append("--skip-validation")
    if verbose:
        args.append("--verbose")

    ctx = click.get_current_context()
    ctx.invoke(subnet_submit, **{
        "agent_path": agent_path,
        "wallet_name": wallet_name,
        "wallet_hotkey": wallet_hotkey,
        "api_key": api_key,
        "api_url": None,
        "tournament_id": tournament_id,
        "submit_all": False,
        "skip_validation": skip_validation,
        "verbose": verbose,
    })
