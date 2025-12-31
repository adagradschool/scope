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
│     scope spawn    scope poll    scope wait    scope    scope setup         │
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
├── setup                           → Install hooks + check tmux
└── abort <id>                      → Kill session and descendants

scope                               → Launch TUI
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
$ scope
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

---

## Addendum: Contracts & Task Types

This section describes proposed extensions for task typing and agent selection.

### Task Type System

New field on Session: `task_type`

| Type | Purpose | Expected Output |
|------|---------|-----------------|
| `explore` | Navigate/understand codebase | Insights, file locations, patterns found |
| `implement` | Write/modify code | Files changed, summary of approach |
| `test` | Run/validate | Pass/fail, failure details |
| `review` | Analyze/reason about code | Assessment, concerns, suggestions |
| `refactor` | Transform preserving behavior | Files changed, what was preserved |

Default: `implement` (most common case).

### Agent Selection

New field on Session: `agent`

| Agent | Description |
|-------|-------------|
| `claude-code` | Default. Full Claude Code session. |
| `codex` | OpenAI Codex CLI. Fast, good at execution. |
| `aider` | Aider tool. |
| *(extensible)* | New agents can be added. |

Agent selection can be:
- **Explicit**: `--agent codex`
- **Type-based**: Route by task type (e.g., `test` → codex)
- **Cost-aware**: Use cheaper models for exploration

### Updated Spawn Interface

```bash
scope spawn "task" --type explore --agent codex --input src/auth/
```

| Flag | Purpose |
|------|---------|
| `--type` | Task type (explore, implement, test, review, refactor) |
| `--agent` | Agent to use (claude-code, codex, aider) |
| `--input` | Path(s) to pass as context |

### Updated Data Model

```python
@dataclass
class Session:
    id: str
    task: str
    task_type: str       # NEW: explore | implement | test | review | refactor
    agent: str           # NEW: claude-code | codex | aider
    parent: str
    state: str
    tmux_session: str
    created_at: datetime
```

### Updated Filesystem Schema

```
.scope/sessions/0/
├── task            # One-line description
├── task_type       # NEW: explore | implement | test | review | refactor
├── agent           # NEW: claude-code | codex | aider
├── parent
├── state
├── activity
├── result
├── contract.md
└── tmux
```

### Contract Generation by Task Type

The child's contract (system prompt) is shaped by `task_type`:

**explore:**
```markdown
## Task Type: Explore
Your goal is to understand, not modify. Return:
- Key insights about the code structure
- Relevant file paths
- Patterns or conventions observed
Do NOT make changes. Focus on what the caller needs to know.
```

**implement:**
```markdown
## Task Type: Implement
Write or modify code to accomplish the task. Return:
- Files changed (list)
- Brief summary of approach
- Any assumptions made
```

**test:**
```markdown
## Task Type: Test
Run and validate. Return:
- Pass/fail status
- Failure details (if any)
- Coverage or confidence notes
```

**review:**
```markdown
## Task Type: Review
Analyze the code. Return:
- Assessment (good/concerning/needs work)
- Specific concerns or issues
- Suggestions for improvement
Do NOT make changes unless explicitly asked.
```

**refactor:**
```markdown
## Task Type: Refactor
Transform the code while preserving behavior. Return:
- Files changed
- What was preserved (behavior guarantees)
- What was improved (structure, clarity, performance)
```

### Parent Decision Heuristics

When should a parent spawn a subagent? Add to CLAUDE.md:

```markdown
## When to Spawn a Subagent

Spawn when:
- Task would consume significant context (>30% of window)
- Task is parallelizable with other work
- Task has clear inputs/outputs you can specify
- Task is self-contained (doesn't need your running state)

Don't spawn when:
- Quick lookup or small edit (just do it)
- Task requires back-and-forth dialogue
- You need to see intermediate steps
- Task is tightly coupled to your current work

Remember: spawning preserves YOUR context. The subagent pays the context cost, you get back a concise result.
```

### Design Decisions

