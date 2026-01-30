"""Hook installation for Claude Code integration.

This module provides functions to install scope hooks into Claude Code's
settings.json file and tmux hooks for pane exit detection.
"""

import shlex
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import orjson

from scope.core.config import content_hash, read_all_versions, write_all_versions

# Hook configuration to install
HOOK_CONFIG = {
    "PreToolUse": [
        {
            "matcher": "Task",
            "hooks": [
                {
                    "type": "command",
                    "command": "echo 'BLOCKED: Use scope spawn instead of Task tool. Run: scope spawn \"your task\"' && exit 1",
                }
            ],
        },
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": "scope-hook block-background-scope",
                }
            ],
        },
        {
            "matcher": "Edit|Write|Bash|NotebookEdit|Read|Grep|Glob",
            "hooks": [
                {
                    "type": "command",
                    "command": "sh -c '[ -n \"$SCOPE_SESSION_ID\" ] && scope-hook context-gate'",
                }
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": "scope-hook activity"}],
        }
    ],
    "UserPromptSubmit": [
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": "scope-hook task"}],
        },
    ],
    "Stop": [
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": "scope-hook context"}],
        },
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": "scope-hook stop"}],
        },
    ],
    "SessionStart": [
        {
            "matcher": "startup",
            "hooks": [{"type": "command", "command": "scope-hook ready"}],
        }
    ],
}


def get_claude_settings_path() -> Path:
    """Get the path to Claude Code's settings.json."""
    return Path.home() / ".claude" / "settings.json"


def _is_scope_hook(hook_entry: dict) -> bool:
    """Check if a hook entry is a scope hook."""
    hooks = hook_entry.get("hooks", [])
    if not hooks:
        return False
    command = hooks[0].get("command", "")
    return "scope-hook" in command or "scope spawn" in command


def install_hooks() -> None:
    """Install scope hooks into Claude Code settings.

    This function is idempotent:
    1. Reads existing ~/.claude/settings.json (creates if missing)
    2. Removes all existing scope hooks
    3. Adds current scope hooks from HOOK_CONFIG
    4. Preserves non-scope hooks in their original order

    Existing non-scope hooks are preserved.
    """
    settings_path = get_claude_settings_path()

    # Ensure .claude directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing settings
    if settings_path.exists():
        content = settings_path.read_bytes()
        settings = orjson.loads(content) if content else {}
    else:
        settings = {}

    # Get or create hooks section
    hooks = settings.get("hooks", {})

    # For each event type, remove existing scope hooks and add current ones
    for event, scope_hooks in HOOK_CONFIG.items():
        if event in hooks:
            # Filter out existing scope hooks, keep user hooks
            user_hooks = [h for h in hooks[event] if not _is_scope_hook(h)]
        else:
            user_hooks = []

        # Add current scope hooks followed by user hooks
        hooks[event] = list(scope_hooks) + user_hooks

    # Also clean up any scope hooks in events not in current HOOK_CONFIG
    for event in list(hooks.keys()):
        if event not in HOOK_CONFIG:
            hooks[event] = [h for h in hooks[event] if not _is_scope_hook(h)]
            # Remove empty event entries
            if not hooks[event]:
                del hooks[event]

    settings["hooks"] = hooks

    # Write back with pretty formatting
    settings_path.write_bytes(orjson.dumps(settings, option=orjson.OPT_INDENT_2))


def get_global_claude_md_path() -> Path:
    """Get the path to global CLAUDE.md."""
    return Path.home() / ".claude" / "CLAUDE.md"


