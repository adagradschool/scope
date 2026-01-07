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
        }
    ],
    "Stop": [
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": "scope-hook stop"}],
        }
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


def install_hooks() -> None:
    """Install scope hooks into Claude Code settings.

    This function:
    1. Reads existing ~/.claude/settings.json (creates if missing)
    2. Merges scope hook configuration into the hooks section
    3. Writes the updated settings back

    Existing hooks are preserved - scope hooks are added/updated alongside them.
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

    # Merge our hook configuration
    for event, event_hooks in HOOK_CONFIG.items():
        if event not in hooks:
            hooks[event] = []

        # Check if scope hook already exists for this event
        existing_commands = {
            h.get("hooks", [{}])[0].get("command", "")
            for h in hooks[event]
            if isinstance(h, dict)
        }

        for hook_entry in event_hooks:
            hook_command = hook_entry.get("hooks", [{}])[0].get("command", "")
            if hook_command not in existing_commands:
                hooks[event].append(hook_entry)

    settings["hooks"] = hooks

    # Write back with pretty formatting
    settings_path.write_bytes(orjson.dumps(settings, option=orjson.OPT_INDENT_2))


def get_global_claude_md_path() -> Path:
    """Get the path to global CLAUDE.md."""
    return Path.home() / ".claude" / "CLAUDE.md"


RALPH_COMMAND_CONTENT = """<prompt>
  <params>
    goal # Primary outcome or acceptance criteria
    max_iterations # Maximum number of loop iterations
    delta_threshold # Minimum improvement needed to continue
  </params>

  <system>
    You are the root orchestrator for a RALPH loop implemented with Scope.
    Always interview the user first to lock requirements and stopping criteria.
    Never start spawning subagents until the variables are confirmed.
  </system>

  <instructions>
    # RALPH Loop (Root-Agent Orchestration)

    ## Phase 0: Interview
    Gather the following variables through a conversational interview.
    IMPORTANT: Ask ONE question at a time. Wait for the user's response before
    asking the next question. This keeps the conversation natural and allows
    you to gather maximum information through follow-up questions.

    Variables to collect:
    - Goal / acceptance criteria
    - max_iterations
    - delta_threshold (what counts as meaningful improvement)
    - Quality metric or rubric (if any)
    - Constraints (time, budget, risk tolerance, allowed changes)

    If any answer is ambiguous or incomplete, ask clarifying follow-ups before
    moving to the next variable. Do not proceed to Phase 1 until all variables
    are confirmed.

    ## Phase 1: Initialize
    Summarize the variables back to the user and get confirmation.
    Define the initial state and success criteria in 1-3 sentences.

    ## Phase 2: Iterate
    For each iteration (i from 1 to max_iterations):

    1) CRITIQUE: Spawn a critique subagent to evaluate the current state against
       the goal. Wait for the critique results.

    2) EVALUATE STOPPING CRITERION: Pass the critique to a delta-evaluator
       subagent. The evaluator judges whether:
       - The critique indicates the goal is already met, OR
       - The critique is small enough (< delta_threshold) that further
         iteration would not yield meaningful improvement
       If either condition is true, STOP the loop. Do not proceed to step 3.

    3) ACT: Only after the evaluator approves continuation, spawn an improvement
       subagent to apply the critique. The critique from step 1 is the input
       for this step.

    Always pass the current variables into each subagent task. Each iteration
    MUST be a new subagent session in Scope. Never spawn the improvement
    subagent without first getting approval from the evaluator.

    ## Phase 3: Exit
    Report why the loop stopped (goal met, delta too small, or max iterations).
    Provide a concise summary of changes and current state.

    ## Always
    - Use `scope spawn` for subagent work.
    - Use `scope wait` to gather results.
    - Ask the user to adjust variables if new constraints or goals emerge.
  </instructions>
</prompt>
"""

SCOPE_COMMAND_CONTENT = """<prompt>
  <instructions>
You are a scope-managed agent. Before starting work, run estimation:

```bash
scope estimate "your task description here"
```

Use the `recommend` field from the output to classify:

- **atomic**: Do it yourself. Single focused action.
- **composite**: 2+ independent parts. Spawn each with `scope spawn "subtask"`, wait with `scope wait`.
- **borderline**: Use judgment - if files are related, do it yourself. If independent, spawn.
- **unclear**: MUST spawn ONE exploration subagent with `scope spawn`, then `scope wait`. After results return, re-classify. You are FORBIDDEN from exploring yourself (no Grep, Glob, Read for exploration).

State your classification: **TASK TYPE: [ATOMIC/COMPOSITE/BORDERLINE/UNCLEAR]** with the estimate output.

Rules:
1. NEVER use the Task tool - it is blocked. Use `scope spawn` instead.
2. Subtasks must be smaller than the parent task. If not, do it yourself.
3. scope spawn -> starts a subagent
   scope poll -> poll subagent status without blocking
   scope wait -> blocking call to subagent
4. Trust the estimate. Don't override unless you have specific knowledge it missed.
5. Common mistake: Rationalizing "I'll just explore myself" when estimate says unclear. Don't do this.
  </instructions>
</prompt>

$ARGUMENTS
"""


def get_claude_commands_dir() -> Path:
    """Get the path to Claude Code's custom commands directory."""
    return Path.home() / ".claude" / "commands"


def install_custom_commands() -> None:
    """Install custom Claude Code commands for scope."""
    commands_dir = get_claude_commands_dir()
    commands_dir.mkdir(parents=True, exist_ok=True)

    # Install /ralph command
    ralph_path = commands_dir / "ralph.md"
    ralph_path.write_text(RALPH_COMMAND_CONTENT)

    # Install /scope command
    scope_path = commands_dir / "scope.md"
    scope_path.write_text(SCOPE_COMMAND_CONTENT)


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
            hooks[event] = [
                h
                for h in hooks[event]
                if not any(
                    hh.get("command", "").startswith("scope-hook")
                    for hh in h.get("hooks", [])
                )
            ]
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


def install_ccstatusline() -> None:
    """Install and configure ccstatusline for Claude Code.

    This function:
    1. Adds statusLine to ~/.claude/settings.json to enable ccstatusline
    2. Creates ~/.config/ccstatusline/settings.json with context percentage enabled
    """
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
    ccstatusline_path = get_ccstatusline_settings_path()
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
