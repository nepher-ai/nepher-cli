"""hackathon submit — validate directories or zips, zip dirs, preflight, upload."""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

from nepher_cli.http_util import parse_error_body, request_json

console = Console(stderr=True)


def _print_quota_line(prefix: str, body: dict[str, Any]) -> None:
    rem = body.get("submissions_remaining")
    max_n = body.get("max_submissions_per_user")
    used = body.get("submission_attempts_used")
    if isinstance(rem, int) and isinstance(max_n, int) and isinstance(used, int):
        console.print(
            f"{prefix}: [bold]{rem}[/bold] of {max_n} upload attempt(s) remaining ({used} used successfully)."
        )


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov"}
PDF_EXTS = {".pdf"}
ALLOWED_ASSET_EXTS = IMAGE_EXTS | VIDEO_EXTS | PDF_EXTS

# Local sanity cap before network (bytes) — server preflight limits override when present.
DEFAULT_MAX_SUBMISSION_ZIP_BYTES = 512 * 1024 * 1024  # 512 MiB

MAX_FILES_IN_SUBMISSION = 20_000
MAX_FILES_IN_ASSETS = 5000
MAX_TOTAL_ASSETS_UNCOMPRESSED = 2 * 1024 * 1024 * 1024  # 2 GiB

BLOCKED_SUFFIXES = (
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".com",
    ".msi",
    ".scr",
    ".pif",
    ".vbs",
)

