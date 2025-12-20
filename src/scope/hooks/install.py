"""Hook installation for Claude Code integration.

This module provides functions to install scope hooks into Claude Code's
settings.json file.
"""

from pathlib import Path

import orjson

# Hook configuration to install
HOOK_CONFIG = {
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
    settings_path.write_bytes(
        orjson.dumps(settings, option=orjson.OPT_INDENT_2)
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

    settings_path.write_bytes(
        orjson.dumps(settings, option=orjson.OPT_INDENT_2)
    )
