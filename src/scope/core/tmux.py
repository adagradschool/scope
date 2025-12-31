"""tmux wrapper for scope.

Provides functions to create and manage tmux windows for scope.
Each Claude Code session runs in its own window within the main scope session.
This allows attaching/detaching without destroying sessions.
"""

import os
import subprocess
from pathlib import Path


# Socket name for tmux isolation (used for testing)
# Set SCOPE_TMUX_SOCKET to use a separate tmux server
TMUX_SOCKET_ENV = "SCOPE_TMUX_SOCKET"


def _tmux_cmd(args: list[str]) -> list[str]:
    """Build a tmux command, optionally with a custom socket.

    If SCOPE_TMUX_SOCKET is set, adds -L <socket> to use an isolated server.
    """
    socket = os.environ.get(TMUX_SOCKET_ENV)
    if socket:
        return ["tmux", "-L", socket] + args
    return ["tmux"] + args


class TmuxError(Exception):
    """Raised when a tmux command fails."""

    pass


def get_scope_session() -> str:
    """Get the tmux session name for scope.

    Returns a project-specific session name based on git root (or cwd).
    Configurable via SCOPE_TMUX_SESSION env var to override.
    """
    if env_session := os.environ.get("SCOPE_TMUX_SESSION"):
        return env_session
    from scope.core.project import get_project_identifier

    return f"scope-{get_project_identifier()}"


