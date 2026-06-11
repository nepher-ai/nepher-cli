"""npcli — unified Nepher command-line interface."""

from __future__ import annotations

import click

from nepher_cli import __version__
from nepher_cli.commands.account import account, cmd_login, cmd_logout, cmd_whoami
from nepher_cli.commands.envhub import envhub
from nepher_cli.commands.hackathon import hackathon
from nepher_cli.commands.simstore import simstore
from nepher_cli.commands.tournament import tournament


@click.group(
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
)
@click.version_option(version=__version__, prog_name="npcli")
def main() -> None:
    """npcli — the unified Nepher command-line interface.

    Provides centralized access to all Nepher sub-platforms:

    \b
      login       Log in with a Nepher API key
      whoami      Show the currently authenticated user
      logout      Clear locally stored credentials
      account     API keys and coldkey registration
      tournament  Browse tournaments, submit agents, leaderboards
      envhub      Manage Isaac Lab environment bundles
      hackathon   Browse and submit to hackathons
      simstore    SimStore marketplace (coming soon)

    \b
    Quick start:
      npcli login --api-key nepher_xxxxxxxx
      npcli whoami
      npcli hackathon list
      npcli envhub list
      npcli tournament list

    Run any sub-command with --help for details and examples.

    API keys are created at https://account.nepher.ai (Account > API Keys).
    """


main.add_command(cmd_login, name="login")
main.add_command(cmd_logout, name="logout")
main.add_command(cmd_whoami, name="whoami")
main.add_command(account)
main.add_command(tournament)
main.add_command(envhub)
main.add_command(hackathon)
main.add_command(simstore)


if __name__ == "__main__":
    raise SystemExit(main())
