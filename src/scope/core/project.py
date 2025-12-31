"""Project identification utilities for scope.

Provides functions to identify the current project (git repo or cwd)
and generate unique identifiers for it.
"""

import hashlib
import subprocess
from pathlib import Path


def get_root_path_for(path: Path) -> Path:
    """Get the root path for scope storage (git root or given path)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return path


def get_root_path() -> Path:
    """Get the root path for scope storage (git root or cwd)."""
    return get_root_path_for(Path.cwd())


def get_project_identifier_for(path: Path) -> str:
    """Get a unique identifier for a project path.

    Returns:
        A string like "dirname-hash" where:
        - dirname is the basename of the git root (or cwd)
        - hash is first 8 chars of sha256 of the full path

    Example:
        For /Users/ada/fun/scope -> "scope-abc12345"
    """
    root_path = get_root_path_for(path)
    dir_name = root_path.name
    path_hash = hashlib.sha256(str(root_path).encode()).hexdigest()[:8]
    return f"{dir_name}-{path_hash}"


def get_project_identifier() -> str:
    """Get a unique identifier for the current project."""
    return get_project_identifier_for(Path.cwd())


def get_global_scope_base_for(path: Path) -> Path:
    """Get the global scope directory for a given project path."""
    identifier = get_project_identifier_for(path)
    return Path.home() / ".scope" / "repos" / identifier


def get_global_scope_base() -> Path:
    """Get the global scope directory for current project.

    Returns ~/.scope/repos/{identifier}/ where identifier is from
    get_project_identifier().

    Returns:
        Path to the global scope directory for this project.
    """
    return get_global_scope_base_for(Path.cwd())
