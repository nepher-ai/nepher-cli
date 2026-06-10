"""Archive and checksum helpers — pure Python stdlib, no external dependencies."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

# Names and suffixes excluded from submission archives
_EXCLUDED_NAMES: frozenset[str] = frozenset({
    "__pycache__", ".git", ".gitignore",
    "logs", "outputs", ".env", "venv", ".venv", "node_modules",
})
_EXCLUDED_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo"})


def _is_excluded(path_part: str) -> bool:
    p = Path(path_part)
    return p.name in _EXCLUDED_NAMES or p.suffix in _EXCLUDED_SUFFIXES


def zip_directory(source_dir: Path, output_path: Path) -> None:
    """Create a ZIP archive of *source_dir* at *output_path*.

    Files are added in sorted order for reproducibility. Common
    build artefacts and VCS directories are excluded automatically.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(source_dir)
            if any(_is_excluded(part) for part in rel.parts):
                continue
            zf.write(file_path, rel)


def compute_checksum(file_path: Path) -> str:
    """Return the SHA-256 hex digest of *file_path*."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_file_size(file_path: Path) -> int:
    """Return the size of *file_path* in bytes."""
    return file_path.stat().st_size
