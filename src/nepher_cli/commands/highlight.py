"""tournament highlight subgroup — manage verified play videos.

Highlights are admin-uploaded videos bound to a submission (``--agent-id``) and an
eval phase. Placement is never supplied here: the platform reads rank and score
from the tournament leaderboard when the highlight is served.
"""

from __future__ import annotations

import json as jsonlib
import mimetypes
from pathlib import Path
from typing import Any

import click
import httpx
from rich.console import Console
from rich.table import Table

from nepher_cli.config import TOURNAMENT_BACKEND
from nepher_cli.core.http import (
    authed_delete,
    authed_get,
    authed_patch,
    authed_post,
    parse_error_body,
)

console = Console(stderr=True)

PHASES = ("public", "private")
STATUSES = ("draft", "published")


def _admin_url(api_url: str | None, path: str = "") -> str:
    return f"{(api_url or TOURNAMENT_BACKEND).rstrip('/')}/api/v1/admin/highlights{path}"


def _handle(response: httpx.Response) -> Any:
    """Raise a friendly SystemExit on failure, else return the decoded body."""
    if response.status_code >= 400:
        console.print(
            f"[red]{parse_error_body(response.text) or response.text.strip() or f'HTTP {response.status_code}'}[/red]"
        )
        raise SystemExit(1)
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        console.print("[red]Invalid JSON response.[/red]")
        raise SystemExit(1)


def _call(fn, *args, **kwargs) -> Any:
    try:
        return _handle(fn(*args, **kwargs))
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e


def _print_highlight(data: dict[str, Any], heading: str) -> None:
    console.print(f"[green]{heading}[/green]")
    for label, key in [
        ("Highlight ID", "id"),
        ("Tournament", "tournament_name"),
        ("Submission", "agent_id"),
        ("Hotkey", "miner_hotkey"),
        ("Phase", "phase"),
        ("Status", "status"),
        ("Rank", "rank"),
    ]:
        value = data.get(key)
        if value is not None:
            console.print(f"  {label:<13}: [bold]{value}[/bold]")


@click.group("highlight")
def highlight() -> None:
    """Manage verified play videos (admin only).

    \b
      list        List highlights, including drafts
      upload      Upload a play video for a submission
      publish     Make a highlight public
      unpublish   Return a highlight to draft
      delete      Remove a highlight and its video
    """


_api_url_option = click.option(
    "--api-url", default=None, help=f"Tournament API URL (default: {TOURNAMENT_BACKEND})."
)
_api_key_option = click.option(
    "--api-key", "--apikey", "api_key",
    default=None, envvar="NEPHER_API_KEY", metavar="KEY",
    help="Nepher API key. Falls back to stored credentials.",
)
_json_option = click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")


