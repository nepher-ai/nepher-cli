"""subnet command group — validate and submit agents to Bittensor Subnet 49.

Delegates to ``nepher_core`` and ``miner`` from the nepher-subnet package when
installed.  All commands fail gracefully with a clear install hint if those
packages are not available in the current environment.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import click
from rich.console import Console

from nepher_cli.config import TOURNAMENT_BACKEND
from nepher_cli.credentials import get_stored_api_key

console = Console(stderr=True)

_NEPHER_CORE_HINT = (
    "The subnet commands require [bold]nepher-subnet[/bold] and its dependencies "
    "(bittensor, nepher_core).\n\n"
    "Install them from the nepher-subnet repository:\n"
    "  [bold]pip install -e path/to/nepher-subnet[/bold]\n\n"
    "Or install bittensor directly:\n"
    "  [bold]pip install bittensor[/bold]"
)


def _require_nepher_core() -> tuple:
    """Return (submit_agent, validate_agent_structure, list_active_tournaments) or exit."""
    try:
        from miner.submit import submit_agent, validate_agent_structure, list_active_tournaments  # type: ignore[import]
        return submit_agent, validate_agent_structure, list_active_tournaments
    except ImportError:
        console.print(f"[red]nepher_core / miner not available.[/red]\n\n{_NEPHER_CORE_HINT}")
        raise SystemExit(1)


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


@click.group("subnet")
def subnet() -> None:
    """Interact with Nepher Bittensor Subnet 49 — validate and submit agents."""


@subnet.command("validate")
@click.option("--path", "agent_path", type=click.Path(), required=True, help="Path to agent directory.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output.")
def subnet_validate(agent_path: str, verbose: bool) -> None:
    """Validate local agent structure without submitting.

    Checks for required files (best_policy/best_policy.pt, source/) and warns
    about missing optional files (scripts/rsl_rl/play.py, etc.).

    Requires [bold]nepher-subnet[/bold] to be installed.
    """
    _, validate_agent_structure, _ = _require_nepher_core()

    path = Path(agent_path)
    console.print(f"Validating agent at [bold]{path}[/bold]...")

    is_valid, errors = validate_agent_structure(path)

    if is_valid:
        console.print("[green]Agent structure is valid.[/green]")
        raise SystemExit(0)
    else:
        console.print("[red]Agent validation failed:[/red]")
        for err in errors:
            console.print(f"  • {err}")
        raise SystemExit(1)


@subnet.command("submit")
@click.option("--path", "agent_path", type=click.Path(), required=True, help="Path to agent directory.")
@click.option("--wallet-name", default="miner", show_default=True, help="Bittensor wallet name.")
@click.option("--wallet-hotkey", default="default", show_default=True, help="Bittensor wallet hotkey.")
@click.option(
    "--api-key",
    default=None,
    envvar="NEPHER_API_KEY",
    help="Nepher API key. Falls back to stored credentials.",
)
@click.option("--api-url", default=None, help=f"Tournament API URL (default: {TOURNAMENT_BACKEND}).")
@click.option("--tournament-id", default=None, help="Target tournament ID (required when multiple are active).")
@click.option("--all", "submit_all", is_flag=True, help="Submit to every active tournament in its submit window.")
@click.option("--skip-validation", is_flag=True, help="Skip local agent structure validation.")
@click.option("--verbose", "-v", is_flag=True)
def subnet_submit(
    agent_path: str,
    wallet_name: str,
    wallet_hotkey: str,
    api_key: str | None,
    api_url: str | None,
    tournament_id: str | None,
    submit_all: bool,
    skip_validation: bool,
    verbose: bool,
) -> None:
    """Submit a trained agent to Bittensor Subnet 49 tournaments.

    Zips the agent directory, signs the archive with your Bittensor hotkey,
    then uploads to the tournament backend.

    Requires [bold]nepher-subnet[/bold] (and bittensor) to be installed.
    """
    submit_agent, validate_agent_structure, list_active_tournaments = _require_nepher_core()

    if submit_all and tournament_id:
        console.print("[red]Use either --all or --tournament-id, not both.[/red]")
        raise SystemExit(1)

    resolved_key = _resolve_api_key(api_key)
    resolved_url = api_url or TOURNAMENT_BACKEND
    path = Path(agent_path)

    if not skip_validation:
        console.print("Validating agent structure...")
        is_valid, errors = validate_agent_structure(path)
        if not is_valid:
            console.print("[red]Agent validation failed:[/red]")
            for err in errors:
                console.print(f"  • {err}")
            raise SystemExit(1)
        console.print("[green]Agent structure valid.[/green]")

    try:
        from nepher_core.utils.logging import setup_logging  # type: ignore[import]
        setup_logging(level="DEBUG" if verbose else "INFO")
    except ImportError:
        pass

    async def _run() -> int:
        if submit_all:
            tournaments = await list_active_tournaments(resolved_key, resolved_url)
            from miner.window import is_submittable  # type: ignore[import]
            targets = [t for t in tournaments if is_submittable(t)]
            if not targets:
                console.print("[red]No active tournaments are currently accepting submissions.[/red]")
                return 1
            results = []
            for t in targets:
                console.print(f"Submitting to [bold]{t.id}[/bold] ({t.task_name})...")
                try:
                    await submit_agent(
                        agent_path=path,
                        wallet_name=wallet_name,
                        wallet_hotkey=wallet_hotkey,
                        api_key=resolved_key,
                        api_url=resolved_url,
                        tournament_id=str(t.id),
                    )
                    results.append((t, True))
                except Exception as e:
                    console.print(f"[red]Submission to {t.id} failed:[/red] {e}")
                    results.append((t, False))
            ok = all(r for _, r in results)
            console.print(f"[{'green' if ok else 'red'}]{sum(r for _, r in results)}/{len(results)} succeeded.[/{'green' if ok else 'red'}]")
            return 0 if ok else 1
        else:
            console.print("Submitting agent...")
            try:
                agent_id = await submit_agent(
                    agent_path=path,
                    wallet_name=wallet_name,
                    wallet_hotkey=wallet_hotkey,
                    api_key=resolved_key,
                    api_url=resolved_url,
                    tournament_id=tournament_id,
                )
                console.print(f"[green]Agent submitted successfully.[/green] Agent ID: [bold]{agent_id}[/bold]")
                return 0
            except Exception as e:
                console.print(f"[red]Submission failed:[/red] {e}")
                return 1

    raise SystemExit(asyncio.run(_run()))


@subnet.command("list-active")
@click.option("--api-key", default=None, envvar="NEPHER_API_KEY")
@click.option("--api-url", default=None)
def subnet_list_active(api_key: str | None, api_url: str | None) -> None:
    """List active tournaments and whether they accept submissions.

    Requires [bold]nepher-subnet[/bold] to be installed.
    """
    _, _, list_active_tournaments = _require_nepher_core()

    resolved_key = _resolve_api_key(api_key)
    resolved_url = api_url or TOURNAMENT_BACKEND

    async def _run() -> int:
        try:
            tournaments = await list_active_tournaments(resolved_key, resolved_url)
        except Exception as e:
            console.print(f"[red]Failed to list tournaments:[/red] {e}")
            return 1

        if not tournaments:
            console.print("[dim]No active tournaments.[/dim]")
            return 0

        try:
            from miner.window import is_submittable, describe_stage  # type: ignore[import]
        except ImportError:
            is_submittable = lambda t: False  # noqa: E731
            describe_stage = lambda t: "unknown"  # noqa: E731

        console.print(f"[bold]{len(tournaments)} active tournament(s):[/bold]")
        for t in tournaments:
            accepting = "[green]yes[/green]" if is_submittable(t) else "[red]no[/red]"
            console.print(
                f"  {t.id} | {getattr(t, 'task_name', '?')} | "
                f"stage={describe_stage(t)} | accepts_submissions={accepting}"
            )
        return 0

    raise SystemExit(asyncio.run(_run()))
