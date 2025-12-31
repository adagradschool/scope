# scope

[![PyPI](https://img.shields.io/pypi/v/scopeai.svg)](https://pypi.org/project/scopeai/)
[![Python](https://img.shields.io/pypi/pyversions/scopeai.svg)](https://pypi.org/project/scopeai/)
[![License](https://img.shields.io/github/license/adagradschool/scope.svg)](https://github.com/adagradschool/scope/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/adagradschool/scope/ci.yml?branch=main)](https://github.com/adagradschool/scope/actions)

**Your context is rotting. Scope fixes that.**

Every task you give Claude Code accumulates context: file contents, failed attempts, exploratory tangents. When compaction kicks in, critical details vanish. Your main session becomes a diluted mess of half-remembered explorations.

**Scope solves this by spawning purpose-specific subagents.** Each subagent gets a fresh context, does one job, and returns only the relevant result. Your main session stays lean—you orchestrate and synthesize, not accumulate.

## The Problem

```
Main Session Context Over Time:

Start:    [████████████████████████████████████████] 100% relevant
After 3   [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 20% relevant
  tasks:  ↑ file reads, dead ends, tangents, old completions

After     [██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 5% relevant
compaction: ↑ critical details lost in summarization
```

This is **context rot**. The more you do in one session, the worse your context-to-relevance ratio becomes. Summarization doesn't help—it discards the wrong things.

## The Solution

```
With Scope:

Main:     [████████████████████████████████████████] orchestration + results only
          ↓ spawn
Subagent: [████████████████░░░░░░░░░░░░░░░░░░░░░░░░] does one job, returns summary
          ↑ fresh context, focused task, clean result
```

Each subagent:
- Starts with **fresh context** (no accumulated baggage)
- Has a **single purpose** (no scope creep)
- Returns **only what matters** (you get the result, not the journey)

Your main session becomes a coordinator, not a garbage collector.

## Quick Start

```bash
# Install
uv tool install scopeai

# Or run directly without installing
uvx scopeai

# Run setup (installs hooks, checks dependencies)
scope setup

# Launch the dashboard
scope
```

That's it. Now from any Claude Code session:

```bash
# Spawn a subagent
id=$(scope spawn "implement user authentication")

# Wait for result
scope wait $id
```

## Scope vs Task Tool

| | Task Tool | Scope |
|---|---|---|
| **Visibility** | Opaque black box | Real-time dashboard |
| **Intervention** | None—wait and hope | Attach, steer, abort anytime |
| **Context** | Shares parent context | Fresh context per agent |
| **Parallelism** | Sequential only | Spawn many in parallel |
| **Nesting** | Limited | Unlimited hierarchy |
| **Debugging** | Results only | Full session inspection |

The Task tool is a blind subprocess. Scope gives you a **visible, controllable swarm**.

## Usage

### For Humans: `scope`

```bash
scope
```

```
┌─ scope ────────────────────────────────────────────────── 3 running ─┐
│                                                                      │
│  ▼ 0   Refactor auth to JWT        ● running   waiting on children   │
│    ├ 0.0  Extract JWT helpers      ● running   editing token.ts      │
│    └ 0.1  Update middleware        ✓ done      ─                     │
│  ▶ 1   Write tests for user module ● running   jest --watch          │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  n new   ↵ attach   x abort   d hide done                            │
└──────────────────────────────────────────────────────────────────────┘
```

| Key | Action |
|-----|--------|
| `n` | New session (opens Claude Code in split pane) |
| `enter` | Attach to selected session |
| `x` | Abort selected (and descendants) |
| `j/k` | Navigate |
| `h/l` | Collapse/expand |
| `d` | Toggle completed sessions |

### For Claude Code: Programmatic Interface

```bash
# Spawn a subagent
id=$(scope spawn "Write tests for auth module" --input src/auth/)
# Returns: 0

# Check status (non-blocking)
scope poll $id
# Returns: {"status": "running", "activity": "editing test_auth.py"}

# Wait for completion (blocking)
scope wait $id
# Returns: {"status": "done", "result": "..."}
```

### DAG Orchestration

Model complex tasks as a dependency graph:

```bash
# Declare the full DAG upfront
scope spawn "research auth patterns" --id research
scope spawn "audit current codebase" --id audit
scope spawn "implement auth" --id impl --after research,audit
scope spawn "write tests" --id tests --after impl
scope spawn "update docs" --id docs --after impl

# Wait only on leaf nodes—dependencies auto-resolve
scope wait tests docs
```

### Nesting

Subagents can spawn children. Nesting is automatic via `SCOPE_SESSION_ID`:

```bash
# Inside session 0, this creates 0.0
scope spawn "Extract JWT helpers"

# Inside session 0.0, this creates 0.0.0
scope spawn "Parse token format"
```

## Why Parallelism is a Bonus

Yes, scope lets you run tasks in parallel. But that's not why you should use it.

You should use scope because **single-session context management is fundamentally broken**. Even if you only ever run one subagent at a time, you win:

- Fresh context for each task
- Clean results without journey baggage
- Main session stays lean and relevant
- No more losing critical details to compaction

Parallelism just means you can do this faster.

## How It Works

- Each session is a real Claude Code process in tmux
- State lives in `.scope/sessions/` (inspectable with standard Unix tools)
- Hooks track activity automatically (no model self-reporting)
- `scope` watches for changes and updates instantly

See [docs/02-architecture.md](docs/02-architecture.md) for technical details.

## Philosophy

1. **Transparency over magic** — No black boxes. The subagent's state is your state.
2. **Control over autonomy** — Intervention is a first-class feature.
3. **Contracts over conversations** — Inputs and outputs are explicit.
4. **Minimalism over ceremony** — One command to spawn, one interface to observe.

See [docs/00-philosophy.md](docs/00-philosophy.md) for the full design philosophy.

## Requirements

- Python 3.10+
- tmux
- Claude Code

## License

MIT