SCOPE_SKILL_CONTENT = """---
name: scope
description: Enable scope-managed orchestration with doer-checker loops and DAG dependencies.
---

# Scope: Orchestration CLI

You are scope-managed. Task tool is disabled; use `scope spawn` for subagents.

## Core Primitive: The Loop

Every `scope spawn` runs a **doer-checker loop**:

1. The doer executes the task.
2. A checker (spawned with `--checker`) reviews the work.
3. If the checker finds issues, the doer retries (up to `--max-iterations`).

`--checker` is **required** — every spawn MUST include it. The spawn will fail without it. Use a shell command (exit 0 = pass, non-zero = fail) or an agent checker (prefix with `agent:`).

Examples:
- `--checker "pytest tests/"` — shell command checker
- `--checker "agent: Verify the fix is correct and minimal. ACCEPT or RETRY."` — agent checker

## DAGs: Dependency Ordering

Use `--id` and `--after` to build task graphs:

```bash
scope spawn --id build "Build the project" --checker "make check"
scope spawn --id test --after build "Run tests" --checker "pytest"
scope spawn --id lint --after build "Run linter" --checker "ruff check ."
scope wait test lint
```

`test` and `lint` both wait for `build`, then run in parallel.

## Context Limit (100k tokens)

When blocked by context gate:
- **HANDOFF**: `scope spawn "Continue: [progress] + [remaining work]" --checker "agent: Verify work completed. ACCEPT/RETRY."`
- **SPLIT**: spawn subtasks with `--checker`, then `scope wait`

## Recursion Guard

- Subtasks MUST be strictly smaller than parent
- NEVER spawn a task similar to what you received -- do it yourself
- Include specific context: files, functions, progress

## Limits

- **Max 2-3 concurrent subagents.** Before spawning, run `scope poll` to check active count.
- **Depth awareness.** Your depth = dots in `$SCOPE_SESSION_ID` + 1. The deeper you are, the more you should bias toward doing work directly vs spawning. Beyond depth 5, avoid spawning entirely.

Batch work into 2-3 chunks rather than spawning per-item.

## CLI Quick Reference

```
scope spawn "task" --checker "cmd"     # Start subagent (--checker REQUIRED)
scope spawn "task" --checker "agent: Review for correctness. ACCEPT/RETRY."
scope spawn --id=X --after=Y --checker "cmd"  # With dependency ordering
scope spawn --plan --checker "cmd"     # Start in plan mode
scope poll [id]                        # Check status (non-blocking)
scope wait [id]                        # Block until done
scope abort <id>                       # Kill a session
scope trajectory <id>                  # View what a session did
scope setup                            # Reinstall hooks
scope uninstall                        # Remove scope integration
```
"""


def get_claude_skills_dir() -> Path:
    """Get the path to Claude Code's skills directory."""
    return Path.home() / ".claude" / "skills"


def install_scope_skill() -> None:
    """Install the scope skill to ~/.claude/skills/scope/SKILL.md."""
    skill_dir = get_claude_skills_dir() / "scope"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(SCOPE_SKILL_CONTENT)


