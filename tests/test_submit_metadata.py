"""Submission title/description validation."""

from __future__ import annotations

import pytest

from nepher_cli.commands.hackathon import validate_submission_metadata


def test_validate_metadata_accepts_title_and_description() -> None:
    title, desc = validate_submission_metadata("  My Robot  ", "Hello\n")
    assert title == "My Robot"
    assert desc == "Hello"


def test_validate_metadata_empty_description_ok() -> None:
    title, desc = validate_submission_metadata("Entry", "   ")
    assert title == "Entry"
    assert desc == ""


def test_validate_metadata_rejects_empty_title() -> None:
    with pytest.raises(SystemExit):
        validate_submission_metadata("  ", "notes")


def test_validate_metadata_rejects_long_title() -> None:
    with pytest.raises(SystemExit):
        validate_submission_metadata("x" * 201, "")
