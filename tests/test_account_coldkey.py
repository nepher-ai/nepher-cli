"""Coldkey signing helpers — wallet library preferred over btcli."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from nepher_cli.commands.account import (
    _extract_btcli_payload,
    _looks_like_scalecodec_conflict,
    _sign_with_bittensor_wallet,
    _signature_to_hex,
    has_scalecodec_cyscale_conflict,
)


def test_has_scalecodec_cyscale_conflict() -> None:
    assert has_scalecodec_cyscale_conflict({"cyscale", "scalecodec"}) is True
    assert has_scalecodec_cyscale_conflict({"cyscale", "py-scale-codec"}) is True
    assert has_scalecodec_cyscale_conflict({"cyscale"}) is False
    assert has_scalecodec_cyscale_conflict({"scalecodec"}) is False
    assert has_scalecodec_cyscale_conflict(set()) is False


def test_looks_like_scalecodec_conflict() -> None:
    traceback = (
        "RuntimeError:\n\nConflict detected: 'scalecodec' (py-scale-codec) is installed.\n"
        "This conflicts with 'cyscale', which uses the same namespace.\n"
    )
    assert _looks_like_scalecodec_conflict(traceback) is True
    assert _looks_like_scalecodec_conflict("btcli: wallet not found") is False


def test_signature_to_hex() -> None:
    assert _signature_to_hex(b"\xab\xcd") == "abcd"
    assert _signature_to_hex("0xAbCd") == "AbCd"
    assert _signature_to_hex("deadbeef") == "deadbeef"


def test_extract_btcli_payload_signed_message_keys() -> None:
    raw = '{"signed_message": "aabb", "signer_address": "5FakeAddress11111111111111111111111111111111"}'
    data = _extract_btcli_payload(raw, "hello")
    assert data is not None
    assert data["signature"] == "aabb"
    assert data["address"].startswith("5Fake")
    assert data["message"] == "hello"


def test_sign_with_bittensor_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeKeypair:
        ss58_address = "5FakeColdkey"

        def sign(self, data: bytes) -> bytes:
            assert data == b"challenge-text"
            return b"\x01\x02"

    class FakeFile:
        def exists_on_device(self) -> bool:
            return True

    class FakeWallet:
        def __init__(self, name: str) -> None:
            assert name == "vali_ck4"
            self.coldkey_file = FakeFile()
            self.coldkey = FakeKeypair()

    mod = types.ModuleType("bittensor_wallet")
    mod.Wallet = FakeWallet  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bittensor_wallet", mod)

    signed = _sign_with_bittensor_wallet("vali_ck4", "challenge-text")
    assert signed == {
        "message": "challenge-text",
        "address": "5FakeColdkey",
        "signature": "0102",
    }


def test_sign_with_bittensor_wallet_missing_lib(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any):
        if name == "bittensor_wallet":
            raise ImportError("no wallet")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _sign_with_bittensor_wallet("vali_ck4", "msg") is None
