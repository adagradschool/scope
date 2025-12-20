"""tmux wrapper for scope.

Provides functions to create and manage tmux sessions for scope.
Each Claude Code session runs in its own independent tmux session.
"""

import os
import subprocess
from pathlib import Path


class TmuxError(Exception):
    """Raised when a tmux command fails."""

    pass


def in_tmux() -> bool:
    """Check if we're running inside a tmux session.

    Returns:
        True if inside tmux, False otherwise.
    """
    return os.environ.get("TMUX") is not None


def enable_mouse() -> None:
    """Enable tmux mouse mode for pane switching."""
    subprocess.run(["tmux", "set", "-g", "mouse", "on"], capture_output=True)


def attach_in_split(session_name: str) -> str:
    """Join a session's pane into the current window as a horizontal split.

    Uses join-pane instead of nested tmux attach, which allows proper
    mouse/keyboard interaction with both panes.

    Args:
        session_name: The tmux session to pull from (e.g., "scope-0")

    Returns:
        The pane ID of the joined pane (e.g., "%5")

    Raises:
        TmuxError: If tmux command fails.
    """
    # Get current panes before joining
    before = subprocess.run(
        ["tmux", "list-panes", "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    panes_before = set(before.stdout.strip().split("\n"))

    # Join the pane from the target session into current window
    # -h: horizontal split (side by side)
    result = subprocess.run(
        ["tmux", "join-pane", "-h", "-s", f"{session_name}:0.0"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to join pane: {result.stderr}")

    # Get panes after joining - the new one is the joined pane
    after = subprocess.run(
        ["tmux", "list-panes", "-F", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    panes_after = set(after.stdout.strip().split("\n"))

    new_panes = panes_after - panes_before
    if new_panes:
        return new_panes.pop()

    # Fallback: return the rightmost pane (should be the joined one with -h)
    result = subprocess.run(
        ["tmux", "display-message", "-t", "{right}", "-p", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def detach_to_session(pane_id: str, session_name: str) -> None:
    """Move a pane back to its own tmux session.

    Recreates the session if needed and moves the pane there.

    Args:
        pane_id: The pane to move (e.g., "%5")
        session_name: The session to move it to (e.g., "scope-0")

    Raises:
        TmuxError: If tmux command fails.
    """
    # First verify the pane exists
    result = subprocess.run(
        ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_id}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Pane {pane_id} not found")

    # Create the destination session with a placeholder
    # Use a shell command that will be replaced when we move the pane
    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, "cat"],  # cat blocks waiting for input
        capture_output=True,
        text=True,
    )
    # Check if session exists now (either we created it or it already existed)
    if not has_session(session_name):
        raise TmuxError(f"Could not create session {session_name}: {result.stderr}")

    # Move the pane to the new session's window
    result = subprocess.run(
        ["tmux", "move-pane", "-s", pane_id, "-t", f"{session_name}:0"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to move pane: {result.stderr}")

    # Kill the placeholder pane (cat)
    # The moved pane should now be in the session, kill the 'cat' pane
    result = subprocess.run(
        ["tmux", "list-panes", "-t", session_name, "-F", "#{pane_id} #{pane_current_command}"],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.strip().split("\n"):
        if line and "cat" in line.lower():
            cat_pane = line.split()[0]
            subprocess.run(
                ["tmux", "kill-pane", "-t", cat_pane],
                capture_output=True,
            )
            break


def ensure_scope_session() -> None:
    """Ensure the main 'scope' tmux session exists.

    Creates a detached session if it doesn't exist.
    """
    if has_session(SCOPE_SESSION):
        return

    # Create a new detached session
    # The initial window will be replaced or used for scope top
    cmd = ["tmux", "new-session", "-d", "-s", SCOPE_SESSION]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TmuxError(f"Failed to create scope session: {result.stderr}")


def create_session(
    name: str,
    command: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Create a new detached tmux session.

    Args:
        name: Session name (e.g., "scope-0")
        command: Command to run in the session
        cwd: Working directory for the session. Defaults to current directory.
        env: Additional environment variables to set.

    Raises:
        TmuxError: If tmux command fails.
    """
    cwd = cwd or Path.cwd()

    # Build command with environment variables
    if env:
        env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
        full_command = f"{env_prefix} {command}"
    else:
        full_command = command

    # tmux new-session -d -s {name} -c {cwd} "{command}"
    cmd = [
        "tmux",
        "new-session",
        "-d",  # Detached
        "-s",
        name,  # Session name
        "-c",
        str(cwd),  # Working directory
        full_command,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise TmuxError(f"Failed to create tmux session: {result.stderr}")


def has_session(name: str) -> bool:
    """Check if a tmux session exists.

    Args:
        name: Session name to check.

    Returns:
        True if session exists, False otherwise.
    """
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def kill_session(name: str) -> None:
    """Kill a tmux session.

    Args:
        name: Session name to kill (e.g., "scope-0")

    Raises:
        TmuxError: If tmux command fails.
    """
    result = subprocess.run(
        ["tmux", "kill-session", "-t", name],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to kill session {name}: {result.stderr}")


def get_current_session() -> str | None:
    """Get the name of the current tmux session.

    Returns:
        Session name if running inside tmux, None otherwise.
    """
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#{session_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def split_window(
    command: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Split the current tmux window horizontally and run a command.

    Args:
        command: Command to run in the new pane.
        cwd: Working directory. Defaults to current directory.
        env: Additional environment variables to set.

    Raises:
        TmuxError: If tmux command fails.
    """
    cwd = cwd or Path.cwd()

    # Build command with environment variables (same pattern as create_session)
    if env:
        env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
        full_command = f"{env_prefix} {command}"
    else:
        full_command = command

    cmd = [
        "tmux",
        "split-window",
        "-h",  # Horizontal split
        "-c",
        str(cwd),  # Working directory
        full_command,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TmuxError(f"Failed to split window: {result.stderr}")


def create_window(
    name: str,
    command: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Create a new window in the current or scope tmux session.

    If running inside tmux, creates window in current session.
    If not in tmux, ensures "scope" session exists and creates window there.

    Args:
        name: Window name (e.g., "w0")
        command: Command to run in the window
        cwd: Working directory. Defaults to current directory.
        env: Additional environment variables to set.

    Raises:
        TmuxError: If tmux command fails.
    """
    cwd = cwd or Path.cwd()

    # Build command with environment variables
    if env:
        env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
        full_command = f"{env_prefix} {command}"
    else:
        full_command = command

    # If not in tmux, use the scope session
    current = get_current_session()
    if current is None:
        ensure_scope_session()
        target = SCOPE_SESSION
    else:
        target = current

    cmd = [
        "tmux",
        "new-window",
        "-d",  # Don't switch to the new window
        "-t", target,
        "-n", name,  # Window name
        "-c", str(cwd),
        full_command,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TmuxError(f"Failed to create window: {result.stderr}")


def select_window(name: str) -> None:
    """Select a window by name in the current session.

    Args:
        name: The window name to select (e.g., "w0")

    Raises:
        TmuxError: If window doesn't exist or command fails.
    """
    cmd = ["tmux", "select-window", "-t", name]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TmuxError(f"Failed to select window: {result.stderr}")
