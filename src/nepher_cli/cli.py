"""CLI entrypoint — argparse, global --service, hidden --backend."""

from __future__ import annotations

import argparse
import sys

from nepher_cli import __version__
from nepher_cli.config import resolve_backend_base
from nepher_cli.register_coldkey import register_coldkey
from nepher_cli.submit import submit


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nepher-cli",
        description="Nepher command-line tools — account (coldkey) and hackathon (submit; no coldkey required).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "-s",
        "--service",
        required=True,
        choices=("account", "hackathon"),
        help="Which backend integration to use: account or hackathon.",
    )
    p.add_argument(
        "--backend",
        default=None,
        metavar="URL",
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    reg = sub.add_parser(
        "register-coldkey",
        help="Bind a Bittensor coldkey via the account API (requires btcli).",
    )
    reg.add_argument("--wallet", required=True, help="Bittensor wallet name (coldkey).")
    reg.add_argument("--apikey", required=True, help="Nepher API key (identifies your account).")

    subp = sub.add_parser(
        "submit",
        help="Upload submission.zip and assets.zip (pick hackathon if several are open).",
    )
    subp.add_argument("--apikey", required=True, help="Nepher API key.")
    subp.add_argument(
        "--hackathon-id",
        default=None,
        metavar="UUID",
        dest="hackathon_id",
        help="Hackathon UUID when more than one event is accepting submissions.",
    )
    subp.add_argument(
        "--submission",
        required=True,
        metavar="PATH",
        dest="submission",
        help="Path to submission.zip (project source).",
    )
    subp.add_argument(
        "--assets",
        required=True,
        metavar="PATH",
        help="Path to assets.zip (images, videos, PDFs).",
    )
    subp.add_argument(
        "--public-source",
        action="store_true",
        help="Opt in to public source download when rules allow (matches website checkbox).",
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

    base = resolve_backend_base(args.service, args.backend)

    if args.command == "register-coldkey":
        return register_coldkey(args.wallet, args.apikey, base)

    from pathlib import Path

    return submit(
        args.apikey,
        Path(args.submission),
        Path(args.assets),
        base,
        public_source=args.public_source,
        hackathon_id=args.hackathon_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
