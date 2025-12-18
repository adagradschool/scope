# Architecture

## Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.10+ | Ship fast, maintainable |
| CLI | Click | Standard, composable |
| TUI | Textual | Rich widgets, async-first |
| File watching | watchfiles | Rust-based, cross-platform, instant |
| Multiplexer | tmux | Ubiquitous, stable |
| Distribution | PyPI + uv | Zero bundling, ~1MB |
| IPC | Filesystem | Inspectable, debuggable |

## Package Structure

```
scope/
├── pyproject.toml
├── README.md
└── src/
    └── scope/
        ├── __init__.py
        ├── __main__.py         # python -m scope
        │
        ├── cli.py              # Click command group
        │
        ├── commands/
        │   ├── __init__.py
        │   ├── spawn.py        # scope spawn
        │   ├── poll.py         # scope poll
        │   ├── wait.py         # scope wait
        │   └── setup.py        # scope setup
        │
        ├── tui/
        │   ├── __init__.py
        │   ├── app.py          # Textual App
        │   ├── widgets/
        │   │   ├── __init__.py
        │   │   ├── session_tree.py
        │   │   ├── header.py
        │   │   └── footer.py
        │   └── screens/
        │       ├── __init__.py
        │       └── main.py
        │
        ├── core/
        │   ├── __init__.py
        │   ├── state.py        # Session CRUD
        │   ├── session.py      # Session dataclass
        │   ├── tree.py         # Flat → hierarchical
        │   ├── contract.py     # Contract generation
        │   └── tmux.py         # tmux wrapper
        │
        └── hooks/
            ├── __init__.py
            ├── install.py      # Install CC hooks
            └── handler.py      # Hook handler script
```

## pyproject.toml

```toml
[project]
name = "scope-cli"
version = "0.1.0"
description = "Subagent orchestration for Claude Code"
requires-python = ">=3.10"
dependencies = [
    "textual>=0.50.0",
    "click>=8.0.0",
    "orjson>=3.9.0",
    "watchfiles>=0.21.0",
]

[project.scripts]
scope = "scope.cli:main"
scope-hook = "scope.hooks.handler:main"
```

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                  CLI                                        │
│                                (Click)                                      │
│     scope spawn    scope poll    scope wait    scope top    scope setup     │
└────────┬──────────────┬─────────────┬────────────┬──────────────┬───────────┘
         │              │             │            │              │
         ▼              ▼             ▼            ▼              ▼
┌─────────────┐  ┌───────────┐  ┌──────────┐  ┌────────┐  ┌─────────────┐
│   Spawn     │  │   Poll    │  │   Wait   │  │  TUI   │  │   Setup     │
│             │  │           │  │          │  │(Textual│  │             │
│ - next_id   │  │ - read    │  │ - poll   │  │  App)  │  │ - hooks     │
│ - write     │  │   state   │  │   loop   │  │        │  │ - tmux      │
│   session   │  │ - output  │  │ - timeout│  │        │  │ - CLAUDE.md │
│ - tmux new  │  │           │  │          │  │        │  │             │
└──────┬──────┘  └─────┬─────┘  └────┬─────┘  └───┬────┘  └─────────────┘
       │               │             │            │
       └───────────────┴─────────────┴────────────┘
                       │
                       ▼
              ┌───────────────────┐
              │      State        │
              │    (core/)        │
              │                   │
              │  - load_session   │
              │  - load_all       │
              │  - save_session   │
              │  - next_id        │
              └─────────┬─────────┘
                        │
                        ▼
              ┌───────────────────┐
              │    Filesystem     │
              │                   │
              │  .scope/          │
              │  ├── next_id      │
              │  └── sessions/    │
              │      └── {id}/    │
              └───────────────────┘
```

## Data Models

```python
@dataclass
class Session:
    id: str              # "0", "0.1", "0.1.2"
    task: str            # "Refactor auth module"
    parent: str          # "" for root, "0" for child of 0
    state: str           # "pending" | "running" | "done" | "aborted"
    activity: str        # "editing src/auth.ts"
    tmux_session: str    # "scope-0"
    created_at: datetime

@dataclass
class TreeNode:
    session: Session
    children: list[TreeNode]
    expanded: bool
    depth: int
```

## Filesystem Schema

```
.scope/
├── next_id                 # Counter: "3"
└── sessions/
    ├── 0/
    │   ├── task            # "Refactor auth to use JWT"
    │   ├── parent          # "" (empty = top-level)
    │   ├── state           # running | done | aborted
    │   ├── activity        # "waiting on children"
    │   ├── result          # Final output (freeform)
    │   ├── contract.md     # Injected prompt
    │   └── tmux            # "scope-0"
    ├── 0.0/
    │   ├── task            # "Extract JWT helpers"
    │   ├── parent          # "0"
    │   └── ...
    └── 0.1/
        ├── parent          # "0"
        └── ...
