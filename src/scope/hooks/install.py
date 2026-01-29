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
        }
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
    return command.startswith("scope-hook") or "scope spawn" in command


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


RALPH_SKILL_CONTENT = """---
name: ralph
description: Iterative refinement loops. Use when improving outputs through critique cycles, quality improvement, polish/editing tasks, or convergent optimization toward a goal.
---

# RALPH: Iterative Refinement Loop

You are an **orchestrator only**. Do not do any work directly—only spawn subagents and evaluate their outputs.

Critique → Evaluate → Act → Repeat until done.

## 1. Lock Variables (ask one at a time)
- **Goal**: What does done look like?
- **Max iterations**: Default 5
- **Delta threshold**: When is improvement too small to continue?

Do not proceed until confirmed.

## 2. Loop

Each spawn must include both the **global task** (overall goal) and the **tactical task** (specific action):

```
while iterations < max:
    scope spawn "Global: {goal}. Tactical: Critique the current state—what's wrong, what's missing, how far from done?"
    scope wait
    # Read critique from session output

    if goal_met(critique) or delta < threshold:
        break

    scope spawn "Global: {goal}. Tactical: Improve based on this critique: {critique}"
    scope wait
```

## 3. Exit
Report: why stopped, what changed, current state.

## Rules
- You are an orchestrator: spawn and evaluate only, never do the work yourself
- Each spawn gets both global context (the goal) and tactical context (the specific step)
- Never improve without evaluating the critique first
- Stop early if delta is negligible
"""

TDD_SKILL_CONTENT = """---
name: tdd
description: Test-driven development. Use for new feature implementation, bug fixes requiring regression tests, or any code change needing test coverage.
---

# TDD: Test-Driven Development

Red → Green → Refactor. Tests first, always.

## Cycle
1. **Red**: Write a failing test for the next piece of functionality
2. **Green**: Write minimal code to make it pass
3. **Refactor**: Clean up while keeping tests green

## Workflow
```
scope spawn "Write failing test for: {feature}"
scope wait

scope spawn "Implement minimal code to pass the test"
scope wait

scope spawn "Refactor: clean up implementation, ensure tests pass"
scope wait
```

## Rules
- Never write implementation before the test exists
- Each test should fail for the right reason before you fix it
- Keep cycles small: one behavior per test
- Run tests after every change
- Refactor only when green
"""

RLM_SKILL_CONTENT = """---
name: rlm
description: Large context exploration. Use when exploring large codebases (>100K tokens), unknown codebase structure, finding needles in haystacks, or iterative examination of unfamiliar content.
---

# RLM: Recursive Language Model Exploration

Peek → Grep → Dive. Explore large contexts without flooding your window.

## Pattern
1. **Peek**: Inspect structure first (head, tail, outline)
2. **Grep**: Narrow search with patterns before diving deep
3. **Dive**: Spawn subagents for focused analysis of specific sections

## Workflow
```
# 1. Peek at structure
Read first 100 lines, check file structure, identify sections

# 2. Grep to locate
Search for relevant patterns before spawning

# 3. Dive on specific targets
scope spawn "Analyze {specific_section} in {file}"
scope wait
```

## Rules
- ALWAYS peek before spawning - understand structure first
- Use grep to narrow, don't spawn "analyze everything"
- Max dive depth: 3 levels
- Each dive must be smaller scope than parent
- If >50% of dives return empty, try different patterns
"""

MAP_REDUCE_SKILL_CONTENT = """---
name: map-reduce
description: Parallel independent tasks with aggregation. Use for file-by-file analysis, aggregatable results across chunks, or when N workers can process simultaneously.
---

# Map-Reduce: Parallel Workers + Aggregation

Fork N workers → Wait all → Reduce results.

## Phases
1. **Map**: Spawn N independent workers in parallel
2. **Wait**: Block until all complete
3. **Reduce**: Synthesize results into final output

## Workflow
```
# Map phase - spawn 2-3 workers MAX (batch items into chunks)
scope spawn "Process batch 1: files A, B, C"
scope spawn "Process batch 2: files D, E, F"

# Wait phase - block for all
scope wait

# Reduce phase - synthesize (you do this, or spawn reducer)
Combine results from all workers into final output
```

## Rules
- Batch items into 2-3 chunks, don't spawn per-item
- Workers MUST be independent (no shared state)
- Each worker gets a specific, bounded chunk
- Wait for ALL workers before reducing
- Reducer sees only outputs, not worker context
- If a worker fails, decide: retry, skip, or abort
"""