@highlight.command("list")
@click.option("--tournament-id", default=None, help="Filter by tournament.")
@click.option("--phase", type=click.Choice(PHASES), default=None, help="Filter by eval phase.")
@click.option("--status", type=click.Choice(STATUSES), default=None, help="Filter by publish state.")
@click.option("--limit", type=int, default=24, show_default=True, help="Highlights per page.")
@_api_key_option
@_api_url_option
@_json_option
def highlight_list(
    tournament_id: str | None,
    phase: str | None,
    status: str | None,
    limit: int,
    api_key: str | None,
    api_url: str | None,
    output_json: bool,
) -> None:
    """List highlights with their live leaderboard placement."""
    params = {
        k: v
        for k, v in {
            "tournament_id": tournament_id,
            "phase": phase,
            "status": status,
            "page_size": limit,
        }.items()
        if v is not None
    }
    data = _call(authed_get, _admin_url(api_url), api_key=api_key, params=params)

    if output_json:
        click.echo(jsonlib.dumps(data, indent=2))
        return

    items: list[dict[str, Any]] = data.get("items", [])
    if not items:
        console.print("[dim]No highlights found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Rank", justify="right")
    table.add_column("Phase", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Hotkey")
    table.add_column("Tournament", style="dim")

    for item in items:
        rank = "winner" if item.get("is_winner") else (item.get("rank") or "—")
        table.add_row(
            str(item.get("id", "")),
            str(rank),
            str(item.get("phase", "—")),
            str(item.get("status", "—")),
            str(item.get("miner_hotkey", "—")),
            str(item.get("tournament_name") or "—"),
        )

    from rich import print as rprint

    rprint(table)
    console.print(f"\n[dim]{len(items)} of {data.get('total', len(items))} highlight(s).[/dim]")


@highlight.command("upload")
@click.option("--tournament-id", required=True, help="Tournament the run belongs to.")
@click.option("--phase", type=click.Choice(PHASES), required=True, help="Eval phase of the run.")
@click.option("--file", "video_path", type=click.Path(exists=True, dir_okay=False), required=True,
              help="Play video (MP4 or WebM, max 100 MB).")
@click.option("--agent-id", default=None, help="Submission the video shows.")
@click.option("--rank", type=int, default=None,
              help="Resolve the submission by its current rank in this phase instead of --agent-id.")
@click.option("--title", default=None, help="Display title.")
@click.option("--poster", "poster_path", type=click.Path(exists=True, dir_okay=False), default=None,
              help="Optional poster image (JPG, PNG, WebP, max 10 MB).")
@click.option("--publish", is_flag=True, help="Publish immediately instead of saving a draft.")
@_api_key_option
@_api_url_option
@_json_option
def highlight_upload(
    tournament_id: str,
    phase: str,
    video_path: str,
    agent_id: str | None,
    rank: int | None,
    title: str | None,
    poster_path: str | None,
    publish: bool,
    api_key: str | None,
    api_url: str | None,
    output_json: bool,
) -> None:
    """Upload a verified play video and bind it to a submission.

    Provide either --agent-id or --rank; the platform stores the resolved
    submission so the card's placement always tracks the leaderboard.
    """
    if not agent_id and rank is None:
        console.print("[red]Provide --agent-id or --rank.[/red]")
        raise SystemExit(1)

    form: dict[str, str] = {
        "tournament_id": tournament_id,
        "phase": phase,
        "publish": str(publish).lower(),
    }
    if agent_id:
        form["agent_id"] = agent_id
    if rank is not None:
        form["rank"] = str(rank)
    if title:
        form["title"] = title

    video = Path(video_path)
    files: dict[str, Any] = {
        "file": (video.name, video.read_bytes(), mimetypes.guess_type(video.name)[0] or "video/mp4"),
    }
    if poster_path:
        poster = Path(poster_path)
        files["poster"] = (
            poster.name,
            poster.read_bytes(),
            mimetypes.guess_type(poster.name)[0] or "image/jpeg",
        )

    console.print("Uploading play video...")
    data = _call(
        authed_post,
        _admin_url(api_url, "/upload"),
        api_key=api_key,
        data=form,
        files=files,
        timeout=600.0,
    )

    if output_json:
        click.echo(jsonlib.dumps(data, indent=2))
        return

    _print_highlight(data, "Highlight published." if publish else "Highlight saved as draft.")


def _set_status(
    highlight_id: str,
    status: str,
    api_key: str | None,
    api_url: str | None,
    output_json: bool,
) -> None:
    data = _call(
        authed_patch,
        _admin_url(api_url, f"/{highlight_id}"),
        api_key=api_key,
        json_body={"status": status},
    )
    if output_json:
        click.echo(jsonlib.dumps(data, indent=2))
        return
    _print_highlight(data, f"Highlight marked {status}.")


@highlight.command("publish")
@click.argument("highlight_id")
@_api_key_option
@_api_url_option
@_json_option
def highlight_publish(
    highlight_id: str, api_key: str | None, api_url: str | None, output_json: bool
) -> None:
    """Publish a draft highlight.

    Final (private-phase) clips stay hidden from the public feed until the
    tournament reaches its review stage.
    """
    _set_status(highlight_id, "published", api_key, api_url, output_json)


@highlight.command("unpublish")
@click.argument("highlight_id")
@_api_key_option
@_api_url_option
@_json_option
def highlight_unpublish(
    highlight_id: str, api_key: str | None, api_url: str | None, output_json: bool
) -> None:
    """Return a published highlight to draft."""
    _set_status(highlight_id, "draft", api_key, api_url, output_json)


@highlight.command("delete")
@click.argument("highlight_id")
@click.option("--keep-media", is_flag=True, help="Keep the video in the Media Library.")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
@_api_key_option
@_api_url_option
def highlight_delete(
    highlight_id: str,
    keep_media: bool,
    yes: bool,
    api_key: str | None,
    api_url: str | None,
) -> None:
    """Delete a highlight and, unless --keep-media, its video."""
    if not yes:
        click.confirm(f"Delete highlight {highlight_id}?", abort=True)

    query = "?keep_media=true" if keep_media else ""
    _call(authed_delete, _admin_url(api_url, f"/{highlight_id}{query}"), api_key=api_key)
    console.print("[green]Highlight deleted.[/green]")
