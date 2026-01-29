"""Scope configuration management.

Handles ~/.scope/config for tracking setup state and versions.
"""

import hashlib
from pathlib import Path

import orjson


def get_scope_config_path() -> Path:
    """Get the path to scope's config file."""
    return Path.home() / ".scope" / "config.json"


def read_config() -> dict:
    """Read scope config, returning empty dict if not found."""
    config_path = get_scope_config_path()
    if not config_path.exists():
        return {}
    try:
        content = config_path.read_bytes()
        return orjson.loads(content) if content else {}
    except (orjson.JSONDecodeError, OSError):
        return {}


def write_config(config: dict) -> None:
    """Write scope config."""
    config_path = get_scope_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_bytes(orjson.dumps(config, option=orjson.OPT_INDENT_2))


def get_installed_version(component: str) -> str | None:
    """Get the installed version hash for a setup component."""
    config = read_config()
    return config.get("setup_versions", {}).get(component)


def set_installed_version(component: str, version_hash: str) -> None:
    """Set the installed version hash for a setup component."""
    config = read_config()
    if "setup_versions" not in config:
        config["setup_versions"] = {}
    config["setup_versions"][component] = version_hash
    write_config(config)


def content_hash(*contents: str) -> str:
    """Generate a hash from content strings."""
    combined = "".join(contents)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def read_all_versions() -> dict[str, str]:
    """Read all installed version hashes at once.

    Returns:
        Dict mapping component names to version hashes.
    """
    config = read_config()
    return config.get("setup_versions", {})


def write_all_versions(versions: dict[str, str]) -> None:
    """Write all version hashes at once.

    Args:
        versions: Dict mapping component names to version hashes.
    """
    config = read_config()
    config["setup_versions"] = versions
    write_config(config)


DEFAULT_MAX_COMPLETED_SESSIONS = 5


def get_max_completed_sessions() -> int:
    """Get the maximum number of completed sessions to keep in memory.

    Completed sessions beyond this limit will be evicted (tmux window killed)
    but their data will be preserved on disk for resumption.

    Returns:
        The max completed sessions limit (default: 5).
    """
    config = read_config()
    return config.get("max_completed_sessions", DEFAULT_MAX_COMPLETED_SESSIONS)


def set_max_completed_sessions(n: int) -> None:
    """Set the maximum number of completed sessions to keep in memory.

    Args:
        n: The new limit (must be >= 0).
    """
    if n < 0:
        raise ValueError("max_completed_sessions must be >= 0")
    config = read_config()
    config["max_completed_sessions"] = n
    write_config(config)
