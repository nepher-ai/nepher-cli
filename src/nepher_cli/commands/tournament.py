"""tournament command group — list, status, leaderboard, validate, submit."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nepher_cli.config import TOURNAMENT_BACKEND
from nepher_cli.core.credentials import get_auth_headers, get_stored_api_key
from nepher_cli.core.http import parse_error_body
from nepher_cli.tournament.agent_check import check_agent_structure
from nepher_cli.tournament import api as tournament_api
from nepher_cli.tournament.packer import compute_checksum, get_file_size, zip_directory
from nepher_cli.tournament.wallet import prepare_submission_credentials

console = Console(stderr=True)


def _resolve_api_key(api_key: str | None) -> str:
    resolved = api_key or os.environ.get("NEPHER_API_KEY") or get_stored_api_key()
    if not resolved:
        console.print(
            "[red]No API key available.[/red] "
            "Pass [bold]--api-key[/bold] or set [bold]NEPHER_API_KEY[/bold] "
            "or run [bold]npcli account login[/bold] first."
        )
        raise SystemExit(1)
    return resolved


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


def _tournament_timestamp(t: dict[str, Any], key: str) -> int | None:
    val = t.get(key)
    return int(val) if val is not None else None


def _is_submittable(t: dict[str, Any], now: int | None = None) -> bool:
    """True when contest_start_time <= now < contest_end_time."""
    if now is None:
        now = int(time.time())
    start = _tournament_timestamp(t, "contest_start_time")
    end = _tournament_timestamp(t, "contest_end_time")
    if start is None or end is None:
        return False
    return start <= now < end


def _describe_stage(t: dict[str, Any], now: int | None = None) -> str:
    """Human-readable current stage for a tournament."""
    if now is None:
        now = int(time.time())
    cs = _tournament_timestamp(t, "contest_start_time")
    ce = _tournament_timestamp(t, "contest_end_time")
    es = _tournament_timestamp(t, "evaluation_start_time")
    ee = _tournament_timestamp(t, "evaluation_end_time")
    rs = _tournament_timestamp(t, "reward_start_time")
    re_ = _tournament_timestamp(t, "reward_end_time")
    sw = _tournament_timestamp(t, "submit_window_start_time")
    if cs is None or now < cs:
        return "upcoming"
    if re_ is not None and now >= re_:
        return "completed"
    if rs is not None and now >= rs:
        return "reward"
    if ee is not None and now >= ee:
        return "review"
    if es is not None and now >= es:
        return "evaluation"
    if ce is not None and now >= ce:
        return "evaluation"
    if sw is not None and now >= sw:
        return "submit"
    return "contest"


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


_EMPTY = "-"


def _fmt_unix(ts: int | None) -> str:
    if ts is None:
        return _EMPTY
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _fmt_time_range(start: int | None, end: int | None) -> str:
    if start is None and end is None:
        return _EMPTY
    if start is not None and end is not None:
        return f"{_fmt_unix(start)} to {_fmt_unix(end)}"
    return _fmt_unix(start if start is not None else end)


def _fmt_block_range(start: int | None, end: int | None) -> str:
    if start is None and end is None:
        return _EMPTY
    if start is not None and end is not None:
        return f"{start:,} - {end:,}"
    return f"{start or end:,}"


def _status_markup(status: str | None) -> str:
    if not status:
        return _EMPTY
    colors = {"active": "green", "approved": "blue", "cancelled": "red", "completed": "dim"}
    color = colors.get(status.lower(), "white")
    return f"[{color}]{status}[/{color}]"


def _subnet_field(data: dict[str, Any], key: str) -> Any:
    cfg = data.get("subnet_config") or {}
    return data.get(key) if data.get(key) is not None else cfg.get(key)


def _render_tournament_status(data: dict[str, Any]) -> None:
    from rich import print as rprint

    title = _tournament_title(data)
    tid = str(data.get("id", "?"))
    header_lines = [f"[bold]{title}[/bold]", f"[cyan]{tid}[/cyan]"]
    if data.get("subtitle"):
        header_lines.append(f"[dim]{data['subtitle']}[/dim]")
    rprint(Panel("\n".join(header_lines), border_style="cyan", padding=(0, 1)))

    overview = Table(show_header=False, box=None, padding=(0, 2))
    overview.add_column(style="dim", no_wrap=True)
    overview.add_column()
    overview.add_row("Status", _status_markup(data.get("status")))
    overview.add_row("Stage", str(data.get("stage") or _EMPTY))
    if data.get("is_active") is not None:
        active = "[green]yes[/green]" if data.get("is_active") else "[dim]no[/dim]"
        overview.add_row("Active", active)
    overview.add_row("Task", _tournament_task_name(data))
    overview.add_row("Versions", _tournament_versions(data))
    if data.get("difficulty"):
        overview.add_row("Difficulty", str(data["difficulty"]))
    if data.get("tags"):
        overview.add_row("Tags", ", ".join(data["tags"]))
    if data.get("is_featured"):
        overview.add_row("Featured", "[yellow]yes[/yellow]")
    network = _subnet_field(data, "network")
    subnet_uid = _subnet_field(data, "subnet_uid")
    if network is not None:
        overview.add_row("Network", str(network))
    if subnet_uid is not None:
        overview.add_row("Subnet UID", str(subnet_uid))
    if data.get("is_test"):
        overview.add_row("Test mode", "[yellow]yes[/yellow]")
    if data.get("has_public_eval"):
        phase = data.get("current_eval_phase") or _EMPTY
        overview.add_row("Eval phase", str(phase))
    rprint(overview)

    phases = Table(title="Schedule", show_header=True, header_style="bold", box=None, padding=(0, 1))
    phases.add_column("Phase", style="dim", no_wrap=True)
    phases.add_column("Time (UTC)", no_wrap=True)
    phases.add_column("Blocks", justify="right", no_wrap=True)

    phase_rows: list[tuple[str, int | None, int | None, int | None, int | None]] = [
        ("Contest", data.get("contest_start_time"), data.get("contest_end_time"),
         data.get("contest_start_block"), data.get("contest_end_block")),
        ("Submit window", data.get("submit_window_start_time"), data.get("contest_end_time"),
         data.get("submit_window_start_block"), data.get("contest_end_block")),
        ("Evaluation", data.get("evaluation_start_time"), data.get("evaluation_end_time"),
         data.get("evaluation_start_block"), data.get("evaluation_end_block")),
        ("Reward", data.get("reward_start_time"), data.get("reward_end_time"),
         data.get("reward_start_block"), data.get("reward_end_block")),
    ]
    if data.get("has_public_eval") and data.get("public_eval_end_time"):
        phase_rows.insert(2, (
            "Public eval ends",
            None,
            data.get("public_eval_end_time"),
            None,
            None,
        ))

    for label, t_start, t_end, b_start, b_end in phase_rows:
        if t_start is None and t_end is None and b_start is None and b_end is None:
            continue
        time_col = _fmt_unix(t_end) if label == "Public eval ends" else _fmt_time_range(t_start, t_end)
        phases.add_row(label, time_col, _fmt_block_range(b_start, b_end))

    rprint(phases)

    stats = data.get("statistics") or {}
    if stats:
        stats_table = Table(title="Statistics", show_header=False, box=None, padding=(0, 2))
        stats_table.add_column(style="dim", no_wrap=True)
        stats_table.add_column(justify="right")
        for label, key in [
            ("Agents submitted", "agents_count"),
            ("Participants", "participants_count"),
            ("Eligible miners", "eligible_count"),
            ("Validators", "validator_count"),
        ]:
            val = stats.get(key)
            if val is not None:
                stats_table.add_row(label, str(val))
        if stats.get("top_score") is not None:
            stats_table.add_row("Top score", f"{float(stats['top_score']):.4f}")
        if stats.get("average_score") is not None:
            stats_table.add_row("Average score", f"{float(stats['average_score']):.4f}")
        if stats.get("score_phase"):
            stats_table.add_row("Score phase", str(stats["score_phase"]))
        rprint(stats_table)

    eval_cfg = data.get("eval_config") or {}
    if eval_cfg:
        eval_table = Table(title="Evaluation", show_header=False, box=None, padding=(0, 2))
        eval_table.add_column(style="dim", no_wrap=True)
        eval_table.add_column()
        if eval_cfg.get("task_name"):
            eval_table.add_row("Eval task", str(eval_cfg["task_name"]))
        if eval_cfg.get("category"):
            eval_table.add_row("Category", str(eval_cfg["category"]))
        scenes = eval_cfg.get("env_scenes") or []
        if scenes:
            scene_parts = [
                f"{s.get('env_id', '?')}" + (f" (scene {s['scene']})" if s.get("scene") is not None else "")
                for s in scenes
            ]
            eval_table.add_row("Environments", ", ".join(scene_parts))
        for label, key in [
            ("Episodes", "num_episodes"),
            ("Max steps", "max_episode_steps"),
            ("Parallel envs", "num_envs"),
        ]:
            if eval_cfg.get(key) is not None:
                eval_table.add_row(label, str(eval_cfg[key]))
        rprint(eval_table)

    links = Table(title="Repositories", show_header=False, box=None, padding=(0, 2))
    links.add_column(style="dim", no_wrap=True)
    links.add_column()
    has_links = False
    if data.get("task_gh"):
        links.add_row("Task repo", str(data["task_gh"]))
        has_links = True
    if data.get("eval_gh"):
        links.add_row("Eval repo", str(data["eval_gh"]))
        has_links = True
    if has_links:
        rprint(links)

    if data.get("winner_hotkey"):
        winner = Table(title="Winner", show_header=False, box=None, padding=(0, 2))
        winner.add_column(style="dim", no_wrap=True)
        winner.add_column()
        winner.add_row("Hotkey", str(data["winner_hotkey"]))
        if data.get("winner_score") is not None:
            winner.add_row("Score", f"{float(data['winner_score']):.4f}")
        if data.get("winner_agent_id"):
            winner.add_row("Agent ID", str(data["winner_agent_id"]))
        approved = "[green]yes[/green]" if data.get("winner_approved") else "[dim]pending[/dim]"
        winner.add_row("Approved", approved)
        rprint(winner)

    meta_parts: list[str] = []
    if data.get("created_at"):
        meta_parts.append(f"Created {data['created_at']}")
    if data.get("updated_at"):
        meta_parts.append(f"Updated {data['updated_at']}")
    if meta_parts:
        rprint(f"[dim]{' | '.join(meta_parts)}[/dim]")


@click.group("tournament")
def tournament() -> None:
    """Browse tournaments, check leaderboards, validate agents, and submit to Subnet 49."""


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

    _render_tournament_status(data)


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


@tournament.command("check")
@click.option("--path", "agent_path", type=click.Path(), required=True, help="Path to agent directory.")
@click.option("--verbose", "-v", is_flag=True, help="Show warnings for missing recommended files.")
def tournament_check(agent_path: str, verbose: bool) -> None:
    """Check local agent directory structure without submitting.

    Verifies required files (best_policy/best_policy.pt, source/) and warns
    about missing recommended files (scripts/rsl_rl/play.py, etc.).

    No extra dependencies required — runs entirely offline.
    """
    path = Path(agent_path)
    console.print(f"Validating agent at [bold]{path}[/bold]...")

    is_valid, errors, warnings = check_agent_structure(path)

    if warnings and verbose:
        for w in warnings:
            console.print(f"  [yellow]warning:[/yellow] {w}")

    if is_valid:
        console.print("[green]Agent structure is valid.[/green]")
        raise SystemExit(0)
    else:
        console.print("[red]Agent validation failed:[/red]")
        for err in errors:
            console.print(f"  • {err}")
        raise SystemExit(1)


@tournament.command("submit")
@click.option("--path", "agent_path", type=click.Path(), required=True, help="Path to agent directory.")
@click.option("--wallet-name", default="miner", show_default=True, help="Bittensor wallet name.")
@click.option("--wallet-hotkey", default="default", show_default=True, help="Bittensor wallet hotkey.")
@click.option(
    "--api-key", "--apikey", "api_key",
    default=None, envvar="NEPHER_API_KEY", metavar="KEY",
    help="Nepher API key (nepher_...). Identifies your account; falls back to stored credentials.",
)
@click.option("--api-url", default=None, help=f"Tournament API URL (default: {TOURNAMENT_BACKEND}).")
@click.option("--tournament-id", default=None, help="Target tournament ID (required when multiple are active).")
@click.option("--verbose", "-v", is_flag=True)
def tournament_submit(
    agent_path: str,
    wallet_name: str,
    wallet_hotkey: str,
    api_key: str | None,
    api_url: str | None,
    tournament_id: str | None,
    verbose: bool,
) -> None:
    """Submit a trained agent to Bittensor Subnet 49 tournaments.

    Your Nepher account is identified by the API key (--api-key, NEPHER_API_KEY,
    or credentials from npcli account login). The wallet hotkey signs the archive.

    Requires [bold]bittensor[/bold] for wallet signing:
      pip install bittensor
    """
    resolved_key = _resolve_api_key(api_key)
    resolved_url = api_url or TOURNAMENT_BACKEND
    path = Path(agent_path)

    console.print("Checking agent structure...")
    is_valid, errors, warnings = check_agent_structure(path)
    if warnings and verbose:
        for w in warnings:
            console.print(f"  [yellow]warning:[/yellow] {w}")
    if not is_valid:
        console.print("[red]Agent validation failed:[/red]")
        for err in errors:
            console.print(f"  • {err}")
        raise SystemExit(1)
    console.print("[green]Agent structure valid.[/green]")

    async def _run() -> int:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                archive = Path(tmpdir) / "agent.zip"

                console.print("Creating submission archive...")
                zip_directory(path, archive)
                content_hash = compute_checksum(archive)
                file_size = get_file_size(archive)
                if verbose:
                    console.print(
                        f"  [dim]Archive: {file_size:,} bytes, "
                        f"sha256: {content_hash[:16]}...[/dim]"
                    )

                console.print("Signing with wallet...")
                miner_hotkey, public_key, file_info, signature = (
                    prepare_submission_credentials(wallet_name, wallet_hotkey, content_hash)
                )

                console.print("Requesting upload token...")
                token_data = await tournament_api.request_upload_token(
                    api_key=resolved_key,
                    api_url=resolved_url,
                    miner_hotkey=miner_hotkey,
                    public_key=public_key,
                    file_info=file_info,
                    signature=signature,
                    file_size=file_size,
                    tournament_id=tournament_id,
                )
                resolved_tournament_id = token_data["tournament_id"]
                upload_token = token_data["upload_token"]

                console.print("Uploading agent...")
                agent_id = await tournament_api.upload_agent(
                    api_key=resolved_key,
                    api_url=resolved_url,
                    tournament_id=resolved_tournament_id,
                    upload_token=upload_token,
                    miner_hotkey=miner_hotkey,
                    content_hash=content_hash,
                    file_path=archive,
                )

            console.print(
                f"[green]Agent submitted successfully.[/green] "
                f"Agent ID: [bold]{agent_id}[/bold]"
            )
            return 0
        except Exception as e:
            console.print(f"[red]Submission failed:[/red] {e}")
            return 1

    raise SystemExit(asyncio.run(_run()))


@tournament.command("list-active")
@click.option("--api-url", default=None, help=f"Tournament API URL (default: {TOURNAMENT_BACKEND}).")
def tournament_list_active(api_url: str | None) -> None:
    """List active tournaments and whether they accept submissions.

    Public endpoint — no login required.
    """
    base = (api_url or TOURNAMENT_BACKEND).rstrip("/")
    url = f"{base}/api/v1/tournaments/active/list"
    try:
        r = httpx.get(url, headers=_optional_headers(), params={"subnet": "true"}, timeout=30.0)
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

    tournaments: list[dict[str, Any]] = (
        data.get("tournaments", []) if isinstance(data, dict) else data
    )

    if not tournaments:
        console.print("[dim]No active tournaments.[/dim]")
        return

    console.print(f"[bold]{len(tournaments)} active tournament(s):[/bold]")
    for t in tournaments:
        accepting = "[green]yes[/green]" if _is_submittable(t) else "[red]no[/red]"
        console.print(
            f"  {t.get('id', '?')} | {t.get('task_name', '?')} | "
            f"stage={_describe_stage(t)} | accepts_submissions={accepting}"
        )
