"""Hugging Face weight custody for tournament submissions — stdlib and httpx only.

Large weights stay in the miner's private Hugging Face repo. The miner uploads a
small archive plus a signed *seal*: repo, commit, and the SHA-256 of every weight
file. The definitions here (proof file, fingerprint, seal message) are shared with
``nepher_core/custody.py`` in nepher-subnet and are pinned by the same test vectors.
See ``nepher-subnet/docs/huggingface-weight-custody.md``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

PROOF_FILENAME = "nepher-proof.json"
MODE_INLINE = "inline"
MODE_HUGGINGFACE = "huggingface"

_FINGERPRINT_PREFIX = "nepher-weights-v1\n"
_SEAL_PREFIX = "nepher-seal-v1"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_REVISION_RE = re.compile(r"[0-9a-f]{40}")
_REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")

# Hard-coded so an environment variable can never redirect the token elsewhere.
HF_API_BASE = "https://huggingface.co"
_REQUIRED_TOKEN_PERMISSION = "repo.content.read"
_ALLOWED_TOKEN_PERMISSIONS = frozenset({"repo.content.read", "repo.access.read"})


class CustodyError(ValueError):
    """The submission cannot be sealed."""


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest of *path*, reading in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_valid_revision(revision: str) -> bool:
    """True for a full 40-character lowercase commit SHA."""
    return bool(_REVISION_RE.fullmatch(revision))


def is_valid_repo_id(repo_id: str) -> bool:
    """True for ``owner/name``."""
    return bool(_REPO_RE.fullmatch(repo_id))


def hash_weights(weights_dir: Path) -> dict[str, str]:
    """Hash every file under *weights_dir*. Hidden files and directories are skipped."""
    result: dict[str, str] = {}
    for path in sorted(weights_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(weights_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        result[rel.as_posix()] = sha256_file(path)
    return result


def read_declared_weights(agent_yaml_text: str) -> dict[str, str]:
    """Read the ``weights:`` mapping of ``agent.yaml`` without a YAML dependency.

    ``agent.yaml`` stores weights as a one-level mapping of relative path to digest.
    """
    declared: dict[str, str] = {}
    in_block = False
    for raw in agent_yaml_text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indented = line.startswith((" ", "\t"))
        if not in_block:
            if not indented and line.strip() == "weights:":
                in_block = True
            continue
        if not indented:
            break
        key, sep, value = line.strip().rpartition(":")
        if not sep:
            raise CustodyError(f"agent.yaml weights line is not 'path: sha256': {line.strip()}")
        key = key.strip().strip("'\"")
        declared[key] = value.strip().strip("'\"").lower()
    return declared


def weights_fingerprint(weights: Mapping[str, str], base_digests: Iterable[str] = ()) -> str:
    """Return the fingerprint used to detect a duplicate submission.

    Digests on the public base-checkpoint allowlist are left out when the submission also
    contains other files, so miners can share that checkpoint. A submission that is only
    the public checkpoint is fingerprinted in full: the first one is accepted and a later
    copy of the same files collides.

    Raises:
        CustodyError: If there are no weight files.
    """
    if not weights:
        raise CustodyError("weights contain no files")
    base = {digest.lower() for digest in base_digests}
    all_digests = sorted({digest.lower() for digest in weights.values()})
    novel = [digest for digest in all_digests if digest not in base]
    claimed = novel or all_digests
    return hashlib.sha256((_FINGERPRINT_PREFIX + "\n".join(claimed)).encode()).hexdigest()


def seal_message(
    miner_hotkey: str,
    tournament_id: str,
    fingerprint: str,
    hf_repo: str,
    hf_revision: str,
    timestamp: int,
) -> str:
    """Return the exact string the hotkey signs to seal a submission."""
    return (
        f"{_SEAL_PREFIX}:{miner_hotkey}:{tournament_id}:{fingerprint}"
        f":{hf_repo}:{hf_revision}:{timestamp}"
    )


def proof_document(tournament_id: str, miner_hotkey: str) -> dict[str, Any]:
    """Return the proof document for a tournament and hotkey."""
    return {"version": 1, "tournament_id": tournament_id, "miner_hotkey": miner_hotkey}


def write_proof(agent_path: Path, tournament_id: str, miner_hotkey: str) -> Path:
    """Write ``nepher-proof.json`` into the agent directory and return its path."""
    target = Path(agent_path) / PROOF_FILENAME
    target.write_text(
        json.dumps(proof_document(tournament_id, miner_hotkey)) + "\n", encoding="utf-8"
    )
    return target


def check_proof(
    agent_path: Path,
    tournament_id: str | None = None,
    miner_hotkey: str | None = None,
) -> tuple[list[str], dict[str, Any] | None]:
    """Check the proof file. Tournament and hotkey are compared only when given."""
    path = Path(agent_path) / PROOF_FILENAME
    if not path.is_file():
        return [f"missing {PROOF_FILENAME} (create it with: npcli tournament proof)"], None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{PROOF_FILENAME}: {exc}"], None
    errors: list[str] = []
    if not isinstance(document, dict) or document.get("version") != 1:
        return [f"{PROOF_FILENAME} must be a version 1 object"], None
    for key in ("tournament_id", "miner_hotkey"):
        if not isinstance(document.get(key), str) or not document[key]:
            errors.append(f"{PROOF_FILENAME}: {key} must be a non-empty string")
    if tournament_id is not None and document.get("tournament_id") != tournament_id:
        errors.append(f"{PROOF_FILENAME} names another tournament")
    if miner_hotkey is not None and document.get("miner_hotkey") != miner_hotkey:
        errors.append(f"{PROOF_FILENAME} names another hotkey")
    return errors, document


def check_huggingface_layout(
    agent_path: Path,
    *,
    base_digests: Iterable[str] = (),
    tournament_id: str | None = None,
    miner_hotkey: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Validate a submission whose weights live on Hugging Face.

    The agent directory still holds ``weights/`` locally so the hashes can be
    computed. The archive built for upload omits it.

    Returns:
        ``(errors, local_weights)`` where *local_weights* maps relative path to SHA-256.
    """
    agent_path = Path(agent_path)
    errors: list[str] = []
    if not agent_path.is_dir():
        return [f"Not a directory: {agent_path}"], {}
    for name in ("brain", "train", "weights"):
        if not (agent_path / name).is_dir():
            errors.append(f"missing directory: {name}/")
    config_path = agent_path / "agent.yaml"
    declared: dict[str, str] = {}
    if not config_path.is_file():
        errors.append("missing agent.yaml")
    else:
        try:
            declared = read_declared_weights(config_path.read_text(encoding="utf-8"))
        except (CustodyError, UnicodeDecodeError) as exc:
            errors.append(str(exc))
        if not declared:
            errors.append("agent.yaml must list weights as 'path: sha256'")
    for rel, digest in declared.items():
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            errors.append(f"weights path must stay inside weights/: {rel}")
        if not _SHA256_RE.fullmatch(digest):
            errors.append(f"weights digest for {rel} is not 64 hex characters")
    local: dict[str, str] = {}
    if (agent_path / "weights").is_dir():
        local = hash_weights(agent_path / "weights")
        if not local:
            errors.append("weights/ has no files")
        for rel in sorted(set(local) - set(declared)):
            errors.append(f"weights file has no hash in agent.yaml: {rel}")
        for rel in sorted(set(declared) - set(local)):
            errors.append(f"weights file listed in agent.yaml is missing: {rel}")
        for rel in sorted(set(local) & set(declared)):
            if local[rel] != declared[rel]:
                errors.append(f"sha256 mismatch for weights/{rel}")
    if local:
        try:
            weights_fingerprint(local, base_digests)
        except CustodyError as exc:
            errors.append(str(exc))
    proof_errors, _ = check_proof(agent_path, tournament_id, miner_hotkey)
    errors.extend(proof_errors)
    return errors, local


