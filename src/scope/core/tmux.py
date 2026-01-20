"""tmux wrapper for scope.

Provides functions to create and manage tmux windows for scope.
Each Claude Code session runs in its own window within the main scope session.
This allows attaching/detaching without destroying sessions.
"""

import os
import shlex
import signal
import subprocess
import time
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


def _build_command_args(command: str, env: dict[str, str] | None) -> list[str]:
    """Build argv for tmux command execution without relying on shell parsing."""
    try:
        args = shlex.split(command)
    except ValueError as exc:
        raise TmuxError(f"Failed to parse command: {exc}") from exc

    if not args:
        raise TmuxError("Command is empty")

    if env:
        env_args = [f"{key}={value}" for key, value in env.items()]
        return ["env", *env_args, *args]

    return args


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


def is_server_running() -> bool:
    """Check if a tmux server is running and reachable."""
    try:
        result = subprocess.run(
            _tmux_cmd(["list-sessions"]),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False

    if result.returncode == 0:
        return True

    stderr = (result.stderr or "").lower()
    if "no server running" in stderr or "failed to connect to server" in stderr:
        return False

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

    # tmux new-session -d -s {name} -c {cwd} "{command}"
    cmd = _tmux_cmd(
        [
            "new-session",
            "-d",  # Detached
            "-s",
            name,  # Session name
            "-c",
            str(cwd),  # Working directory
        ]
    )
    cmd.extend(_build_command_args(command, env))

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


def _list_pane_pids(target: str) -> list[int]:
    """Return pane process IDs for a tmux target."""
    result = subprocess.run(
        _tmux_cmd(["list-panes", "-t", target, "-F", "#{pane_pid}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    pids: list[int] = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


def _process_tree(root_pids: set[int]) -> set[int]:
    """Collect descendants of root pids using the system process table."""
    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,ppid="],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return set()
    if result.returncode != 0:
        return set()

    children: dict[int, list[int]] = {}
    for line in result.stdout.strip().split("\n"):
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)

    descendants: set[int] = set()
    stack = list(root_pids)
    while stack:
        pid = stack.pop()
        for child in children.get(pid, []):
            if child in descendants:
                continue
            descendants.add(child)
            stack.append(child)
    return descendants


def _kill_pids(pids: set[int], sig: signal.Signals) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_pane_processes(target: str, timeout: float = 0.5) -> None:
    """Best-effort terminate processes for panes in a target."""
    root_pids = set(_list_pane_pids(target))
    if not root_pids:
        return

    descendants = _process_tree(root_pids)
    all_pids = root_pids | descendants

    _kill_pids(all_pids, signal.SIGTERM)
    time.sleep(timeout)
    remaining = {pid for pid in all_pids if _pid_alive(pid)}
    if remaining:
        _kill_pids(remaining, signal.SIGKILL)


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


def get_rightmost_pane_id() -> str | None:
    """Get the pane ID for the rightmost pane in the current window."""
    result = subprocess.run(
        _tmux_cmd(["list-panes", "-F", "#{pane_id}\t#{pane_right}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    rightmost_id = None
    rightmost_edge = None
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        pane_id, pane_right = parts
        try:
            pane_right_edge = int(pane_right)
        except ValueError:
            continue
        if rightmost_edge is None or pane_right_edge > rightmost_edge:
            rightmost_edge = pane_right_edge
            rightmost_id = pane_id

    return rightmost_id


def get_pane_option(pane_id: str, option: str) -> str | None:
    """Get a pane-local option value."""
    result = subprocess.run(
        _tmux_cmd(["display-message", "-t", pane_id, "-p", f"#{{@{option}}}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if value else None


def get_right_pane_session_id() -> str | None:
    """Get the scope session ID for the rightmost pane if present."""
    pane_id = get_rightmost_pane_id()
    if pane_id is None:
        return None
    return get_pane_option(pane_id, "scope_session_id")


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

    cmd = _tmux_cmd(
        [
            "split-window",
            "-h",  # Horizontal split
            "-c",
            str(cwd),  # Working directory
        ]
    )
    cmd.extend(_build_command_args(command, env))

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

    # If not in tmux, use the scope session
    current = get_current_session()
    if current is None:
        ensure_scope_session()
        target = get_scope_session()
    else:
        target = current

    # Keep panes alive on early command exit so join-pane can attach reliably.
    subprocess.run(
        _tmux_cmd(["set-option", "-g", "remain-on-exit", "on"]),
        capture_output=True,
        text=True,
    )

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
        ]
    )
    cmd.extend(_build_command_args(command, env))

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


def _get_tmux_lock_path(target: str | None = None) -> Path:
    """Get the path to the tmux operations lock file.

    Args:
        target: Optional target for per-target locking. If None, uses global lock.

    Returns:
        Path to the lock file.
    """
    from scope.core.state import ensure_scope_dir

    scope_dir = ensure_scope_dir()
    if target:
        # Per-target lock allows parallel operations on different targets
        # Sanitize target name for filesystem (replace special chars)
        safe_target = target.replace(":", "_").replace("/", "_").replace(".", "_")
        return scope_dir / f".tmux-{safe_target}.lock"
    return scope_dir / ".tmux.lock"


def _capture_pane(target: str, lines: int = 50) -> tuple[str, bool]:
    """Capture the last N lines from a tmux pane.

    Args:
        target: The tmux target pane.
        lines: Number of lines to capture from the end.

    Returns:
        Tuple of (captured content, success). If capture fails, returns ("", False).
    """
    result = subprocess.run(
        _tmux_cmd(["capture-pane", "-t", target, "-p", "-S", f"-{lines}"]),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout, True
    return "", False


def send_keys(
    target: str,
    keys: str,
    submit: bool = True,
    retries: int = 3,
    verify: bool = True,
) -> None:
    """Send keys to a tmux target (window or session).

    Uses per-target file-based locking to prevent race conditions when multiple
    processes send keys concurrently, while allowing parallel operations on
    different targets. Includes retry logic and optional verification.

    Args:
        target: The tmux target to send keys to (e.g., ":w0" for window, "scope-0" for session).
        keys: The text to send. If empty, only submits Enter when submit=True.
        submit: Whether to send C-m (Enter) after the keys to submit. Defaults to True.
        retries: Number of retry attempts on failure. Defaults to 3.
        verify: Whether to verify key delivery by checking pane content. Defaults to True.

    Raises:
        TmuxError: If tmux command fails after all retries.
    """
    import fcntl
    import sys
    import time

    # Ensure at least one attempt
    retries = max(1, retries)

    lock_path = _get_tmux_lock_path(target)
    last_error: str | None = None

    for attempt in range(retries):
        try:
            # Acquire exclusive lock for this target to serialize operations
            # Using "a" mode to avoid truncating (slightly more efficient)
            with open(lock_path, "a") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                # Note: lock is auto-released when file is closed (context manager exit)

                # Capture content before sending for verification
                content_before = ""
                capture_ok = True
                if verify and keys:
                    content_before, capture_ok = _capture_pane(target)

                if keys:
                    # Use -l flag to send keys literally (prevents special char interpretation)
                    cmd = _tmux_cmd(["send-keys", "-t", target, "-l", keys])
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        last_error = f"Failed to send keys to {target}: {result.stderr}"
                        raise TmuxError(last_error)

                if submit:
                    # Small delay to let keys be processed before Enter
                    time.sleep(0.05)
                    # C-m (Ctrl+M) is carriage return - submits in Claude Code
                    result = subprocess.run(
                        _tmux_cmd(["send-keys", "-t", target, "C-m"]),
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        last_error = (
                            f"Failed to send Enter to {target}: {result.stderr}"
                        )
                        raise TmuxError(last_error)

                # Verify keys were received by checking pane content changed
                # Only verify if we successfully captured before AND have non-empty keys
                if verify and keys and capture_ok:
                    time.sleep(0.15)  # Allow time for keys to appear
                    content_after, after_ok = _capture_pane(target)
                    # Only fail verification if capture succeeded both times
                    # and content is identical (nothing changed)
                    if after_ok and content_after == content_before:
                        last_error = f"Keys may not have been received by {target}"
                        raise TmuxError(last_error)

                # Success - return without raising
                return

        except TmuxError:
            if attempt < retries - 1:
                # Exponential backoff: 0.25s, 0.5s, 1s...
                backoff = 0.25 * (2**attempt)
                print(
                    f"[scope] send_keys retry {attempt + 1}/{retries} for {target}, "
                    f"waiting {backoff:.2f}s: {last_error}",
                    file=sys.stderr,
                )
                time.sleep(backoff)
            else:
                raise TmuxError(
                    f"Failed to send keys after {retries} attempts: {last_error}"
                )
