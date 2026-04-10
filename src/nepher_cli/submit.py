"""hackathon submit — local zip checks, preflight, assets limits, multipart upload."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

from nepher_cli.http_util import parse_error_body, request_json

console = Console(stderr=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov"}
PDF_EXTS = {".pdf"}

# Local sanity cap before network (bytes) — server remains authoritative.
MAX_SUBMISSION_ZIP_BYTES = 512 * 1024 * 1024  # 512 MiB


def validate_api_key_format(api_key: str) -> None:
    if not api_key.startswith("nepher_"):
        console.print(
            "[red]invalid api key format[/red] — keys must start with [bold]nepher_[/bold]."
        )
        raise SystemExit(1)


def _preflight_url(base: str) -> str:
    return f"{base.rstrip('/')}/api/v1/hackathon/submit/preflight"


def _upload_url(base: str) -> str:
    return f"{base.rstrip('/')}/api/v1/hackathon/submit/upload"


def _assert_zip(path: Path, label: str) -> zipfile.ZipFile:
    if not path.is_file():
        console.print(f"[red]File not found[/red]: {path}")
        raise SystemExit(1)
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile:
        console.print(f"[red]Not a valid zip file[/red]: {label} ({path})")
        raise SystemExit(1) from None
    return zf


def _submission_zip_non_empty(zf: zipfile.ZipFile) -> bool:
    for info in zf.infolist():
        if not info.is_dir() and info.file_size > 0:
            return True
    return False


def scan_assets_zip(zf: zipfile.ZipFile) -> dict[str, Any]:
    """Count files by category; ignore directory entries."""
    counts = {"images": 0, "videos": 0, "pdfs": 0}
    sizes: dict[str, list[tuple[str, int]]] = {"images": [], "videos": [], "pdfs": []}
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if name.endswith("/"):
            continue
        base = Path(name).name
        ext = Path(base).suffix.lower()
        size = info.file_size
        if ext in IMAGE_EXTS:
            counts["images"] += 1
            sizes["images"].append((name, size))
        elif ext in VIDEO_EXTS:
            counts["videos"] += 1
            sizes["videos"].append((name, size))
        elif ext in PDF_EXTS:
            counts["pdfs"] += 1
            sizes["pdfs"].append((name, size))
    return {"counts": counts, "sizes": sizes}


def _limit_int(limits: dict[str, Any], key: str) -> int | None:
    v = limits.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def check_assets_against_limits(
    scan: dict[str, Any],
    limits: dict[str, Any],
) -> None:
    """Raise SystemExit if limits exceeded."""
    c = scan["counts"]
    max_img = _limit_int(limits, "max_images")
    max_vid = _limit_int(limits, "max_videos")
    max_pdf = _limit_int(limits, "max_pdfs")
    max_img_mb = _limit_int(limits, "max_image_size_mb")
    max_vid_mb = _limit_int(limits, "max_video_size_mb")
    max_pdf_mb = _limit_int(limits, "max_pdf_size_mb")

    if max_img is not None and c["images"] > max_img:
        console.print(
            f"[red]assets.zip exceeds image limit[/red]: found {c['images']}, limit is {max_img}."
        )
        raise SystemExit(1)
    if max_vid is not None and c["videos"] > max_vid:
        console.print(
            f"[red]assets.zip exceeds video limit[/red]: found {c['videos']}, limit is {max_vid}."
        )
        raise SystemExit(1)
    if max_pdf is not None and c["pdfs"] > max_pdf:
        console.print(
            f"[red]assets.zip exceeds PDF limit[/red]: found {c['pdfs']}, limit is {max_pdf}."
        )
        raise SystemExit(1)

    mb = 1024 * 1024

    def check_sizes(
        key_mb: int | None,
        pairs: list[tuple[str, int]],
        label: str,
    ) -> None:
        if key_mb is None:
            return
        max_bytes = key_mb * mb
        for name, sz in pairs:
            if sz > max_bytes:
                mb_sz = sz / mb
                console.print(
                    f"[red]{label} too large[/red]: {name} is {mb_sz:.1f} MB, limit is {key_mb} MB."
                )
                raise SystemExit(1)

    sizes = scan["sizes"]
    check_sizes(max_img_mb, sizes["images"], "Image")
    check_sizes(max_vid_mb, sizes["videos"], "Video")
    check_sizes(max_pdf_mb, sizes["pdfs"], "PDF")


def submit(
    api_key: str,
    submission_path: Path,
    assets_path: Path,
    base_url: str,
    *,
    public_source: bool = False,
) -> int:
    validate_api_key_format(api_key)

    console.print("Checking archives...")
    sub_zf = _assert_zip(submission_path, "submission.zip")
    try:
        if not _submission_zip_non_empty(sub_zf):
            console.print("[red]submission.zip is empty[/red] — add project files before zipping.")
            return 1
        sub_size = submission_path.stat().st_size
        if sub_size > MAX_SUBMISSION_ZIP_BYTES:
            max_mb = MAX_SUBMISSION_ZIP_BYTES // (1024 * 1024)
            sub_mb = sub_size / (1024 * 1024)
            console.print(
                f"[red]submission.zip is too large[/red] for local check "
                f"({sub_mb:.1f} MB, max {max_mb} MB)."
            )
            return 1
    finally:
        sub_zf.close()

    ast_zf = _assert_zip(assets_path, "assets.zip")
    try:
        assets_scan = scan_assets_zip(ast_zf)
    finally:
        ast_zf.close()

    console.print("Verifying your API key and submission eligibility...")
    pre_url = _preflight_url(base_url)
    with httpx.Client() as client:
        try:
            pr = request_json(client, "POST", pre_url, json_body={"api_key": api_key})
        except httpx.RequestError as e:
            console.print(
                "[red]Unable to reach the Nepher backend[/red]. "
                f"Check your network connection. ({e})"
            )
            return 1

    if pr.status_code != 200:
        err = parse_error_body(pr.text) or pr.text.strip() or f"HTTP {pr.status_code}"
        console.print(f"[red]{err}[/red]")
        return 1

    try:
        pre_body = pr.json()
    except json.JSONDecodeError:
        console.print("[red]Unexpected preflight response[/red] (invalid JSON).")
        return 1

    if not isinstance(pre_body, dict) or pre_body.get("status") != "ok":
        console.print("[red]Preflight did not return status ok.[/red]")
        return 1

    limits = pre_body.get("limits")
    if not isinstance(limits, dict):
        console.print("[red]Preflight missing limits.[/red]")
        return 1

    console.print("Validating assets.zip against hackathon limits...")
    check_assets_against_limits(assets_scan, limits)

    sub_mb = submission_path.stat().st_size / (1024 * 1024)
    ast_mb = assets_path.stat().st_size / (1024 * 1024)
    console.print(
        f"Uploading submission.zip ({sub_mb:.1f} MB) and assets.zip ({ast_mb:.1f} MB)..."
    )

    up_url = _upload_url(base_url)
    data: dict[str, str] = {"api_key": api_key}
    if public_source:
        data["submitter_public_source"] = "true"
    else:
        data["submitter_public_source"] = "false"

    with httpx.Client() as client:
        try:
            with open(submission_path, "rb") as sf, open(assets_path, "rb") as af:
                files = {
                    "submission": (submission_path.name, sf, "application/zip"),
                    "assets": (assets_path.name, af, "application/zip"),
                }
                ur = client.post(
                    up_url,
                    data=data,
                    files=files,
                    timeout=600.0,
                )
        except OSError as e:
            console.print(f"[red]Could not read zip files[/red]: {e}")
            return 1
        except httpx.RequestError as e:
            console.print(
                "[red]Unable to reach the Nepher backend[/red]. "
                f"Check your network connection. ({e})"
            )
            return 1

    if ur.status_code in (200, 201):
        try:
            ub = ur.json()
        except json.JSONDecodeError:
            console.print("[red]Unexpected upload response[/red] (invalid JSON).")
            return 1
        if isinstance(ub, dict):
            sid = ub.get("submission_id", "?")
            st = ub.get("status", "?")
            msg = ub.get("message", "")
            console.print("[green]Submission uploaded successfully.[/green]")
            console.print(f"  Submission ID: [bold]{sid}[/bold]")
            console.print(f"  Status: {st} (pending review)")
            if msg:
                console.print(f"  {msg}")
            console.print(
                "\n[dim]Your submission is now being reviewed. "
                "Check your dashboard for updates.[/dim]"
            )
            return 0

    err = parse_error_body(ur.text) or ur.text.strip() or f"HTTP {ur.status_code}"
    console.print(f"[red]{err}[/red]")
    return 1
