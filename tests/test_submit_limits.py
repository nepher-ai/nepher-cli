"""Assets zip scanning and limit checks."""

from __future__ import annotations

import io
import zipfile

import pytest

from nepher_cli.commands.hackathon import check_assets_against_limits, scan_assets_zip


def _zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return buf.getvalue()


def test_scan_assets_counts() -> None:
    data = _zip_bytes(
        [
            ("a.png", b"x"),
            ("b.JPG", b"yy"),
            ("c.mp4", b"z" * 100),
            ("d.pdf", b"p"),
        ]
    )
    zf = zipfile.ZipFile(io.BytesIO(data), "r")
    try:
        scan = scan_assets_zip(zf)
    finally:
        zf.close()
    assert scan["counts"]["images"] == 2
    assert scan["counts"]["videos"] == 1
    assert scan["counts"]["pdfs"] == 1


def test_check_assets_passes_within_limits() -> None:
    scan = {
        "counts": {"images": 2, "videos": 1, "pdfs": 0},
        "sizes": {
            "images": [("a.png", 100), ("b.png", 200)],
            "videos": [("c.mp4", 1024)],
            "pdfs": [],
        },
    }
    limits = {
        "max_images": 5,
        "max_videos": 2,
        "max_image_size_mb": 10,
        "max_video_size_mb": 200,
    }
    check_assets_against_limits(scan, limits)


def test_check_assets_image_count_exceeds() -> None:
    scan = {
        "counts": {"images": 8, "videos": 0, "pdfs": 0},
        "sizes": {"images": [], "videos": [], "pdfs": []},
    }
    limits = {"max_images": 5}
    with pytest.raises(SystemExit):
        check_assets_against_limits(scan, limits)


def test_check_assets_file_too_large() -> None:
    mb = 1024 * 1024
    scan = {
        "counts": {"images": 1, "videos": 0, "pdfs": 0},
        "sizes": {"images": [("huge.png", 11 * mb)], "videos": [], "pdfs": []},
    }
    limits = {"max_images": 5, "max_image_size_mb": 10}
    with pytest.raises(SystemExit):
        check_assets_against_limits(scan, limits)
