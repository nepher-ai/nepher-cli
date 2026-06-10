"""Local agent directory structure check — no external dependencies."""

from __future__ import annotations

from pathlib import Path

# Required items: relative path → "file" or "directory"
_REQUIRED: dict[str, str] = {
    "best_policy": "directory",
    "best_policy/best_policy.pt": "file",
    "source": "directory",
}

# Recommended (absent ones produce warnings, not errors)
_RECOMMENDED: dict[str, str] = {
    "scripts/list_envs.py": "file",
    "scripts/rsl_rl/play.py": "file",
}


def check_agent_structure(
    agent_path: Path,
) -> tuple[bool, list[str], list[str]]:
    """Check whether *agent_path* meets the expected agent layout.

    Returns:
        (is_valid, errors, warnings)

        * ``is_valid``  – True when all required items are present and correct.
        * ``errors``    – Required items that are missing or the wrong type.
        * ``warnings``  – Recommended items that are absent (non-blocking).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not agent_path.exists():
        return False, [f"Path does not exist: {agent_path}"], warnings

    if not agent_path.is_dir():
        return False, [f"Not a directory: {agent_path}"], warnings

    for rel_path, item_type in _REQUIRED.items():
        full_path = agent_path / rel_path
        if not full_path.exists():
            errors.append(f"Required {item_type} missing: {rel_path}")
        elif item_type == "directory" and not full_path.is_dir():
            errors.append(f"Expected directory but found file: {rel_path}")
        elif item_type == "file" and not full_path.is_file():
            errors.append(f"Expected file but found directory: {rel_path}")

    source_dir = agent_path / "source"
    if source_dir.exists() and source_dir.is_dir():
        if not any(d.is_dir() for d in source_dir.iterdir()):
            errors.append("source/ directory must contain at least one task module subdirectory")

    for rel_path, item_type in _RECOMMENDED.items():
        if not (agent_path / rel_path).exists():
            warnings.append(f"Recommended {item_type} missing: {rel_path}")

    return len(errors) == 0, errors, warnings
