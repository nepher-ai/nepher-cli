"""Console output for submission quota hints."""

from __future__ import annotations

from nepher_cli.submit import _print_quota_line


def test_print_quota_line_skips_when_missing_fields(capsys) -> None:
    _print_quota_line("X", {})
    assert capsys.readouterr().err == ""


def test_print_quota_line_prints_when_complete(capsys) -> None:
    _print_quota_line(
        "Eligible now",
        {
            "submissions_remaining": 4,
            "max_submissions_per_user": 10,
            "submission_attempts_used": 6,
        },
    )
    err = capsys.readouterr().err
    assert "Eligible now" in err
    assert "4" in err and "10" in err and "6" in err
