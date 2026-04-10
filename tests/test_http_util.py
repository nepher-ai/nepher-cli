"""HTTP helpers."""

from __future__ import annotations

from nepher_cli.http_util import parse_error_body


def test_parse_error_body_json() -> None:
    assert parse_error_body('{"error": "no coldkey registered"}') == "no coldkey registered"


def test_parse_error_body_invalid() -> None:
    assert parse_error_body("not json") is None