def check_repo_token_scope(whoami: Mapping[str, Any], hf_repo: str) -> list[str]:
    """Check a ``whoami-v2`` payload: owner of the repo, fine-grained, read-only, one repo."""
    owner = hf_repo.partition("/")[0]
    errors: list[str] = []
    if whoami.get("type") != "user":
        errors.append("the token must belong to a user account")
    if whoami.get("name") != owner:
        errors.append(f"the token owner is not the owner of {hf_repo}")
    token = (whoami.get("auth") or {}).get("accessToken") or {}
    if token.get("role") != "fineGrained":
        errors.append("the token must be a fine-grained token")
        return errors
    fine = token.get("fineGrained") or {}
    if fine.get("global"):
        errors.append("the token has account-wide permissions; scope it to this repo only")
    scoped = fine.get("scoped") or []
    if len(scoped) != 1:
        errors.append("the token must be scoped to exactly one repo")
        return errors
    entity = scoped[0].get("entity") or {}
    if entity.get("type") != "model" or entity.get("name") != hf_repo:
        errors.append(f"the token must be scoped to the model repo {hf_repo}")
    permissions = set(scoped[0].get("permissions") or [])
    if _REQUIRED_TOKEN_PERMISSION not in permissions:
        errors.append(f"the token needs the {_REQUIRED_TOKEN_PERMISSION} permission")
    extra = sorted(permissions - _ALLOWED_TOKEN_PERMISSIONS)
    if extra:
        errors.append(f"the token must be read-only; remove: {', '.join(extra)}")
    return errors


def verify_hf_token(token: str, hf_repo: str, *, client: httpx.Client | None = None) -> list[str]:
    """Ask Hugging Face directly about *token* before it is sent to Nepher."""
    owns_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        response = http.get(
            f"{HF_API_BASE}/api/whoami-v2", headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.RequestError as exc:
        return [f"could not reach Hugging Face: {exc}"]
    finally:
        if owns_client:
            http.close()
    if response.status_code != 200:
        return [f"Hugging Face rejected the token (HTTP {response.status_code})"]
    try:
        payload = response.json()
    except ValueError:
        return ["Hugging Face returned an unreadable response"]
    return check_repo_token_scope(payload, hf_repo)


@dataclass(frozen=True)
class HuggingFaceSubmission:
    """Everything the seal needs, checked locally before any upload."""

    tournament_id: str
    miner_hotkey: str
    hf_repo: str
    hf_revision: str
    weights: Mapping[str, str]
    base_digests: frozenset[str]
    hf_token: str

    @property
    def fingerprint(self) -> str:
        """Fingerprint of the non-base weight digests."""
        return weights_fingerprint(self.weights, self.base_digests)

    def seal(self, sign: Callable[[str], str], timestamp: int | None = None) -> dict[str, Any]:
        """Build the signed seal sent with the upload-token request."""
        stamp = int(time.time()) if timestamp is None else timestamp
        message = seal_message(
            self.miner_hotkey,
            self.tournament_id,
            self.fingerprint,
            self.hf_repo,
            self.hf_revision,
            stamp,
        )
        return {
            "hf_repo": self.hf_repo,
            "hf_revision": self.hf_revision,
            "weights": dict(self.weights),
            "weights_fingerprint": self.fingerprint,
            "proof": proof_document(self.tournament_id, self.miner_hotkey),
            "seal_message": message,
            "seal_signature": sign(message),
            "hf_read_token": self.hf_token,
        }