MAKER_CHECKER_SKILL_CONTENT = """---
name: maker-checker
description: High-stakes work needing independent validation. Use for security-sensitive code, critical outputs needing review, or separation of creation and verification.
---

# Maker-Checker: Separation of Concerns

One makes, another validates. Never self-review.

## Roles
- **Maker**: Creates the artifact (code, plan, analysis)
- **Checker**: Reviews, critiques, validates independently

## Workflow
```
# Maker creates
scope spawn "Create: {artifact_description}"
scope wait

# Checker validates (fresh context, no maker bias)
scope spawn "Review: validate {artifact}, check for {criteria}"
scope wait

# If checker finds issues, iterate
scope spawn "Fix: address these issues: {checker_feedback}"
scope wait
```

## Rules
- Maker and checker MUST be separate agents (fresh context)
- Checker never sees maker's reasoning, only output
- Define validation criteria upfront
- Iterate until checker approves or max iterations hit
- For critical work: use different models (maker=fast, checker=thorough)
"""

DAG_SKILL_CONTENT = """---
name: dag
description: Multi-step workflows with task dependencies. Use for build pipelines requiring ordered execution, or complex orchestration with partial parallelism.
---

# DAG: Dependency Graph Execution

Tasks with dependencies. Use --id and --after for ordering.

## Syntax
```
scope spawn --id=A "Task A (no deps)"
scope spawn --id=B "Task B (no deps)"
scope spawn --id=C --after=A,B "Task C (needs A and B)"
scope spawn --id=D --after=C "Task D (needs C)"
```

## Workflow
```
# 1. Identify tasks and dependencies
# 2. Assign IDs to each task
# 3. Spawn with --after for dependencies
# 4. scope wait blocks until all complete

scope spawn --id=parse "Parse input files"
scope spawn --id=validate "Validate schema"
scope spawn --id=transform --after=parse,validate "Transform data"
scope spawn --id=output --after=transform "Generate output"
scope wait
```

## Rules
- Tasks without --after start immediately
- --after=X,Y waits for BOTH X and Y
- Cycles are forbidden (A->B->A)
- Failed dependency = dependent task skipped
- Use descriptive IDs (not just a,b,c)
"""

SCOPE_COMMAND_CONTENT = """<prompt>
  <instructions>
You are scope-managed. Task tool is disabled; use `scope spawn` for subagents.

## MANDATORY: Pattern Selection (Passive Skill Index)

Before doing ANY work, you MUST select **at most one** pattern below and follow it.

**Key idea (from recent evals):** *"agent can access X" ≠ "agent will access X"*. So we make the playbook **always present** instead of relying on a separate retrieval/tool invocation.

| Pattern | Trigger (examples) | What to do (canonical) |
|---|---|---|
| **RALPH (critique → improve loop)** | improve/refine/polish/iterate | Spawn alternating critique + improve subtasks until done. |
| **TDD (red → green → refactor)** | add tests / fix bug with regression / implement feature | Spawn: write failing test → implement minimal → refactor (keep tests green). |
| **RLM (peek → grep → dive)** | explore/find/understand codebase; large file | Peek structure first, grep to narrow, then spawn focused dives. |
| **MAP‑REDUCE** | process many items/files; aggregatable | Spawn 2–3 chunked workers → wait all → reduce/summarize. |
| **MAKER‑CHECKER** | security/critical/review/high‑stakes | One agent makes; a different agent validates; iterate on issues. |
| **DAG** | pipeline; dependencies; A then B then C | Encode deps with `--id` and `--after`; wait on leaves. |

## Enforcement Protocol

1. **STOP** — don’t start executing immediately.
2. **CLASSIFY** — does one pattern above clearly match?
3. **FOLLOW or PROCEED**:
   - If a pattern matches: **follow it explicitly** using `scope spawn` / `scope wait`.
   - If no pattern matches: proceed directly, but keep the scope small.

## Examples

- "Improve this code quality" → RALPH
- "Add a new endpoint with tests" → TDD
- "Find where errors are handled" → RLM
- "Process all .py files" → MAP‑REDUCE
- "Review this security‑critical change" → MAKER‑CHECKER
- "Build, then test, then deploy" → DAG
- "Rename this variable" → no pattern; do it directly

## Context Limit (100k tokens)

When blocked by context gate:
- **HANDOFF**: `scope spawn "Continue: [progress] + [remaining work]"`
- **SPLIT**: `scope spawn "subtask 1"` + `scope spawn "subtask 2"` + `scope wait`

## Commands

| Command | Effect |
|---------|--------|
| `scope spawn "task"` | Start subagent |
| `scope spawn --id=X --after=Y "task"` | Start with dependency |
| `scope poll` | Check status (non-blocking) |
| `scope wait` | Block until complete |

## Recursion Guard

- Subtasks MUST be strictly smaller than parent
- NEVER spawn a task similar to what you received—do it yourself
- Include specific context: files, functions, progress

## Limits

- **Max 2-3 concurrent subagents.** Before spawning, run `scope poll` to check active count.
- **Depth awareness.** Your depth = dots in `$SCOPE_SESSION_ID` + 1. The deeper you are, the more you should bias toward doing work directly vs spawning. Beyond depth 5, avoid spawning entirely.

Batch work into 2-3 chunks rather than spawning per-item.

## CLI Quick Reference

```
scope                  # Launch TUI (shows all sessions)
scope spawn "task"     # Start subagent with task
scope spawn --plan     # Start in plan mode
scope spawn --model=X  # Use specific model (opus/sonnet/haiku)
scope poll [id]        # Check status (non-blocking)
scope wait [id]        # Block until done
scope abort <id>       # Kill a session
scope trajectory <id>  # Export conversation JSON
scope setup            # Reinstall hooks/skills
scope uninstall        # Remove scope integration
```

DAG options: `--id=NAME --after=A,B` for dependency ordering.
  </instructions>
</prompt>

$ARGUMENTS
"""


