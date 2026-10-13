"""Hugging Face weight custody: fingerprint, seal, local layout, and token scope."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from nepher_cli.tournament.agent_check import check_agent_structure
from nepher_cli.tournament.custody import (
    PROOF_FILENAME,
    CustodyError,
    HuggingFaceSubmission,
    check_huggingface_layout,
    check_repo_token_scope,
    hash_weights,
    read_declared_weights,
    seal_message,
    weights_fingerprint,
    write_proof,
)
from nepher_cli.tournament.packer import zip_directory

HOTKEY = "5Fhot"
REPO = "alice/go-weights"
REVISION = "f" * 40
# Same vectors as nepher-subnet/tests/test_custody.py and docs/huggingface-weight-custody.md.
VECTOR_WEIGHTS = {
    "model-00001.safetensors": "a" * 64,
    "model-00002.safetensors": "b" * 64,
    "config.json": "c" * 64,
}
VECTOR_FINGERPRINT = "d1997740cfac05556674280cf56da868615abc23da3b301e0f806bef6c30af97"
VECTOR_MESSAGE = f"nepher-seal-v1:{HOTKEY}:tid-1:{VECTOR_FINGERPRINT}:{REPO}:{REVISION}:1700000000"


def _agent(root: Path, *, tournament_id: str = "tid-1", declare: bool = True) -> Path:
    for name in ("brain", "train", "weights"):
        (root / name).mkdir(parents=True)
    (root / "weights" / "model.bin").write_bytes(b"novel weights")
    (root / "weights" / "sub").mkdir()
    (root / "weights" / "sub" / "config.json").write_bytes(b"{}")
    (root / "brain" / "policy.py").write_text("x = 1\n", encoding="utf-8")
    hashes = hash_weights(root / "weights")
    lines = ["entry: policy:Brain", "horizon: 8", "action_dim: 8", "weights:"]
    if declare:
        lines += [f"  {rel}: {digest}" for rel, digest in hashes.items()]
    (root / "agent.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_proof(root, tournament_id, HOTKEY)
    return root


def test_fingerprint_vector_ignores_base_paths_and_order():
    assert weights_fingerprint(VECTOR_WEIGHTS, {"c" * 64}) == VECTOR_FINGERPRINT
    renamed = {"x.bin": "b" * 64, "y.bin": "a" * 64, "z.bin": "c" * 64}
    assert weights_fingerprint(renamed, {"C" * 64}) == VECTOR_FINGERPRINT


BASE_ONLY_FINGERPRINT = "9c7995808ddf861b631f6839a193dd893f2a32f816f3e6b1eec8804822c2d30d"


def test_unmodified_base_checkpoint_is_fingerprinted_and_collides():
    base = set(VECTOR_WEIGHTS.values())
    assert weights_fingerprint(VECTOR_WEIGHTS, base) == BASE_ONLY_FINGERPRINT
    renamed = {"x.bin": "b" * 64, "y.bin": "a" * 64, "z.bin": "c" * 64}
    assert weights_fingerprint(renamed, base) == BASE_ONLY_FINGERPRINT
    # A fine-tune keeps the public files and adds its own; that fingerprint ignores the base.
    fine_tune = {**VECTOR_WEIGHTS, "adapter.bin": "d" * 64}
    assert weights_fingerprint(fine_tune, base) != BASE_ONLY_FINGERPRINT
    with pytest.raises(CustodyError):
        weights_fingerprint({})


def test_seal_message_vector():
    message = seal_message(HOTKEY, "tid-1", VECTOR_FINGERPRINT, REPO, REVISION, 1700000000)
    assert message == VECTOR_MESSAGE


def test_seal_signs_exact_message_and_carries_token():
    submission = HuggingFaceSubmission(
        tournament_id="tid-1",
        miner_hotkey=HOTKEY,
        hf_repo=REPO,
        hf_revision=REVISION,
        weights=VECTOR_WEIGHTS,
        base_digests=frozenset({"c" * 64}),
        hf_token="hf_read",
    )
    seal = submission.seal(lambda message: "sig:" + message, timestamp=1700000000)
    assert seal["seal_message"] == VECTOR_MESSAGE
    assert seal["seal_signature"] == "sig:" + VECTOR_MESSAGE
    assert seal["weights_fingerprint"] == VECTOR_FINGERPRINT
    assert seal["proof"] == {"version": 1, "tournament_id": "tid-1", "miner_hotkey": HOTKEY}
    assert seal["hf_read_token"] == "hf_read"


def test_read_declared_weights_handles_quotes_comments_and_blocks():
    text = (
        "entry: a:B\n"
        "weights:  # hashes\n"
        f"  'model.bin': \"{'A' * 64}\"\n"
        f"  sub/config.json: {'b' * 64}\n"
        "horizon: 8\n"
    )
    assert read_declared_weights(text) == {
        "model.bin": "a" * 64,
        "sub/config.json": "b" * 64,
    }


def test_layout_accepts_matching_hashes_and_proof(tmp_path: Path):
    agent = _agent(tmp_path / "agent")
    errors, weights = check_huggingface_layout(agent, tournament_id="tid-1", miner_hotkey=HOTKEY)
    assert errors == []
    assert set(weights) == {"model.bin", "sub/config.json"}


def test_layout_rejects_wrong_hash_missing_file_and_foreign_proof(tmp_path: Path):
    agent = _agent(tmp_path / "agent")
    (agent / "weights" / "model.bin").write_bytes(b"edited after hashing")
    (agent / "weights" / "sub" / "config.json").unlink()
    errors, _ = check_huggingface_layout(agent, tournament_id="other", miner_hotkey="5Fother")
    text = "\n".join(errors)
    assert "sha256 mismatch for weights/model.bin" in text
    assert "listed in agent.yaml is missing: sub/config.json" in text
    assert "another tournament" in text
    assert "another hotkey" in text


def test_layout_rejects_undeclared_file_and_missing_proof(tmp_path: Path):
    agent = _agent(tmp_path / "agent", declare=False)
    (agent / PROOF_FILENAME).unlink()
    errors, _ = check_huggingface_layout(agent)
    text = "\n".join(errors)
    assert "agent.yaml must list weights" in text
    assert "no hash in agent.yaml" in text
    assert PROOF_FILENAME in text


def test_layout_accepts_the_unmodified_base_checkpoint(tmp_path: Path):
    agent = _agent(tmp_path / "agent")
    base = set(hash_weights(agent / "weights").values())
    errors, weights = check_huggingface_layout(agent, base_digests=base)
    assert errors == []
    assert weights_fingerprint(weights, base) == weights_fingerprint(weights, weights.values())


def test_check_agent_structure_huggingface_mode(tmp_path: Path):
    agent = _agent(tmp_path / "agent")
    assert check_agent_structure(agent, "huggingface")[0]
    # The checkpoint layout is not required in this mode and is unchanged otherwise.
    assert not check_agent_structure(agent)[0]


def test_archive_omits_weights_but_keeps_proof_and_agent_yaml(tmp_path: Path):
    agent = _agent(tmp_path / "agent")
    archive = tmp_path / "agent.zip"
    zip_directory(agent, archive, frozenset({"weights"}))
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
    assert {"agent.yaml", PROOF_FILENAME, "brain/policy.py"} <= names
    assert not any(name.startswith("weights/") for name in names)
    inline = tmp_path / "inline.zip"
    zip_directory(agent, inline)
    with zipfile.ZipFile(inline) as zf:
        assert "weights/model.bin" in zf.namelist()


def _whoami(**overrides):
    payload = {
        "type": "user",
        "name": "alice",
        "auth": {
            "accessToken": {
                "role": "fineGrained",
                "fineGrained": {
                    "global": [],
                    "scoped": [
                        {
                            "entity": {"type": "model", "name": REPO},
                            "permissions": ["repo.content.read"],
                        }
                    ],
                },
            }
        },
    }
    payload.update(overrides)
    return payload


def test_token_scope_accepts_single_repo_read_only():
    assert check_repo_token_scope(_whoami(), REPO) == []


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda p: p.update(name="mallory"), "not the owner"),
        (lambda p: p.update(type="org"), "user account"),
        (lambda p: p["auth"]["accessToken"].update(role="write"), "fine-grained"),
        (
            lambda p: p["auth"]["accessToken"]["fineGrained"].update({"global": ["repo.write"]}),
            "account-wide",
        ),
        (
            lambda p: p["auth"]["accessToken"]["fineGrained"]["scoped"].append({}),
            "exactly one repo",
        ),
        (
            lambda p: p["auth"]["accessToken"]["fineGrained"]["scoped"][0]["entity"].update(
                name="alice/other"
            ),
            "scoped to the model repo",
        ),
        (
            lambda p: p["auth"]["accessToken"]["fineGrained"]["scoped"][0].update(
                permissions=["repo.content.read", "repo.write"]
            ),
            "read-only",
        ),
        (
            lambda p: p["auth"]["accessToken"]["fineGrained"]["scoped"][0].update(permissions=[]),
            "permission",
        ),
    ],
)
def test_token_scope_rejects_overbroad_or_foreign_tokens(mutate, expected):
    payload = _whoami()
    mutate(payload)
    errors = check_repo_token_scope(payload, REPO)
    assert any(expected in err for err in errors), errors


def test_proof_file_is_valid_json(tmp_path: Path):
    target = write_proof(tmp_path, "tid-1", HOTKEY)
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": 1,
        "tournament_id": "tid-1",
        "miner_hotkey": HOTKEY,
    }


class _FakeWallet:
    pass


def _patch_submit(monkeypatch, policy, calls):
    from nepher_cli.commands import tournament as module

    async def fake_policy(**_kwargs):
        return policy

    async def fake_token(**kwargs):
        calls["token"] = kwargs
        return {"upload_token": "t", "tournament_id": kwargs["tournament_id"] or "tid-1"}

    async def fake_upload(**kwargs):
        with zipfile.ZipFile(kwargs["file_path"]) as zf:
            calls["names"] = set(zf.namelist())
        calls["upload"] = kwargs
        return {"agent_id": "agent-1", "submission_fee_tao": None}

    monkeypatch.setattr(module.tournament_api, "fetch_submission_policy", fake_policy)
    monkeypatch.setattr(module.tournament_api, "request_upload_token", fake_token)
    monkeypatch.setattr(module.tournament_api, "upload_agent", fake_upload)
    monkeypatch.setattr(module, "load_wallet", lambda *_: _FakeWallet())
    monkeypatch.setattr(module, "get_hotkey", lambda _wallet: HOTKEY)
    monkeypatch.setattr(module, "sign_message", lambda _wallet, message: "sig:" + message)
    monkeypatch.setattr(module, "verify_hf_token", lambda token, repo: [])
    monkeypatch.setattr(
        module,
        "prepare_submission_credentials",
        lambda *_: (HOTKEY, "pk", "file-info", "file-sig"),
    )
    return module


def test_submit_huggingface_uploads_small_archive_and_signed_seal(monkeypatch, tmp_path: Path):
    from click.testing import CliRunner

    agent = _agent(tmp_path / "agent")
    calls: dict = {}
    module = _patch_submit(
        monkeypatch,
        {"tournament_id": "tid-1", "submission_mode": "huggingface", "base_weight_sha256": []},
        calls,
    )
    result = CliRunner().invoke(
        module.tournament,
        [
            "submit",
            "--path",
            str(agent),
            "--api-key",
            "k",
            "--hf-repo",
            REPO,
            "--hf-revision",
            REVISION,
            "--hf-token",
            "hf_read",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not any(name.startswith("weights/") for name in calls["names"])
    assert PROOF_FILENAME in calls["names"]
    seal = calls["token"]["seal"]
    assert seal["seal_signature"] == "sig:" + seal["seal_message"]
    assert seal["hf_repo"] == REPO and seal["hf_revision"] == REVISION
    assert calls["upload"]["weights_fingerprint"] == seal["weights_fingerprint"]


def test_submit_huggingface_requires_repo_and_revision(monkeypatch, tmp_path: Path):
    from click.testing import CliRunner

    agent = _agent(tmp_path / "agent")
    calls: dict = {}
    module = _patch_submit(
        monkeypatch,
        {"tournament_id": "tid-1", "submission_mode": "huggingface", "base_weight_sha256": []},
        calls,
    )
    result = CliRunner().invoke(
        module.tournament, ["submit", "--path", str(agent), "--api-key", "k"]
    )
    assert result.exit_code == 1
    assert "token" not in calls and "upload" not in calls


def test_submit_inline_keeps_full_archive_and_sends_no_seal(monkeypatch, tmp_path: Path):
    from click.testing import CliRunner

    agent = tmp_path / "agent"
    (agent / "best_policy").mkdir(parents=True)
    (agent / "best_policy" / "best_policy.pt").write_bytes(b"pt")
    (agent / "source" / "task").mkdir(parents=True)
    calls: dict = {}
    module = _patch_submit(
        monkeypatch,
        {"tournament_id": "tid-1", "submission_mode": "inline", "base_weight_sha256": []},
        calls,
    )
    result = CliRunner().invoke(
        module.tournament, ["submit", "--path", str(agent), "--api-key", "k"]
    )
    assert result.exit_code == 0, result.output
    assert "best_policy/best_policy.pt" in calls["names"]
    assert calls["token"]["seal"] is None
    assert calls["upload"]["weights_fingerprint"] is None


def test_submit_inline_rejects_hf_options(monkeypatch, tmp_path: Path):
    from click.testing import CliRunner

    agent = tmp_path / "agent"
    (agent / "best_policy").mkdir(parents=True)
    calls: dict = {}
    module = _patch_submit(
        monkeypatch,
        {"tournament_id": "tid-1", "submission_mode": "inline", "base_weight_sha256": []},
        calls,
    )
    result = CliRunner().invoke(
        module.tournament,
        ["submit", "--path", str(agent), "--api-key", "k", "--hf-repo", REPO],
    )
    assert result.exit_code == 1
    assert "upload" not in calls
