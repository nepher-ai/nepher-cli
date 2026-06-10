"""Bittensor wallet operations — lazy import so bittensor is an optional dependency."""

from __future__ import annotations

import time

_BITTENSOR_HINT = (
    "Agent submission requires [bold]bittensor[/bold] for wallet signing.\n\n"
    "Install it with:\n"
    "  [bold]pip install bittensor[/bold]\n\n"
    "Or if you installed nepher-cli via pip:\n"
    "  [bold]pip install \"nepher-cli[bittensor]\"[/bold]"
)


def _require_wallet_class():
    """Return the ``bittensor_wallet.Wallet`` class or exit with a clear error.

    ``bittensor_wallet`` is a standalone package that is installed automatically
    as a dependency of ``bittensor``. Importing it directly keeps the check
    lightweight — we do not need the full bittensor package at import time.
    """
    try:
        from bittensor_wallet import Wallet  # type: ignore[import]
        return Wallet
    except ImportError:
        from rich.console import Console
        Console(stderr=True).print(
            f"[red]bittensor not installed.[/red]\n\n{_BITTENSOR_HINT}"
        )
        raise SystemExit(1)


def load_wallet(wallet_name: str, wallet_hotkey: str):
    """Load a Bittensor wallet by name and hotkey name.

    Exits with a user-friendly message if bittensor is not installed or the
    hotkey file does not exist on this machine.
    """
    Wallet = _require_wallet_class()
    wallet = Wallet(name=wallet_name, hotkey=wallet_hotkey)
    if not wallet.hotkey_file.exists_on_device():
        from rich.console import Console
        Console(stderr=True).print(
            f"[red]Hotkey '[bold]{wallet_hotkey}[/bold]' not found "
            f"for wallet '[bold]{wallet_name}[/bold]'.[/red]\n"
            "Check the wallet name and hotkey with [bold]btcli wallet list[/bold]."
        )
        raise SystemExit(1)
    return wallet


def get_hotkey(wallet) -> str:
    """Return the SS58 address of the wallet's hotkey."""
    return wallet.hotkey.ss58_address


def get_public_key(wallet) -> str:
    """Return the hex-encoded public key of the wallet's hotkey."""
    return wallet.hotkey.public_key.hex()


def sign_message(wallet, message: str) -> str:
    """Sign *message* with the wallet's hotkey and return a hex-encoded signature."""
    return wallet.hotkey.sign(message.encode()).hex()


def create_file_info(miner_hotkey: str, content_hash: str, timestamp: int) -> str:
    """Build the canonical file_info string: ``'hotkey:content_hash:timestamp'``."""
    return f"{miner_hotkey}:{content_hash}:{timestamp}"


def prepare_submission_credentials(
    wallet_name: str,
    wallet_hotkey: str,
    content_hash: str,
) -> tuple[str, str, str, str]:
    """Load wallet and produce all signing artefacts needed for a submission.

    Returns:
        ``(miner_hotkey, public_key, file_info, signature)``
    """
    wallet = load_wallet(wallet_name, wallet_hotkey)
    miner_hotkey = get_hotkey(wallet)
    public_key = get_public_key(wallet)
    timestamp = int(time.time())
    file_info = create_file_info(miner_hotkey, content_hash, timestamp)
    signature = sign_message(wallet, file_info)
    return miner_hotkey, public_key, file_info, signature