def get_claude_commands_dir() -> Path:
    """Get the path to Claude Code's custom commands directory."""
    return Path.home() / ".claude" / "commands"


def get_claude_skills_dir() -> Path:
    """Get the path to Claude Code's skills directory."""
    return Path.home() / ".claude" / "skills"


def install_custom_commands() -> None:
    """Install custom Claude Code commands for scope."""
    commands_dir = get_claude_commands_dir()
    commands_dir.mkdir(parents=True, exist_ok=True)

    # Install /scope command (only scope stays as custom command)
    scope_path = commands_dir / "scope.md"
    scope_path.write_text(SCOPE_COMMAND_CONTENT)


def install_skills() -> None:
    """Install Claude Code skills for scope orchestration patterns.

    Skills are installed to ~/.claude/skills/<skill-name>/SKILL.md
    Each SKILL.md has YAML frontmatter with name and description.
    """
    skills_dir = get_claude_skills_dir()

    skills = {
        "ralph": RALPH_SKILL_CONTENT,
        "tdd": TDD_SKILL_CONTENT,
        "rlm": RLM_SKILL_CONTENT,
        "map-reduce": MAP_REDUCE_SKILL_CONTENT,
        "maker-checker": MAKER_CHECKER_SKILL_CONTENT,
        "dag": DAG_SKILL_CONTENT,
    }

    for skill_name, content in skills.items():
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(content)


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


def _skills_version() -> str:
    """Get version hash for skills based on skill content."""
    return content_hash(
        RALPH_SKILL_CONTENT,
        TDD_SKILL_CONTENT,
        RLM_SKILL_CONTENT,
        MAP_REDUCE_SKILL_CONTENT,
        MAKER_CHECKER_SKILL_CONTENT,
        DAG_SKILL_CONTENT,
    )


def _commands_version() -> str:
    """Get version hash for custom commands."""
    return content_hash(SCOPE_COMMAND_CONTENT)


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

    # Check and update skills
    skills_ver = _skills_version()
    if force or installed_versions.get("skills") != skills_ver:
        try:
            install_skills()
            installed_versions["skills"] = skills_ver
            updated.append("skills")
        except Exception as e:
            if not quiet:
                print(f"Warning: Failed to install skills: {e}", file=sys.stderr)

    # Check and update custom commands
    commands_ver = _commands_version()
    if force or installed_versions.get("commands") != commands_ver:
        try:
            install_custom_commands()
            installed_versions["commands"] = commands_ver
            updated.append("commands")
        except Exception as e:
            if not quiet:
                print(f"Warning: Failed to install commands: {e}", file=sys.stderr)

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
