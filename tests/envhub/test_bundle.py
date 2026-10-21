"""EnvHub bundle extraction and API URL resolution."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from nepher_cli.envhub import config as envhub_config
from nepher_cli.envhub.bundle import extract_bundle, iter_bundle_files, safe_env_id


def _zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_extract_bundle(tmp_path: Path) -> None:
    dest = tmp_path / "cache" / "env-a"
    extract_bundle(_zip(tmp_path / "b.zip", {"manifest.yaml": "id: env-a", "a/s.usd": "x"}), dest)
    assert (dest / "a" / "s.usd").is_file()
    assert [p.name for p in dest.parent.iterdir()] == ["env-a"]


def test_extract_bundle_rejects_zip_slip(tmp_path: Path) -> None:
    dest = tmp_path / "cache" / "env-a"
    archive = _zip(tmp_path / "b.zip", {"manifest.yaml": "id: env-a", "../../evil.txt": "x"})
    with pytest.raises(ValueError):
        extract_bundle(archive, dest)
    assert not (tmp_path / "evil.txt").exists()
    assert not dest.exists()


def test_extract_bundle_requires_manifest(tmp_path: Path) -> None:
    dest = tmp_path / "cache" / "env-a"
    with pytest.raises(ValueError):
        extract_bundle(_zip(tmp_path / "b.zip", {"x.usd": "x"}), dest)
    assert not dest.exists()


@pytest.mark.parametrize("env_id", ["..", "../x", "a/b", ".hidden", ""])
def test_safe_env_id_rejects(env_id: str) -> None:
    with pytest.raises(ValueError):
        safe_env_id(env_id)


def test_iter_bundle_files_skips_vcs_and_secrets(tmp_path: Path) -> None:
    for rel in ["manifest.yaml", "a/s.usd", ".git/config", ".env", "a/__pycache__/m.pyc"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x", encoding="utf-8")
    assert sorted(r.as_posix() for _, r in iter_bundle_files(tmp_path)) == ["a/s.usd", "manifest.yaml"]


def test_legacy_api_url_in_config_file_is_ignored(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('api_url = "https://envhub-api.nepher.ai"\ncache_dir = "/c"\n', encoding="utf-8")
    monkeypatch.setattr(envhub_config, "find_config_file", lambda: cfg)
    data = envhub_config.load_config_file()
    assert "api_url" not in data
    assert data["cache_dir"] == "/c"


def test_set_api_key_is_refused() -> None:
    with pytest.raises(ValueError):
        envhub_config.set_value("api_key", "nepher_x")
