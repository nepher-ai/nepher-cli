"""EnvHub bundle helpers — safe extraction and zipping (same rules as ``nepher``)."""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath, PureWindowsPath

_ENV_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

EXCLUDED_NAMES = {".git", ".hg", ".svn", "__pycache__", ".DS_Store", ".env", ".venv", "venv"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def safe_env_id(env_id: str) -> str:
    """Return ``env_id`` if it is a single safe path segment, else raise ValueError."""
    if not _ENV_ID_RE.match(env_id) or ".." in env_id:
        raise ValueError(f"Invalid environment ID: {env_id!r}")
    return env_id


def _check_member(dest: Path, name: str) -> None:
    win = PureWindowsPath(name)
    if PurePosixPath(name).is_absolute() or win.is_absolute() or win.drive:
        raise ValueError(f"Unsafe path in bundle: {name!r}")
    if not (dest / name).resolve().is_relative_to(dest):
        raise ValueError(f"Unsafe path in bundle: {name!r}")


def extract_bundle(zip_path: Path, dest_dir: Path) -> None:
    """Extract a bundle into ``dest_dir`` atomically.

    Members that would land outside the destination are rejected, the
    uncompressed size is checked against free disk space, and the result only
    replaces ``dest_dir`` once it contains a root ``manifest.yaml``.
    """
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest_dir.name}.", dir=dest_dir.parent))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()
            root = staging.resolve()
            for member in members:
                _check_member(root, member.filename)
            total = sum(m.file_size for m in members)
            free = shutil.disk_usage(staging).free
            if total > free:
                need, have = total / 1024**3, free / 1024**3
                raise ValueError(f"Bundle needs {need:.2f} GB but only {have:.2f} GB is free")
            zf.extractall(staging, members=members)

        if not (staging / "manifest.yaml").is_file():
            raise ValueError("manifest.yaml not found at the root of the bundle")

        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        staging.rename(dest_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def iter_bundle_files(bundle_dir: Path) -> Iterator[tuple[Path, Path]]:
    """Yield ``(path, archive_name)`` for files to include when zipping a bundle."""
    for path in sorted(bundle_dir.rglob("*")):
        rel = path.relative_to(bundle_dir)
        if any(part in EXCLUDED_NAMES for part in rel.parts):
            continue
        if path.is_file() and path.suffix not in EXCLUDED_SUFFIXES:
            yield path, rel