def is_installed() -> bool:
    """Check if tmux is installed on the system.

    Returns:
        True if tmux is installed and accessible, False otherwise.
    """
    try:
        result = subprocess.run(
            _tmux_cmd(["-V"]),
            capture_output=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def tmux_session_name(session_id: str) -> str:
    """Convert a scope session ID to a tmux session name.

    Replaces dots with hyphens since tmux uses dots for window.pane notation.

    Args:
        session_id: The scope session ID (e.g., "0", "0.0", "0.0.1")

    Returns:
        Safe tmux session name (e.g., "scope-0", "scope-0-0", "scope-0-0-1")
    """
    return f"scope-{session_id.replace('.', '-')}"


def tmux_window_name(session_id: str) -> str:
    """Convert a scope session ID to a tmux window name.

    Args:
        session_id: The scope session ID (e.g., "0", "0.0", "0.0.1")

    Returns:
        Window name (e.g., "w0", "w0-0", "w0-0-1")
    """
    return f"w{session_id.replace('.', '-')}"


def in_tmux() -> bool:
    """Check if we're running inside a tmux session.

    Returns:
        True if inside tmux, False otherwise.
    """
    return os.environ.get("TMUX") is not None


def enable_mouse() -> None:
    """Enable tmux mouse mode for pane switching."""
    subprocess.run(_tmux_cmd(["set", "-g", "mouse", "on"]), capture_output=True)


def attach_in_split(window_name: str) -> str:
    """Join a window's pane into the current window as a horizontal split.

    Uses join-pane to move the pane from the target window into the current
    window, allowing proper mouse/keyboard interaction with both panes.

    Args:
        window_name: The tmux window to pull from (e.g., "w0")

    Returns:
        The pane ID of the joined pane (e.g., "%5")

    Raises:
        TmuxError: If tmux command fails.
    """
    # Get current panes before joining
    before = subprocess.run(
        _tmux_cmd(["list-panes", "-F", "#{pane_id}"]),
        capture_output=True,
        text=True,
    )
    panes_before = set(before.stdout.strip().split("\n"))

    # Join the pane from the target window into current window
    # -h: horizontal split (side by side)
    # Use :{window_name}.0 to reference window by name in current session
    result = subprocess.run(
        _tmux_cmd(["join-pane", "-h", "-s", f":{window_name}.0"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to join pane: {result.stderr}")

    # Get panes after joining - the new one is the joined pane
    after = subprocess.run(
        _tmux_cmd(["list-panes", "-F", "#{pane_id}"]),
        capture_output=True,
        text=True,
    )
    panes_after = set(after.stdout.strip().split("\n"))

    new_panes = panes_after - panes_before
    if new_panes:
        return new_panes.pop()

    # Fallback: return the rightmost pane (should be the joined one with -h)
    result = subprocess.run(
        _tmux_cmd(["display-message", "-t", "{right}", "-p", "#{pane_id}"]),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def detach_to_window(pane_id: str, window_name: str) -> None:
    """Move a pane back to its own tmux window.

    Uses break-pane to move the pane to a new window with the given name.

    Args:
        pane_id: The pane to move (e.g., "%5")
        window_name: The window name to create (e.g., "w0")

    Raises:
        TmuxError: If tmux command fails.
    """
    # First verify the pane exists
    result = subprocess.run(
        _tmux_cmd(["display-message", "-t", pane_id, "-p", "#{pane_id}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Pane {pane_id} not found")

    # Use break-pane to move the pane to its own window
    # -d: don't switch to the new window
    # -n: name the new window
    result = subprocess.run(
        _tmux_cmd(["break-pane", "-d", "-s", pane_id, "-n", window_name]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to break pane: {result.stderr}")


def ensure_scope_session() -> None:
    """Ensure the main 'scope' tmux session exists.

    Creates a detached session if it doesn't exist.
    """
    session_name = get_scope_session()
    if has_session(session_name):
        return

    # Create a new detached session
    # The initial window will be replaced or used for the scope TUI
    cmd = _tmux_cmd(["new-session", "-d", "-s", session_name])
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
    cmd = _tmux_cmd(
        [
            "new-session",
            "-d",  # Detached
            "-s",
            name,  # Session name
            "-c",
            str(cwd),  # Working directory
            full_command,
        ]
    )

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
        _tmux_cmd(["has-session", "-t", name]),
        capture_output=True,
    )
    return result.returncode == 0


def has_window(name: str) -> bool:
    """Check if a tmux window exists in the current session.

    Args:
        name: Window name to check.

    Returns:
        True if window exists, False otherwise.
    """
    result = subprocess.run(
        _tmux_cmd(["list-windows", "-F", "#{window_name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    windows = result.stdout.strip().split("\n")
    return name in windows


def kill_window(name: str) -> None:
    """Kill a tmux window by name.

    Args:
        name: Window name to kill (e.g., "w0")

    Raises:
        TmuxError: If tmux command fails.
    """
    result = subprocess.run(
        _tmux_cmd(["kill-window", "-t", f":{name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to kill window {name}: {result.stderr}")


def kill_session(name: str) -> None:
    """Kill a tmux session.

    Args:
        name: Session name to kill (e.g., "scope-0")

    Raises:
        TmuxError: If tmux command fails.
    """
    result = subprocess.run(
        _tmux_cmd(["kill-session", "-t", name]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to kill session {name}: {result.stderr}")


def detach_client() -> None:
    """Detach the current tmux client without stopping sessions."""
    result = subprocess.run(
        _tmux_cmd(["detach-client"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to detach client: {result.stderr}")


def rename_current_window(name: str) -> None:
    """Rename the current tmux window."""
    result = subprocess.run(
        _tmux_cmd(["rename-window", name]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to rename window: {result.stderr}")


def set_current_window_option(option: str, value: str) -> None:
    """Set a window option on the current window."""
    result = subprocess.run(
        _tmux_cmd(["set-option", "-w", "-t", ":", option, value]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to set window option: {result.stderr}")


def has_window_in_session(session_name: str, window_name: str) -> bool:
    """Check if a tmux window exists in a specific session."""
    result = subprocess.run(
        _tmux_cmd(["list-windows", "-t", session_name, "-F", "#{window_name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    windows = result.stdout.strip().split("\n")
    return window_name in windows


def is_window_dead(session_name: str, window_name: str) -> bool:
    """Return True if all panes in a window are dead."""
    result = subprocess.run(
        _tmux_cmd(
            [
                "list-panes",
                "-t",
                f"{session_name}:{window_name}",
                "-F",
                "#{pane_dead}",
            ]
        ),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return True
    values = [value for value in result.stdout.strip().split("\n") if value]
    if not values:
        return True
    return all(value.strip() == "1" for value in values)


def select_window_in_session(session_name: str, window_name: str) -> None:
    """Select a window by name in a specific session."""
    result = subprocess.run(
        _tmux_cmd(["select-window", "-t", f"{session_name}:{window_name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to select window: {result.stderr}")


def kill_window_in_session(session_name: str, window_name: str) -> None:
    """Kill a tmux window by name in a specific session."""
    result = subprocess.run(
        _tmux_cmd(["kill-window", "-t", f"{session_name}:{window_name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to kill window {window_name}: {result.stderr}")


def get_current_session() -> str | None:
    """Get the name of the current tmux session.

    Returns:
        Session name if running inside tmux, None otherwise.
    """
    result = subprocess.run(
        _tmux_cmd(["display-message", "-p", "#{session_name}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def get_current_pane_id() -> str | None:
    """Get the pane ID for the current tmux pane."""
    result = subprocess.run(
        _tmux_cmd(["display-message", "-p", "#{pane_id}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def pane_target_for_window(window_name: str) -> str:
    """Build a pane target for the first pane in a window."""
    current = get_current_session()
    if current is None:
        return f"{get_scope_session()}:{window_name}.0"
    return f":{window_name}.0"


def set_pane_option(target: str, option: str, value: str) -> None:
    """Set a pane-local option."""
    result = subprocess.run(
        _tmux_cmd(["set-option", "-p", "-t", target, option, value]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to set pane option: {result.stderr}")


def select_pane(pane_id: str) -> None:
    """Select a pane by ID in the current window."""
    result = subprocess.run(
        _tmux_cmd(["select-pane", "-t", pane_id]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TmuxError(f"Failed to select pane: {result.stderr}")


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

    cmd = _tmux_cmd(
        [
            "split-window",
            "-h",  # Horizontal split
            "-c",
            str(cwd),  # Working directory
            full_command,
        ]
    )

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
        target = get_scope_session()
    else:
        target = current

    cmd = _tmux_cmd(
        [
            "new-window",
            "-d",  # Don't switch to the new window
            "-t",
            target,
            "-n",
            name,  # Window name
            "-c",
            str(cwd),
            full_command,
        ]
    )

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
    cmd = _tmux_cmd(["select-window", "-t", name])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TmuxError(f"Failed to select window: {result.stderr}")


def send_keys(target: str, keys: str, submit: bool = True) -> None:
    """Send keys to a tmux target (window or session).

    Args:
        target: The tmux target to send keys to (e.g., ":w0" for window, "scope-0" for session).
        keys: The text to send.
        submit: Whether to send C-m (Enter) after the keys to submit. Defaults to True.

    Raises:
        TmuxError: If tmux command fails.
    """
    import time

    # Send message text (no -l flag for raw send)
    cmd = _tmux_cmd(["send-keys", "-t", target, keys])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TmuxError(f"Failed to send keys: {result.stderr}")

    if submit:
        # Wait before sending Enter
        time.sleep(1)
        # C-m (Ctrl+M) is carriage return - submits in Claude Code
        result = subprocess.run(
            _tmux_cmd(["send-keys", "-t", target, "C-m"]),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise TmuxError(f"Failed to send C-m: {result.stderr}")
