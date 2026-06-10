"""envhub command group — list, download, upload, cache, view, config.

Talks directly to the envhub-backend REST API.  The standalone ``nepher``
CLI (from the envhub package) is left unchanged; this group provides the
same operations from inside the unified npcli interface.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import click
import httpx
from rich.console import Console

from nepher_cli.config import ENVHUB_BACKEND
from nepher_cli.core.credentials import get_auth_headers, get_stored_api_key
from nepher_cli.core.http import parse_error_body
from nepher_cli.envhub.cache import is_cached_env, list_cached_env_dirs, resolve_cache_dir
from nepher_cli.envhub.config import (
    get_value as get_envhub_config_value,
    list_values as list_envhub_config_values,
    mask_secret as mask_envhub_config_secret,
    parse_config_value,
    reset_config as reset_envhub_config,
    set_value as set_envhub_config_value,
)

console = Console(stderr=True)


def _headers(api_key: str | None) -> dict[str, str]:
    h = get_auth_headers(api_key)
    if not h:
        ak = get_stored_api_key()
        if ak:
            h = {"X-API-Key": ak}
    return h


def _base() -> str:
    return ENVHUB_BACKEND.rstrip("/")


@click.group("envhub")
def envhub() -> None:
    """Manage Isaac Lab simulation environment bundles via EnvHub."""


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@envhub.command("list")
@click.option("--category", default=None, help="Filter by category.")
@click.option("--type", "env_type", type=click.Choice(["usd", "preset"]), default=None, help="Filter by type.")
@click.option("--benchmark", is_flag=True, help="Show only benchmark environments.")
@click.option("--eval-benchmarks", "eval_benchmarks", is_flag=True, help="Show only evaluation benchmarks.")
@click.option("--search", default=None, help="Full-text search query.")
@click.option("--limit", type=int, default=None, help="Maximum number of results.")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON.")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY")
def envhub_list(
    category: str | None,
    env_type: str | None,
    benchmark: bool,
    eval_benchmarks: bool,
    search: str | None,
    limit: int | None,
    output_json: bool,
    api_key: str | None,
) -> None:
    """List available Isaac Lab environments."""
    params: dict[str, Any] = {}
    if category:
        params["category"] = category
    if env_type:
        params["type"] = env_type
    if benchmark:
        params["benchmark"] = "true"
    if search:
        params["search"] = search
    if limit:
        params["limit"] = limit

    endpoint = f"{_base()}/api/v1/envs/eval-benchmarks/" if eval_benchmarks else f"{_base()}/api/v1/envs/"

    headers = _headers(api_key)
    try:
        r = httpx.get(endpoint, headers=headers, params=params, timeout=30.0)
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

    if isinstance(data, list):
        envs = data
    elif isinstance(data, dict):
        envs = data.get("environments", data.get("results", data.get("items", [])))
    else:
        envs = []

    if output_json:
        click.echo(json.dumps(envs, indent=2))
        return

    if not envs:
        console.print("[dim]No environments found.[/dim]")
        return

    console.print(f"[bold]Found {len(envs)} environment(s):[/bold]\n")
    for env in envs:
        click.echo(f"  {env.get('id', 'N/A')}")
        click.echo(f"    Name:     {env.get('original_name', 'N/A')}")
        click.echo(f"    Version:  {env.get('version', 'N/A')}")
        click.echo(f"    Category: {env.get('category', 'N/A')}")
        click.echo(f"    Type:     {env.get('type', 'N/A')}")
        click.echo(f"    Status:   {env.get('status', 'N/A')}")
        if env.get("is_benchmark"):
            click.echo("    Benchmark: Yes")
        if env.get("description"):
            click.echo(f"    Description: {env.get('description')}")
        click.echo()


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


@envhub.command("download")
@click.argument("env_id")
@click.option("--cache-dir", type=click.Path(), default=None, help="Override local cache directory.")
@click.option("--force", is_flag=True, help="Re-download even if already cached.")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY")
def envhub_download(env_id: str, cache_dir: str | None, force: bool, api_key: str | None) -> None:
    """Download an environment bundle and cache it locally.

    The bundle is extracted to ~/.nepher/cache/<env_id>/ by default.
    """
    cache_root = resolve_cache_dir(cache_dir)
    env_cache = cache_root / env_id

    if is_cached_env(env_cache) and not force:
        console.print(f"[dim]Already cached:[/dim] {env_cache}")
        return

    headers = _headers(api_key)
    url = f"{_base()}/api/v1/envs/{env_id}/download"
    console.print(f"Downloading [bold]{env_id}[/bold]...")
    try:
        with httpx.stream("GET", url, headers=headers, timeout=600.0, follow_redirects=True) as r:
            if r.status_code != 200:
                body = r.read().decode(errors="replace")
                console.print(f"[red]{parse_error_body(body) or body.strip() or f'HTTP {r.status_code}'}[/red]")
                raise SystemExit(1)

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                for chunk in r.iter_bytes(chunk_size=65536):
                    tmp.write(chunk)
    except httpx.RequestError as e:
        console.print(f"[red]Network error[/red]: {e}")
        raise SystemExit(1) from e

    console.print("Extracting bundle...")
    env_cache.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(env_cache)
    except zipfile.BadZipFile:
        console.print("[red]Downloaded file is not a valid ZIP archive.[/red]")
        shutil.rmtree(env_cache, ignore_errors=True)
        tmp_path.unlink(missing_ok=True)
        raise SystemExit(1)
    finally:
        tmp_path.unlink(missing_ok=True)

    console.print(f"[green]Downloaded and cached:[/green] {env_cache}")


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


@envhub.command("upload")
@click.argument("path", type=click.Path(exists=True))
@click.option("--category", required=True, help="Environment category (e.g. navigation, manipulation).")
@click.option("--benchmark", is_flag=True, help="Mark as a benchmark environment.")
@click.option("--force", is_flag=True, help="Upload even if a duplicate exists.")
@click.option("--thumbnail", type=click.Path(exists=True), default=None, help="Optional thumbnail image path.")
@click.option("--api-key", "api_key", default=None, envvar="NEPHER_API_KEY")
def envhub_upload(path: str, category: str, benchmark: bool, force: bool, thumbnail: str | None, api_key: str | None) -> None:
    """Upload an Isaac Lab environment bundle.

    PATH must be a directory containing a valid manifest.yaml, or a pre-built
    .zip archive.  Directories are zipped automatically before upload.
    """
    headers = _headers(api_key)
    if not headers:
        console.print("[yellow]Not authenticated.[/yellow] Run [bold]npcli account login[/bold] or pass [bold]--api-key[/bold].")
        raise SystemExit(1)

    bundle_path = Path(path)
    tmp_zip: Path | None = None

    try:
        if bundle_path.is_dir():
            manifest = bundle_path / "manifest.yaml"
            if not manifest.exists():
                console.print("[red]Invalid bundle[/red]: manifest.yaml not found in directory.")
                raise SystemExit(1)
            console.print("Zipping bundle...")
            tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip")
            import os
            os.close(tmp_fd)
            tmp_zip = Path(tmp_name)
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in bundle_path.rglob("*"):
                    if file.is_file():
                        zf.write(file, file.relative_to(bundle_path))
            upload_path = tmp_zip
        else:
            upload_path = bundle_path

        console.print(f"Uploading [bold]{bundle_path.name}[/bold]...")
        data_fields = {"category": category}
        if benchmark:
            data_fields["benchmark"] = "true"
        if force:
            data_fields["force"] = "true"

        with open(upload_path, "rb") as f:
            files: dict[str, Any] = {"file": (upload_path.name, f, "application/zip")}
            if thumbnail:
                thumb_path = Path(thumbnail)
                files["thumbnail"] = (thumb_path.name, open(thumbnail, "rb"), "image/jpeg")

            try:
                r = httpx.post(
                    f"{_base()}/api/v1/envs/",
                    headers=headers,
                    data=data_fields,
                    files=files,
                    timeout=600.0,
                )
            except httpx.RequestError as e:
                console.print(f"[red]Network error[/red]: {e}")
                raise SystemExit(1) from e

        if r.status_code in (200, 201):
            body = r.json()
            console.print("[green]Environment uploaded successfully.[/green]")
            console.print(f"  ID: {body.get('id', '?')}")
        else:
            console.print(f"[red]{parse_error_body(r.text) or r.text.strip() or f'HTTP {r.status_code}'}[/red]")
            raise SystemExit(1)

    finally:
        if tmp_zip and tmp_zip.exists():
            tmp_zip.unlink()


# ---------------------------------------------------------------------------
# cache sub-group
# ---------------------------------------------------------------------------


@envhub.group("cache")
def envhub_cache() -> None:
    """Manage the local environment bundle cache."""


@envhub_cache.command("list")
@click.option("--cache-dir", type=click.Path(), default=None)
def cache_list(cache_dir: str | None) -> None:
    """List locally cached environments."""
    root = resolve_cache_dir(cache_dir)
    entries = list_cached_env_dirs(root)
    if not entries:
        console.print("[dim]No cached environments.[/dim]")
        return

    console.print(f"[bold]Cached environments ({len(entries)}):[/bold]")
    for e in sorted(entries):
        size = sum(f.stat().st_size for f in e.rglob("*") if f.is_file())
        console.print(f"  {e.name}  ({size / 1024 / 1024:.1f} MB)")


@envhub_cache.command("clear")
@click.argument("env_id", required=False)
@click.option("--cache-dir", type=click.Path(), default=None)
def cache_clear(env_id: str | None, cache_dir: str | None) -> None:
    """Clear cache — all environments or a specific one."""
    root = resolve_cache_dir(cache_dir)
    if env_id:
        target = root / env_id
        if target.exists():
            shutil.rmtree(target)
            console.print(f"[green]Cleared cache for[/green] {env_id}")
        else:
            console.print(f"[yellow]{env_id} is not cached.[/yellow]")
    else:
        if root.exists():
            shutil.rmtree(root)
        console.print("[green]Cleared all cached environments.[/green]")


@envhub_cache.command("info")
@click.option("--cache-dir", type=click.Path(), default=None)
def cache_info(cache_dir: str | None) -> None:
    """Show cache size and location."""
    root = resolve_cache_dir(cache_dir)
    console.print(f"Cache directory: {root}")
    if not root.exists():
        console.print("  (empty — nothing cached yet)")
        return

    entries = list_cached_env_dirs(root)
    total = sum(f.stat().st_size for d in entries for f in d.rglob("*") if f.is_file())
    console.print(f"  Environments: {len(entries)}")
    console.print(f"  Total size:   {total / 1024 / 1024:.2f} MB")

    if entries:
        click.echo("\n  Environments:")
        for e in sorted(entries):
            size = sum(f.stat().st_size for f in e.rglob("*") if f.is_file())
            click.echo(f"    {e.name}: {size / 1024 / 1024:.2f} MB")


@envhub_cache.command("migrate")
@click.argument("new_path", type=click.Path())
@click.option("--cache-dir", type=click.Path(), default=None)
def cache_migrate(new_path: str, cache_dir: str | None) -> None:
    """Move the local cache to a new directory."""
    old_root = resolve_cache_dir(cache_dir)
    new_root = Path(new_path)
    if not old_root.exists():
        console.print("[yellow]Nothing to migrate — cache is empty.[/yellow]")
        return
    new_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_root), str(new_root))
    console.print(f"[green]Cache migrated to[/green] {new_root}")


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------


@envhub.command("view")
@click.argument("env_id")
@click.option("--category", default=None, help="Environment category (resolved from manifest if omitted).")
@click.option("--scene", default=None, help="Scene name or index.")
@click.option("--cache-dir", type=click.Path(), default=None)
def envhub_view(env_id: str, category: str | None, scene: str | None, cache_dir: str | None) -> None:
    """View an environment in Isaac Sim (requires isaaclab on PATH).

    The environment must be downloaded first via [bold]npcli envhub download[/bold].
    """
    try:
        from nepher.loader.registry import load_env, load_scene  # type: ignore[import]
    except ImportError:
        console.print(
            "[red]Isaac Lab not available.[/red]\n\n"
            "The [bold]view[/bold] command requires Isaac Lab to be installed in the current Python "
            "environment.  Run it through Isaac Lab's Python interpreter:\n\n"
            "  [bold]isaaclab.bat -p -c 'import nepher_cli; nepher_cli.cli.main()' "
            "envhub view <env_id>[/bold]\n\n"
            "Or install Isaac Lab: https://isaac-sim.github.io/IsaacLab/"
        )
        raise SystemExit(1)

    root = resolve_cache_dir(cache_dir)
    env_path = root / env_id
    if not is_cached_env(env_path):
        console.print(
            f"[yellow]{env_id} is not cached.[/yellow] "
            f"Run [bold]npcli envhub download {env_id}[/bold] first."
        )
        raise SystemExit(1)

    try:
        env = load_env(env_id, category)
    except Exception as e:
        console.print(f"[red]Failed to load environment[/red]: {e}")
        raise SystemExit(1) from e

    if not scene:
        click.echo(f"Environment: {env_id}")
        scenes = env.get_all_scenes() if hasattr(env, "get_all_scenes") else []
        click.echo(f"Scenes ({len(scenes)}):")
        for i, s in enumerate(scenes):
            click.echo(f"  [{i}] {s.name}")
        return

    console.print(f"Launching scene [bold]{scene}[/bold] in Isaac Sim...")
    # Actual rendering requires the full IsaacLab runtime; delegate back to the
    # installed nepher package's view script which handles AppLauncher setup.
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "nepher", "view", env_id, "--scene", scene], check=False)


# ---------------------------------------------------------------------------
# config sub-group
# ---------------------------------------------------------------------------


@envhub.group("config")
def envhub_config() -> None:
    """Manage EnvHub configuration (shared with the ``nepher`` CLI)."""


@envhub_config.command("get")
@click.argument("key")
def config_get(key: str) -> None:
    """Get a configuration value."""
    val = get_envhub_config_value(key)
    if val is None:
        console.print(f"[yellow]Key '{key}' not set.[/yellow]")
    else:
        click.echo(mask_envhub_config_secret(key, val))


@envhub_config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value."""
    parsed = parse_config_value(value)
    set_envhub_config_value(key, parsed)
    display = mask_envhub_config_secret(key, parsed) if isinstance(parsed, str) else parsed
    console.print(f"[green]Set[/green] {key} = {display}")


@envhub_config.command("list")
def config_list() -> None:
    """List EnvHub configuration values."""
    console.print("[bold]Configuration:[/bold]")
    for key, value in list_envhub_config_values().items():
        click.echo(f"  {key}: {value}")


@envhub_config.command("reset")
def config_reset() -> None:
    """Reset configuration to defaults."""
    if reset_envhub_config():
        console.print("[green]Configuration reset to defaults.[/green]")
    else:
        console.print("[dim]No configuration file to reset.[/dim]")
