"""HTTP helpers."""

from __future__ import annotations

from nepher_cli.core.http import parse_error_body


def test_parse_error_body_json() -> None:
    assert parse_error_body('{"error": "no coldkey registered"}') == "no coldkey registered"


def test_parse_error_body_prefers_message() -> None:
    assert (
        parse_error_body('{"error": "http_error", "message": "Challenge expired"}')
        == "Challenge expired"
    )


def test_parse_error_body_invalid() -> None:
    assert parse_error_body("not json") is None
