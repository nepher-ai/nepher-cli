"""CLI entrypoint — argparse and command dispatch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nepher_cli import __version__
from nepher_cli.config import ACCOUNT_BACKEND, HACKATHON_BACKEND, resolve_backend_base
from nepher_cli.register_coldkey import register_coldkey
from nepher_cli.submit import submit

_EPILOG = f"""\
examples:
  Register a Bittensor coldkey (requires btcli on PATH):
    nepher-cli --service account register-coldkey \\
      --wallet mywallet --apikey nepher_xxxxxxxx

  Submit to a hackathon (folders are zipped automatically):
    nepher-cli --service hackathon submit \\
      --apikey nepher_xxxxxxxx \\
      --title "My entry" \\
      --submission ./my-project \\
      --assets ./my-assets

  Optional listing thumbnail (otherwise an image from --assets is used):
    nepher-cli --service hackathon submit \\
      --apikey nepher_xxxxxxxx \\
      --title "My entry" \\
      --thumbnail ./cover.png \\
      --submission ./my-project \\
      --assets ./my-assets

  When several hackathons accept submissions, pass --hackathon-id:
    nepher-cli --service hackathon submit \\
      --apikey nepher_xxxxxxxx \\
      --hackathon-id 550e8400-e29b-41d4-a716-446655440010 \\
      --title "My entry" \\
      --submission ./my-project \\
      --assets ./my-assets

API keys:
  Create a key at https://accounts.nepher.ai — it must start with nepher_,
  be active, and include Hackathon access when submitting.

services:
  account   {ACCOUNT_BACKEND}
  hackathon {HACKATHON_BACKEND}
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nepher-cli",
        description=(
            "Nepher command-line tools: bind a Bittensor coldkey to your account, "
            "or upload a hackathon project and assets."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "-s",
        "--service",
        required=True,
        choices=("account", "hackathon"),
        help=(
            "Which Nepher API to use: "
            "'account' for register-coldkey, 'hackathon' for submit."
        ),
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    reg = sub.add_parser(
        "register-coldkey",
        help="Bind a Bittensor coldkey to your Nepher account (requires btcli).",
        description=(
            "Request a signing challenge from the account API, sign it with btcli, "
            "and verify the coldkey on your Nepher account. "
            "Run again with a different --wallet to replace an existing coldkey."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    reg.add_argument(
        "--wallet",
        required=True,
        metavar="NAME",
        help="Bittensor wallet name (coldkey). Must exist in your local btcli wallet.",
    )
    reg.add_argument(
        "--apikey",
        required=True,
        metavar="KEY",
        help="Nepher API key (starts with nepher_; from Account → API Keys).",
    )

    subp = sub.add_parser(
        "submit",
        help="Upload project + assets to a hackathon (no coldkey required).",
        description=(
            "Validate and zip your project folder and assets, run preflight checks, "
            "then upload submission.zip and assets.zip. "
            "Omit --hackathon-id when exactly one published event is in the submission phase; "
            "otherwise pass the UUID from your dashboard URL "
            "(/dashboard/hackathons/<UUID>)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subp.add_argument(
        "--apikey",
        required=True,
        metavar="KEY",
        help="Nepher API key (starts with nepher_; Hackathon access required).",
    )
    subp.add_argument(
        "--hackathon-id",
        default=None,
        metavar="UUID",
        dest="hackathon_id",
        help=(
            "Target hackathon UUID. Required when several events are in submission; "
            "optional when only one is open."
        ),
    )
    subp.add_argument(
        "--submission",
        required=True,
        metavar="PATH",
        dest="submission",
        help="Project folder or existing submission.zip (folder is validated and zipped).",
    )
    subp.add_argument(
        "--assets",
        required=True,
        metavar="PATH",
        help="Assets folder or assets.zip (images, videos, and PDFs only).",
    )
    subp.add_argument(
        "--title",
        required=True,
        metavar="TEXT",
        help="Entry title (required, max 200 characters).",
    )
    subp.add_argument(
        "--description",
        default="",
        metavar="TEXT",
        help="Optional Markdown description for your entry page.",
    )
    subp.add_argument(
        "--thumbnail",
        default=None,
        metavar="PATH",
        help="Optional entry thumbnail image (JPEG, PNG, WebP, or GIF).",
    )
    subp.add_argument(
        "--public-source",
        action="store_true",
        help="Opt in to public source download when the event allows it.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.service == "account" and args.command != "register-coldkey":
        parser.error("--service account only supports register-coldkey")
    if args.service == "hackathon" and args.command != "submit":
        parser.error("--service hackathon only supports submit")

    base = resolve_backend_base(args.service)

    if args.command == "register-coldkey":
        return register_coldkey(args.wallet, args.apikey, base)

    return submit(
        args.apikey,
        Path(args.submission),
        Path(args.assets),
        base,
        title=args.title,
        description=args.description,
        thumbnail=Path(args.thumbnail) if args.thumbnail else None,
        public_source=args.public_source,
        hackathon_id=args.hackathon_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