SECRET_TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".env", ".yaml", ".yml", ".toml", ".md"}
SECRET_PATTERNS = [
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk_live_[a-zA-Z0-9]{20,}"),
    re.compile(rb"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
]


MAX_SUBMISSION_TITLE_LEN = 200


def validate_api_key_format(api_key: str) -> None:
    if not api_key.startswith("nepher_"):
        console.print(
            "[red]invalid api key format[/red] — keys must start with [bold]nepher_[/bold]."
        )
        raise SystemExit(1)


def validate_submission_metadata(title: str, description: str) -> tuple[str, str]:
    """Match hackathon backend ``parse_submission_title_description`` rules."""
    title_stripped = (title or "").strip()
    description_stripped = (description or "").strip()
    if not title_stripped:
        console.print("[red]title is required[/red] — pass [bold]--title[/bold] (max 200 characters).")
        raise SystemExit(1)
    if len(title_stripped) > MAX_SUBMISSION_TITLE_LEN:
        console.print(
            f"[red]title is too long[/red] — {len(title_stripped)} characters "
            f"(max {MAX_SUBMISSION_TITLE_LEN})."
        )
        raise SystemExit(1)
    return title_stripped, description_stripped


def _preflight_url(base: str) -> str:
    return f"{base.rstrip('/')}/api/v1/hackathon/submit/preflight/"


def _upload_url(base: str) -> str:
    return f"{base.rstrip('/')}/api/v1/hackathon/submit/upload/"


def _is_dangerous_path(name: str) -> bool:
    n = name.replace("\\", "/").strip()
    if not n or n.endswith("/"):
        return False
    parts = n.split("/")
    for p in parts:
        if p in ("..", "") or p.startswith(".."):
            return True
    return False


def _suffix(name: str) -> str:
    return Path(name).suffix.lower()


def _require_existing_path(path: Path, label: str) -> None:
    if not path.exists():
        console.print(f"[red]Path not found[/red]: {path}")
        raise SystemExit(1)
    if not path.is_dir() and not path.is_file():
        console.print(
            f"[red]{label} must be a directory or zip file[/red]: {path}"
        )
        raise SystemExit(1)


def _iter_directory_files(root: Path) -> list[tuple[str, Path]]:
    """Return (archive member name, absolute file path) for all regular files under root."""
    root = root.resolve()
    out: list[tuple[str, Path]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            if full.is_symlink():
                continue
            if not full.is_file():
                continue
            rel = full.relative_to(root).as_posix()
            if _is_dangerous_path(rel):
                continue
            out.append((rel, full))
    return out


def zip_directory(root: Path, dest: Path) -> None:
    """Write a deflate zip of all files under root (paths relative to root)."""
    files = _iter_directory_files(root)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, file_path in files:
            zf.write(file_path, arcname)


def submission_zip_requirement_violations(zip_path: Path) -> list[str]:
    reasons: list[str] = []
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile:
        return ["invalid submission.zip"]

    try:
        infos = zf.infolist()
        if not infos:
            return ["submission.zip is empty"]

        nonempty = 0
        for i in infos:
            if i.is_dir():
                continue
            if _is_dangerous_path(i.filename):
                reasons.append(f"Unsafe path (zip-slip risk): {i.filename!r}")
            suf = _suffix(i.filename)
            if suf in BLOCKED_SUFFIXES:
                reasons.append(f"Blocked file type {suf} in archive: {i.filename}")
            if i.file_size > 0:
                nonempty += 1

        if nonempty == 0:
            return ["submission.zip has no non-empty files"]

        if len(infos) > MAX_FILES_IN_SUBMISSION:
            reasons.append(
                f"Too many files in archive ({len(infos)} > {MAX_FILES_IN_SUBMISSION})"
            )
    finally:
        zf.close()

    return reasons[:80]


def submission_zip_secret_findings(zip_path: Path) -> list[str]:
    findings: list[str] = []
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile:
        return []

    try:
        for i in zf.infolist():
            if i.is_dir() or i.file_size > 512_000:
                continue
            suf = _suffix(i.filename)
            if suf not in SECRET_TEXT_SUFFIXES and suf != "":
                continue
            try:
                data = zf.read(i.filename)
            except Exception:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(data):
                    findings.append(
                        f"Possible secret material in {i.filename} — manual review"
                    )
                    break
    finally:
        zf.close()

    return findings[:50]


def submission_directory_requirement_violations(root: Path) -> list[str]:
    reasons: list[str] = []
    files = _iter_directory_files(root)
    if not files:
        return ["submission folder is empty"]

    nonempty = 0
    for rel, path in files:
        if _is_dangerous_path(rel):
            reasons.append(f"Unsafe path: {rel!r}")
        suf = _suffix(rel)
        if suf in BLOCKED_SUFFIXES:
            reasons.append(f"Blocked file type {suf}: {rel}")
        try:
            if path.stat().st_size > 0:
                nonempty += 1
        except OSError:
            continue

    if nonempty == 0:
        return ["submission folder has no non-empty files"]

    if len(files) > MAX_FILES_IN_SUBMISSION:
        reasons.append(
            f"Too many files in submission folder ({len(files)} > {MAX_FILES_IN_SUBMISSION})"
        )

    return reasons[:80]


def submission_directory_secret_findings(root: Path) -> list[str]:
    findings: list[str] = []
    for rel, path in _iter_directory_files(root):
        suf = _suffix(rel)
        if suf not in SECRET_TEXT_SUFFIXES and suf != "":
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 512_000:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(data):
                findings.append(f"Possible secret material in {rel} — manual review")
                break
    return findings[:50]


def _print_requirement_errors(label: str, errors: list[str]) -> None:
    console.print(f"[red]{label} does not meet requirements[/red]:")
    for line in errors[:20]:
        console.print(f"  • {line}")
    if len(errors) > 20:
        console.print(f"  … and {len(errors) - 20} more")


def _assert_zip(path: Path, label: str) -> zipfile.ZipFile:
    if not path.is_file():
        console.print(f"[red]Not a zip file[/red]: {label} ({path})")
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
    unsupported: list[str] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if name.endswith("/"):
            continue
        if _is_dangerous_path(name):
            unsupported.append(f"Unsafe path in assets.zip: {name!r}")
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
        else:
            unsupported.append(f"Unsupported asset type in assets.zip: {name}")
    return {"counts": counts, "sizes": sizes, "unsupported": unsupported}


def scan_assets_directory(root: Path) -> dict[str, Any]:
    counts = {"images": 0, "videos": 0, "pdfs": 0}
    sizes: dict[str, list[tuple[str, int]]] = {"images": [], "videos": [], "pdfs": []}
    unsupported: list[str] = []
    total_uncompressed = 0

    files = _iter_directory_files(root)
    if not files:
        unsupported.append("assets folder is empty")
        return {"counts": counts, "sizes": sizes, "unsupported": unsupported}

    if len(files) > MAX_FILES_IN_ASSETS:
        unsupported.append(
            f"Too many files in assets folder ({len(files)} > {MAX_FILES_IN_ASSETS})"
        )

    for rel, path in files:
        try:
            size = path.stat().st_size
        except OSError as e:
            unsupported.append(f"Could not read {rel}: {e}")
            continue
        total_uncompressed += size
        ext = _suffix(rel)
        if ext in IMAGE_EXTS:
            counts["images"] += 1
            sizes["images"].append((rel, size))
        elif ext in VIDEO_EXTS:
            counts["videos"] += 1
            sizes["videos"].append((rel, size))
        elif ext in PDF_EXTS:
            counts["pdfs"] += 1
            sizes["pdfs"].append((rel, size))
        else:
            unsupported.append(f"Unsupported asset type in assets folder: {rel}")

    if total_uncompressed > MAX_TOTAL_ASSETS_UNCOMPRESSED:
        unsupported.append("assets folder uncompressed size too large")

    return {"counts": counts, "sizes": sizes, "unsupported": unsupported}


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
    unsupported = scan.get("unsupported") or []
    if unsupported:
        console.print("[red]assets do not meet requirements[/red]:")
        for line in unsupported[:20]:
            console.print(f"  • {line}")
        if len(unsupported) > 20:
            console.print(f"  … and {len(unsupported) - 20} more")
        raise SystemExit(1)

    c = scan["counts"]
    max_img = _limit_int(limits, "max_images")
    max_vid = _limit_int(limits, "max_videos")
    max_pdf = _limit_int(limits, "max_pdfs")
    max_img_mb = _limit_int(limits, "max_image_size_mb")
    max_vid_mb = _limit_int(limits, "max_video_size_mb")
    max_pdf_mb = _limit_int(limits, "max_pdf_size_mb")

    if max_img is not None and c["images"] > max_img:
        console.print(
            f"[red]assets exceed image limit[/red]: found {c['images']}, limit is {max_img}."
        )
        raise SystemExit(1)
    if max_vid is not None and c["videos"] > max_vid:
        console.print(
            f"[red]assets exceed video limit[/red]: found {c['videos']}, limit is {max_vid}."
        )
        raise SystemExit(1)
    if max_pdf is not None and c["pdfs"] > max_pdf:
        console.print(
            f"[red]assets exceed PDF limit[/red]: found {c['pdfs']}, limit is {max_pdf}."
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


def _max_submission_zip_bytes(limits: dict[str, Any]) -> int:
    mb = _limit_int(limits, "max_submission_zip_mb")
    if mb is not None and mb > 0:
        return mb * 1024 * 1024
    return DEFAULT_MAX_SUBMISSION_ZIP_BYTES


def _validate_submission_input(path: Path) -> None:
    if path.is_dir():
        req = submission_directory_requirement_violations(path)
        if req:
            _print_requirement_errors("Submission folder", req)
            raise SystemExit(1)
        sec = submission_directory_secret_findings(path)
        if sec:
            _print_requirement_errors("Submission folder", sec)
            raise SystemExit(1)
        return

    zf = _assert_zip(path, "submission")
    try:
        if not _submission_zip_non_empty(zf):
            console.print(
                "[red]submission.zip is empty[/red] — add project files before zipping."
            )
            raise SystemExit(1)
    finally:
        zf.close()

    req = submission_zip_requirement_violations(path)
    if req:
        _print_requirement_errors("submission.zip", req)
        raise SystemExit(1)
    sec = submission_zip_secret_findings(path)
    if sec:
        _print_requirement_errors("submission.zip", sec)
        raise SystemExit(1)


def _scan_assets_input(path: Path) -> dict[str, Any]:
    if path.is_dir():
        return scan_assets_directory(path)
    zf = _assert_zip(path, "assets")
    try:
        return scan_assets_zip(zf)
    finally:
        zf.close()


def _zip_input_to_temp(path: Path, prefix: str) -> Path:
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".zip")
    os.close(fd)
    dest = Path(name)
    console.print(f"Zipping {path.name} → {dest.name}...")
    zip_directory(path, dest)
    return dest


def validate_submission_thumbnail(path: Path, *, max_image_size_mb: int) -> tuple[bytes, str, str]:
    """Return (raw bytes, content_type, filename) or exit on validation failure."""
    if not path.is_file():
        console.print(f"[red]Path not found[/red]: {path}")
        raise SystemExit(1)
    ext = path.suffix.lower()
    ext_to_mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    content_type = ext_to_mime.get(ext)
    if not content_type:
        console.print(
            "[red]Unsupported thumbnail type[/red] — use JPEG, PNG, WebP, or GIF."
        )
        raise SystemExit(1)
    try:
        size = path.stat().st_size
    except OSError as e:
        console.print(f"[red]Could not read thumbnail[/red]: {e}")
        raise SystemExit(1)
    max_bytes = max_image_size_mb * 1024 * 1024
    if size <= 0:
        console.print("[red]Thumbnail file is empty[/red].")
        raise SystemExit(1)
    if size > max_bytes:
        mb_sz = size / (1024 * 1024)
        console.print(
            f"[red]Thumbnail too large[/red]: {mb_sz:.1f} MB, limit is {max_image_size_mb} MB."
        )
        raise SystemExit(1)
    try:
        data = path.read_bytes()
    except OSError as e:
        console.print(f"[red]Could not read thumbnail[/red]: {e}")
        raise SystemExit(1)
    return data, content_type, path.name


def submit(
    api_key: str,
    submission_path: Path,
    assets_path: Path,
    base_url: str,
    *,
    title: str,
    description: str = "",
    thumbnail: Path | None = None,
    public_source: bool = False,
    hackathon_id: str | None = None,
) -> int:
    validate_api_key_format(api_key)
    title_clean, description_clean = validate_submission_metadata(title, description)

    _require_existing_path(submission_path, "submission")
    _require_existing_path(assets_path, "assets")

    console.print("Checking submission...")
    _validate_submission_input(submission_path)

    console.print("Checking assets...")
    assets_scan = _scan_assets_input(assets_path)
    if assets_scan.get("unsupported"):
        check_assets_against_limits(assets_scan, {})

    console.print("Verifying your API key and submission eligibility...")
    pre_url = _preflight_url(base_url)
    json_body: dict[str, Any] = {"api_key": api_key}
    if hackathon_id and str(hackathon_id).strip():
        json_body["hackathon_id"] = str(hackathon_id).strip()
    with httpx.Client() as client:
        try:
            pr = request_json(client, "POST", pre_url, json_body=json_body)
        except httpx.RequestError as e:
            console.print(
                "[red]Unable to reach the Nepher backend[/red]. "
                f"Check your network connection. ({e})"
            )
            return 1

    if pr.status_code != 200:
        err = parse_error_body(pr.text) or pr.text.strip() or f"HTTP {pr.status_code}"
        try:
            err_obj = pr.json()
        except json.JSONDecodeError:
            err_obj = None
        if (
            isinstance(err_obj, dict)
            and err_obj.get("code") == "multiple_hackathons"
            and isinstance(err_obj.get("hackathons"), list)
        ):
            console.print(f"[red]{err}[/red]")
            console.print("[bold]Open submission windows:[/bold]")
            for row in err_obj["hackathons"]:
                if isinstance(row, dict):
                    hid = row.get("id", "?")
                    title = row.get("title", "?")
                    console.print(f"  • [cyan]{hid}[/cyan] — {title}")
            console.print(
                "\n[dim]Re-run with[/dim] [bold]--hackathon-id <UUID>[/bold] [dim]to choose one.[/dim]"
            )
        else:
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

    hid = pre_body.get("hackathon_id")
    htitle = pre_body.get("hackathon_title")
    if hid:
        title_bit = f" — {htitle}" if isinstance(htitle, str) and htitle.strip() else ""
        console.print(f"Hackathon: [bold]{hid}[/bold]{title_bit}")

    limits = pre_body.get("limits")
    if not isinstance(limits, dict):
        console.print("[red]Preflight missing limits.[/red]")
        return 1

    console.print("Validating assets against hackathon limits...")
    check_assets_against_limits(assets_scan, limits)

    thumb_payload: tuple[bytes, str, str] | None = None
    if thumbnail is not None:
        max_img_mb = _limit_int(limits, "max_image_size_mb") or 10
        thumb_payload = validate_submission_thumbnail(thumbnail, max_image_size_mb=max_img_mb)

    _print_quota_line("Eligible now", pre_body)

    cleanup: list[Path] = []
    try:
        if submission_path.is_dir():
            sub_zip = _zip_input_to_temp(submission_path, "nepher-submission-")
            cleanup.append(sub_zip)
        else:
            sub_zip = submission_path

        if assets_path.is_dir():
            ast_zip = _zip_input_to_temp(assets_path, "nepher-assets-")
            cleanup.append(ast_zip)
        else:
            ast_zip = assets_path

        max_sub_bytes = _max_submission_zip_bytes(limits)
        sub_size = sub_zip.stat().st_size
        if sub_size > max_sub_bytes:
            max_mb = max_sub_bytes // (1024 * 1024)
            sub_mb = sub_size / (1024 * 1024)
            console.print(
                f"[red]submission.zip is too large[/red] "
                f"({sub_mb:.1f} MB, max {max_mb} MB)."
            )
            return 1

        ast_size = ast_zip.stat().st_size
        if ast_size > max_sub_bytes:
            max_mb = max_sub_bytes // (1024 * 1024)
            ast_mb = ast_size / (1024 * 1024)
            console.print(
                f"[red]assets.zip is too large[/red] "
                f"({ast_mb:.1f} MB, max {max_mb} MB for this event)."
            )
            return 1

        sub_mb = sub_size / (1024 * 1024)
        ast_mb = ast_size / (1024 * 1024)
        upload_bits = f"submission.zip ({sub_mb:.1f} MB) and assets.zip ({ast_mb:.1f} MB)"
        if thumb_payload:
            upload_bits += f" and thumbnail ({thumb_payload[2]})"
        console.print(f"Uploading {upload_bits}...")

        up_url = _upload_url(base_url)
        data: dict[str, str] = {
            "api_key": api_key,
            "title": title_clean,
            "description": description_clean,
        }
        if hackathon_id and str(hackathon_id).strip():
            data["hackathon_id"] = str(hackathon_id).strip()
        data["submitter_public_source"] = "true" if public_source else "false"

        with httpx.Client() as client:
            try:
                with open(sub_zip, "rb") as sf, open(ast_zip, "rb") as af:
                    files: dict[str, tuple[str, object, str]] = {
                        "submission": ("submission.zip", sf, "application/zip"),
                        "assets": ("assets.zip", af, "application/zip"),
                    }
                    if thumb_payload:
                        raw, mime, fname = thumb_payload
                        files["thumbnail"] = (fname, raw, mime)
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
                _print_quota_line("Remaining after this upload", ub)
                console.print(
                    "\n[dim]Your submission is now being reviewed. "
                    "Check your dashboard for updates.[/dim]"
                )
                return 0

        err = parse_error_body(ur.text) or ur.text.strip() or f"HTTP {ur.status_code}"
        console.print(f"[red]{err}[/red]")
        return 1
    finally:
        for p in cleanup:
            p.unlink(missing_ok=True)