**What we're adding:**
- `task_type` — Shapes contract, helps routing, visible in TUI
- `agent` — Enables Claude/Codex/Aider switching

**What we're NOT adding:**

| Feature | Why Not |
|---------|---------|
| `depends_on` (sibling deps) | Parent already handles sequencing via wait/poll. Adding deps makes Scope an orchestrator, conflicting with "visibility layer" philosophy. |
| Auto-orchestration | Scope shows state, doesn't manage execution order. Parent is the orchestrator. |
| Atomizer pattern | No explicit "should I decompose?" LLM call. Parent decides based on heuristics in CLAUDE.md. |
| Aggregator pattern | No auto-synthesis of results. Parent reads results and synthesizes manually. |
| Context auto-propagation | No auto-populating child context from deps. Parent explicitly passes `--input`. |

**Rationale:** Keep Scope simple. Intelligence stays in the prompts, not the orchestration layer.

---

## Addendum: UX Redesign - Native tmux Experience

### Goal

Make scope feel native. No tmux knowledge required.

### Current Problem

- Sessions are tmux **windows** in one shared session
- `select_window` switches away from scope, losing visibility
- User must know tmux commands to navigate back
- No split view (can't see scope + session simultaneously)

### New Architecture

**Each Claude Code session = its own tmux session**

```
tmux session "scope-0" (Claude Code for session 0)
tmux session "scope-1" (Claude Code for session 1)

User's terminal:
┌─────────────────┬─────────────────┐
│   scope         │  attached to    │
│   (TUI)         │  scope-0        │
└─────────────────┴─────────────────┘
```

### Key Behavior Changes

| Action | Current | New |
|--------|---------|-----|
| Entry point | `scope` (requires tmux) | `scope` (auto-launches tmux) |
| `n` (new) | Creates window, stays on scope | Splits right, opens Claude Code |
| `enter` (attach) | Switches window (leaves scope) | Splits right, attaches to session |
| Close split | N/A | Detaches, returns to scope |
| Session persistence | Window in shared session | Independent tmux session |

### Startup Logic

```python
def main():
    if not in_tmux():
        # Auto-launch tmux with scope inside
        os.execvp("tmux", ["tmux", "new-session", "-s", "scope-main", "scope", "--inside-tmux"])
    else:
        # Already in tmux, run the TUI
        run_tui()
```

### Updated tmux Module

```python
def create_session(name: str, command: str, cwd: Path, env: dict) -> None:
    """Create a new independent tmux session."""
    # tmux new-session -d -s scope-0 -c /path "SCOPE_SESSION_ID=0 claude"

def attach_in_split(session_name: str) -> None:
    """Open a split pane attached to an existing session."""
    # tmux split-window -h "tmux attach -t scope-0"

def has_session(name: str) -> bool:
    """Check if a tmux session exists."""

def in_tmux() -> bool:
    """Check if currently running inside tmux."""
```

### Updated Filesystem

```
.scope/sessions/0/
├── tmux_session    # "scope-0" (independent session, was "w0" window)
└── ...
```

### UX Flow

1. User runs `scope`
2. If not in tmux → auto-launches: `tmux new-session -s scope-main "scope --inside-tmux"`
3. TUI shows sessions list
4. Press `n`:
   - Creates independent session: `tmux new-session -d -s scope-0 ... claude`
   - Attaches in split: `tmux split-window -h "tmux attach -t scope-0"`
   - User sees: scope (left) | Claude Code (right)
5. Press `enter` on any session:
   - Opens split attached to that session
6. Close right pane (Ctrl-D):
   - Detaches from session (session keeps running in background)
   - Returns to scope TUI only
7. Press `q`:
   - Exits scope TUI
   - All sessions continue running independently

### Benefits

- **No tmux knowledge needed**: User just runs `scope`, everything else is automatic
- **Split view**: Always see scope + current session side by side
- **Session independence**: Closing splits doesn't kill sessions
- **Native feel**: Just `scope` to start, `q` to quit, close pane to detach
