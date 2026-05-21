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
        help="Upload project + assets (directories zipped automatically; pick hackathon if several are open).",
    )
    subp.add_argument("--apikey", required=True, help="Nepher API key.")
    subp.add_argument(
        "--hackathon-id",
        default=None,
        metavar="UUID",
        dest="hackathon_id",
        help=(
            "Hackathon UUID to submit to. Required when several published events are in the "
            "submission phase; omit when only one is open (preflight picks it). "
            "Copy from the dashboard URL or the list printed on preflight error."
        ),
    )
    subp.add_argument(
        "--submission",
        required=True,
        metavar="DIR",
        dest="submission",
        help="Path to project folder (or submission.zip). Folder is validated and zipped before upload.",
    )
    subp.add_argument(
        "--assets",
        required=True,
        metavar="DIR",
        help="Path to assets folder (or assets.zip): images, videos, PDFs only.",
    )
    subp.add_argument(
        "--title",
        required=True,
        help="Submission title (required, max 200 characters; shown on your entry page).",
    )
    subp.add_argument(
        "--description",
        default="",
        help="Submission description as Markdown (optional; shown on your entry page).",
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
        title=args.title,
        description=args.description,
        public_source=args.public_source,
        hackathon_id=args.hackathon_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
