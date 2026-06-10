"""simstore command group — coming soon placeholder."""

from __future__ import annotations

import click
from rich.console import Console

console = Console(stderr=True)

_COMING_SOON = (
    "[bold]SimStore[/bold] is coming soon.\n\n"
    "SimStore will let you browse, purchase, and publish Isaac Lab simulation "
    "assets directly from the command line.\n\n"
    "Follow [link=https://nepher.ai]nepher.ai[/link] for updates."
)


@click.group("simstore")
def simstore() -> None:
    """SimStore — buy and sell Isaac Lab simulation assets. (Coming soon)"""


@simstore.command("status")
def simstore_status() -> None:
    """Show SimStore availability."""
    console.print(_COMING_SOON)


@simstore.result_callback()
def simstore_fallback(result, **kwargs) -> None:
    pass


@simstore.command("browse", hidden=False)
def simstore_browse() -> None:
    """Browse available simulation assets. (Coming soon)"""
    console.print(_COMING_SOON)


@simstore.command("publish", hidden=False)
def simstore_publish() -> None:
    """Publish a simulation asset to SimStore. (Coming soon)"""
    console.print(_COMING_SOON)


@simstore.command("purchase", hidden=False)
def simstore_purchase() -> None:
    """Purchase a simulation asset. (Coming soon)"""
    console.print(_COMING_SOON)
