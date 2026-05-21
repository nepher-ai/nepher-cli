"""Directory validation, zipping, and asset scans."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from nepher_cli.submit import (
    check_assets_against_limits,
    scan_assets_directory,
    submission_directory_requirement_violations,
    zip_directory,
)


def test_submission_directory_rejects_empty(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    assert submission_directory_requirement_violations(root) == ["submission folder is empty"]


def test_submission_directory_rejects_blocked_exe(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "run.exe").write_bytes(b"x")
    errs = submission_directory_requirement_violations(root)
    assert any("Blocked file type" in e for e in errs)


def test_scan_assets_directory_counts(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.png").write_bytes(b"x")
    (root / "b.mp4").write_bytes(b"y" * 10)
    scan = scan_assets_directory(root)
    assert scan["counts"]["images"] == 1
    assert scan["counts"]["videos"] == 1
    assert scan["unsupported"] == []


def test_scan_assets_directory_rejects_unknown_type(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    (root / "notes.txt").write_text("hi")
    scan = scan_assets_directory(root)
    assert any("Unsupported" in u for u in scan["unsupported"])


def test_zip_directory_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    sub = root / "src"
    sub.mkdir()
    (sub / "main.py").write_text("print('ok')\n")
    dest = tmp_path / "out.zip"
    zip_directory(root, dest)
    with zipfile.ZipFile(dest, "r") as zf:
        names = sorted(zf.namelist())
    assert names == ["src/main.py"]


def test_check_assets_passes_directory_scan(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.png").write_bytes(b"x")
    scan = scan_assets_directory(root)
    limits = {"max_images": 5, "max_videos": 2, "max_image_size_mb": 10}
    check_assets_against_limits(scan, limits)


def test_check_assets_directory_unsupported_exits(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    (root / "readme.txt").write_text("nope")
    scan = scan_assets_directory(root)
    with pytest.raises(SystemExit):
        check_assets_against_limits(scan, {})