def install_tmux_hooks() -> tuple[bool, str | None]:
    """Install tmux hooks for pane exit detection.

    Sets up a global pane-died hook that calls scope-hook to update
    session state when a pane's program exits.

    We use pane-died (not pane-exited) because windows are created with
    remain-on-exit=on. This keeps the pane alive so we can read #{window_name}
    to identify which session exited.

    Returns:
        Tuple of (success, error_message). On success: (True, None).
        On failure: (False, error_message) with details about what went wrong.
    """
    from scope.core.tmux import _tmux_cmd

    # Set global remain-on-exit so panes stay alive for hook to read window name
    remain_result = subprocess.run(
        _tmux_cmd(["set-option", "-g", "remain-on-exit", "on"]),
        capture_output=True,
        text=True,
    )

    if remain_result.returncode != 0:
        error = remain_result.stderr.strip() or "Unknown error"
        return False, f"Failed to set remain-on-exit option: {error}"

    # The hook command passes the window name and pane id to the handler
    # #{window_name} is expanded by tmux (e.g., "w0-2")
    # #{pane_id} is needed to kill the pane after processing (since remain-on-exit is on)
    # Use the current Python to avoid stale entry point scripts
    python_exec = shlex.quote(sys.executable)
    hook_cmd = (
        'run-shell "'
        f"{python_exec} -m scope.hooks.handler pane-died "
        '\\"#{window_name}\\" \\"#{pane_id}\\" \\"#{@scope_session_id}\\" '
        '\\"#{pane_current_path}\\""'
    )

    result = subprocess.run(
        _tmux_cmd(["set-hook", "-g", "pane-died", hook_cmd]),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown error"
        return False, f"Failed to set pane-died hook: {error}"

    # Verify the hook was actually set by reading it back
    verify = subprocess.run(
        _tmux_cmd(["show-hooks", "-g", "pane-died"]),
        capture_output=True,
        text=True,
    )

    if "pane-died" not in verify.stdout or "scope.hooks.handler" not in verify.stdout:
        return False, "Hook verification failed: hook was not set correctly"

    return True, None


def uninstall_tmux_hooks() -> None:
    """Remove tmux hooks installed by scope."""
    from scope.core.tmux import _tmux_cmd

    subprocess.run(
        _tmux_cmd(["set-hook", "-gu", "pane-died"]),
        capture_output=True,
    )


def uninstall_hooks() -> None:
    """Remove scope hooks from Claude Code settings.

    This function removes only scope-specific hooks, leaving other hooks intact.
    """
    settings_path = get_claude_settings_path()

    if not settings_path.exists():
        return

    content = settings_path.read_bytes()
    if not content:
        return

    settings = orjson.loads(content)
    hooks = settings.get("hooks", {})

    # Remove scope hooks from each event
    for event in HOOK_CONFIG:
        if event in hooks:
            hooks[event] = [h for h in hooks[event] if not _is_scope_hook(h)]
            # Remove empty event entries
            if not hooks[event]:
                del hooks[event]

    if hooks:
        settings["hooks"] = hooks
    elif "hooks" in settings:
        del settings["hooks"]

    settings_path.write_bytes(orjson.dumps(settings, option=orjson.OPT_INDENT_2))


def get_ccstatusline_settings_path() -> Path:
    """Get the path to ccstatusline's settings.json."""
    return Path.home() / ".config" / "ccstatusline" / "settings.json"


def install_ccstatusline(force: bool = False) -> None:
    """Install and configure ccstatusline for Claude Code.

    This function:
    1. Adds statusLine to ~/.claude/settings.json to enable ccstatusline
    2. Creates ~/.config/ccstatusline/settings.json with context percentage enabled

    Args:
        force: If False, skip if ccstatusline config already exists.
               If True, always install (used when user explicitly runs 'scope setup').
    """
    ccstatusline_path = get_ccstatusline_settings_path()

    # Skip if config exists and not forcing (auto-setup shouldn't override user's config)
    if not force and ccstatusline_path.exists():
        return

    # 1. Add statusLine to Claude settings
    settings_path = get_claude_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        content = settings_path.read_bytes()
        settings = orjson.loads(content) if content else {}
    else:
        settings = {}

    settings["statusLine"] = {
        "type": "command",
        "command": "npx ccstatusline@latest",
    }
    settings_path.write_bytes(orjson.dumps(settings, option=orjson.OPT_INDENT_2))

    # 2. Create ccstatusline config with context percentage
    ccstatusline_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate fresh UUIDs for each widget
    ccstatusline_settings = {
        "version": 3,
        "lines": [
            [
                {"id": str(uuid4()), "type": "model", "color": "cyan"},
                {"id": str(uuid4()), "type": "separator"},
                {"id": str(uuid4()), "type": "context-percentage", "color": "green"},
                {"id": str(uuid4()), "type": "separator"},
                {"id": str(uuid4()), "type": "cwd", "color": "blue"},
                {"id": str(uuid4()), "type": "separator"},
                {"id": str(uuid4()), "type": "git-branch", "color": "magenta"},
                {"id": str(uuid4()), "type": "separator"},
                {"id": str(uuid4()), "type": "git-changes", "color": "yellow"},
            ],
            [],
            [],
        ],
        "flexMode": "full-minus-40",
        "compactThreshold": 60,
        "colorLevel": 2,
        "inheritSeparatorColors": False,
        "globalBold": False,
        "powerline": {
            "enabled": False,
            "separators": ["\ue0b0"],
            "separatorInvertBackground": [False],
            "startCaps": [],
            "endCaps": [],
            "theme": None,
            "autoAlign": False,
        },
    }

    ccstatusline_path.write_bytes(
        orjson.dumps(ccstatusline_settings, option=orjson.OPT_INDENT_2)
    )


# Version hashes for idempotent setup
def _hooks_version() -> str:
    """Get version hash for hooks based on HOOK_CONFIG content."""
    return content_hash(orjson.dumps(HOOK_CONFIG).decode())


def _skill_version() -> str:
    """Get version hash for the scope skill."""
    return content_hash(SCOPE_SKILL_CONTENT)


def _ccstatusline_version() -> str:
    """Get version hash for ccstatusline config structure."""
    # Hash the structure, not the UUIDs (those are regenerated each time)
    return content_hash("ccstatusline_v3_context_percentage")


def _tmux_hooks_version() -> str:
    """Get version hash for tmux hooks based on hook command structure."""
    # Version based on the pane-died hook command structure
    return content_hash("tmux_pane_died_v1_scope_handler")


def ensure_setup(quiet: bool = True, force: bool = False) -> None:
    """Ensure all setup components are current, updating stale ones silently.

    This is idempotent - only updates components whose version has changed.
    Called automatically on every scope invocation.

    Args:
        quiet: If True, suppress output messages (default for auto-setup).
        force: If True, force reinstall of all components (used by 'scope setup').
    """
    from scope.core.tmux import is_installed as tmux_is_installed
    from scope.core.tmux import is_server_running

    # Skip if tmux not installed (can't do full setup)
    if not tmux_is_installed():
        return

    # Read all versions once at start
    installed_versions = read_all_versions()
    updated = []

    # Check and update hooks
    hooks_ver = _hooks_version()
    if force or installed_versions.get("hooks") != hooks_ver:
        try:
            install_hooks()
            installed_versions["hooks"] = hooks_ver
            updated.append("hooks")
        except Exception as e:
            if not quiet:
                print(f"Warning: Failed to install hooks: {e}", file=sys.stderr)

    # Check and update scope skill
    skill_ver = _skill_version()
    if force or installed_versions.get("skill") != skill_ver:
        try:
            install_scope_skill()
            installed_versions["skill"] = skill_ver
            updated.append("skill")
        except Exception as e:
            if not quiet:
                print(f"Warning: Failed to install skill: {e}", file=sys.stderr)

    # Check and update tmux hooks
    tmux_ver = _tmux_hooks_version()
    if force or installed_versions.get("tmux_hooks") != tmux_ver:
        if is_server_running():
            try:
                success, error = install_tmux_hooks()
                if success:
                    installed_versions["tmux_hooks"] = tmux_ver
                    updated.append("tmux_hooks")
                elif not quiet:
                    print(
                        f"Warning: Failed to install tmux hooks: {error}",
                        file=sys.stderr,
                    )
            except Exception as e:
                if not quiet:
                    print(
                        f"Warning: Failed to install tmux hooks: {e}", file=sys.stderr
                    )

    # Check and update ccstatusline (only if not already configured OR force)
    ccstatusline_ver = _ccstatusline_version()
    if force or installed_versions.get("ccstatusline") != ccstatusline_ver:
        try:
            install_ccstatusline(force=force)
            installed_versions["ccstatusline"] = ccstatusline_ver
            updated.append("ccstatusline")
        except Exception as e:
            if not quiet:
                print(f"Warning: Failed to install ccstatusline: {e}", file=sys.stderr)

    # Write all versions once at end
    if updated:
        try:
            write_all_versions(installed_versions)
        except Exception as e:
            if not quiet:
                print(f"Warning: Failed to save setup state: {e}", file=sys.stderr)

        if not quiet:
            import click

            click.echo(f"Scope setup updated: {', '.join(updated)}")
