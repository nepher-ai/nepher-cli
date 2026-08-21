"""Root CLI help and version."""

from __future__ import annotations

from importlib.metadata import version as pkg_version

from click.testing import CliRunner

from nepher_cli import __version__
from nepher_cli.cli import main


def test_version_matches_installed_package() -> None:
    installed = pkg_version("nepher-cli")
    assert __version__ == installed

    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert installed in result.output
    assert result.output.strip() == f"npcli, version {installed}"


def test_help_mentions_bittensor_install() -> None:
    result = CliRunner().invoke(main, ["-h"])
    assert result.exit_code == 0
    assert "pip install bittensor-wallet" in result.output
    assert 'pip install "nepher-cli[bittensor]"' in result.output