```

## CLI Interface

```
scope
├── spawn <task> [--input PATH]     → session ID (e.g., "0")
├── poll <id>                       → JSON {status, activity, result}
├── wait <id>... [--timeout N]      → JSON {results: [...]}
├── top                             → Launch TUI
├── setup                           → Install hooks + check tmux
└── abort <id>                      → Kill session and descendants
```

**Environment:**
- `SCOPE_SESSION_ID` — Set inside spawned sessions, determines parent

**Exit codes:**
- `0`: Success
- `1`: Error (session not found, tmux failed, etc.)

## tmux Module

| Function | Command |
|----------|---------|
| `create_session(name, cwd, cmd, env)` | `tmux new-session -d -s {name} -c {cwd} "ENV=val {cmd}"` |
| `split_window(name)` | `tmux split-window -h -t {name}` |
| `attach(name)` | `tmux attach -t {name}` |
| `kill_session(name)` | `tmux kill-session -t {name}` |
| `has_session(name)` | `tmux has-session -t {name}` |
| `list_sessions()` | `tmux list-sessions -F "#{session_name}"` |

## State Module

| Function | Input | Output | Side Effects |
|----------|-------|--------|--------------|
| `find_scope_dir()` | — | `Path \| None` | — |
| `ensure_scope_dir()` | — | `Path` | Creates `.scope/` |
| `next_id(parent)` | `str` | `str` | Increments counter |
| `load_session(id)` | `str` | `Session \| None` | — |
| `load_all()` | — | `list[Session]` | — |
| `save_session(session)` | `Session` | — | Writes files |
| `update_state(id, state)` | `str, str` | — | Writes state file |

## Hooks System

### Configuration

Written to `~/.claude/settings.json` by `scope setup`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "scope-hook activity"
      }]
    }],
    "Stop": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "scope-hook stop"
      }]
    }],
    "UserPromptSubmit": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "scope-hook task"
      }]
    }]
  }
}
```

### Hook Handler Logic

```
scope-hook <event>

Input: JSON via stdin (from Claude Code)
Environment: SCOPE_SESSION_ID

Logic:
1. If SCOPE_SESSION_ID unset → exit 0
2. Find .scope/sessions/$SCOPE_SESSION_ID/
3. If not found → exit 0
4. Parse stdin JSON
5. Handle event:
   - activity: extract tool name/file → write to activity file
   - stop: write "done" to state file
   - task: extract first user message → summarize → write to task file
```

### Activity Inference

| Tool | Activity |
|------|----------|
| `Read` | `reading {file_path}` |
| `Edit`, `Write` | `editing {file_path}` |
| `Bash` | `running: {command[:40]}` |
| `Grep` | `searching: {pattern}` |
| `Task` | `spawning subtask` |
| Other | `{tool_name}` |

## TUI Structure

```
ScopeApp(App)
├── BINDINGS
│   ├── n      → new_session
│   ├── enter  → attach
│   ├── x      → abort
│   ├── d      → toggle_done
│   ├── j/down → cursor_down
│   ├── k/up   → cursor_up
│   ├── h/left → collapse
│   ├── l/right→ expand
│   └── q      → quit
│
├── compose()
│   └── Vertical
│       ├── Header (title + running count)
│       ├── SessionTree (main content)
│       └── Footer (keybind hints)
│
└── Watcher
    └── watchfiles monitors .scope/sessions/ → instant refresh on change
```

### TUI Layout

```
┌─ scope ────────────────────────────────────────────────── 3 running ─┐
│                                                                      │
│  ▼ 0   Refactor auth to JWT        ● running   waiting on children   │
│    ├ 0.0  Extract JWT helpers      ● running   editing token.ts      │
│    └ 0.1  Update middleware        ✓ done      ─                     │
│  ▶ 1   Write tests for user module ● running   jest --watch          │
│    2   Fix database connection     ✓ done      ─                     │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  n new   ↵ attach   x abort   d hide done   q quit                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Key Flows

### 1. User starts scope

```
$ scope top
  → App.compose() builds UI
  → load_all() reads .scope/sessions/
  → build_tree() creates hierarchy
  → render tree widget
  → start watchfiles watcher on .scope/sessions/
```

### 2. User creates session (n)

```
  → Prompt for task (or skip, infer from first message)
  → spawn(task) called
    → next_id("") → "3"
    → save_session(...)
    → generate_contract(...)
    → tmux.create_session("scope-3", cwd, "SCOPE_SESSION_ID=3 claude ...")
    → tmux.split_window() to show session
  → refresh_sessions()
  → select new session
```

### 3. Claude Code spawns subagent

```
$ scope spawn "Extract JWT helpers"
  → Read SCOPE_SESSION_ID from env → "0"
  → next_id("0") → "0.0"
  → save_session(id="0.0", parent="0", ...)
  → generate_contract(...)
  → tmux.create_session("scope-0.0", ...)
  → print "0.0" to stdout
```

### 4. Hook updates activity

```
Claude Code calls Read tool
  → PostToolUse hook fires
  → scope-hook activity receives JSON
  → Extracts file_path
  → Writes "reading src/auth.ts" to .scope/sessions/0/activity
```

### 5. Session completes

```
Claude Code exits
  → Stop hook fires
  → scope-hook stop
  → Writes "done" to .scope/sessions/0/state
  → Clears activity file
```

### 6. User attaches to session (enter)

```
  → Get selected session ID
  → tmux.split_window() with attach to that session
  → User interacts in new pane
  → Close pane to detach (session keeps running)
```

## Error Handling

| Error | Response |
|-------|----------|
| tmux not installed | `scope setup` prompts to install |
| Session not found | Exit 1 with message |
| .scope/ not found | Create on first spawn, or error on poll/wait |
| Hook fails | Silent (don't break Claude Code) |
| tmux session died | State shows "running" but attach fails → detect and mark aborted |

## Testing Strategy

| Layer | Approach |
|-------|----------|
| State | Unit tests with temp directories |
| tmux | Integration tests (require tmux) |
| Hooks | Unit tests with mock stdin |
| TUI | Textual's built-in testing (pilot) |
| CLI | Click's CliRunner |
