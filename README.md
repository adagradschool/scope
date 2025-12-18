# scope

**Spawn bounded, purpose-specific subagents. Preserve your context. Maintain visibility and control.**

scope is an agent management system for Claude Code. It lets you spawn subagents that are observable, interruptible, and steerable—without polluting your main context.

## Installation

```bash
# One-shot run (no install)
uvx scope top

# Or install globally
uv tool install scope
```

Then run setup:

```bash
scope setup
```

This checks for `tmux`, installs Claude Code hooks, and configures documentation.

## Usage

### For Humans: `scope top`

```bash
scope top
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
│  n new   ↵ attach   x abort   d hide done   q quit                   │
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
| `q` | Quit (sessions keep running) |

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

Subagents can spawn children. Nesting is automatic via `SCOPE_SESSION_ID`:

```bash
# Inside session 0, this creates 0.0
scope spawn "Extract JWT helpers"

# Inside session 0.0, this creates 0.0.0
scope spawn "Parse token format"
```

## Why scope?

Claude Code is bottlenecked by context, not capability. Subagents help—but current implementations are opaque. When they drift, you can't see or intervene.

scope makes subagents **transparent**:
- See what every session is doing in real-time
- Attach to any session and interact directly
- Abort runaway tasks before they waste tokens

## Philosophy

1. **Transparency over magic** — No black boxes. The subagent's state is your state.
2. **Control over autonomy** — Intervention is a first-class feature.
3. **Contracts over conversations** — Inputs and outputs are explicit.
4. **Minimalism over ceremony** — One command to spawn, one interface to observe.

See [docs/00-philosophy.md](docs/00-philosophy.md) for the full design philosophy.

## How It Works

- Each session is a real Claude Code process
- State lives in `.scope/sessions/` (inspectable with standard Unix tools)
- Hooks track activity automatically (no model self-reporting)
- `scope top` watches for changes and updates instantly

See [docs/02-architecture.md](docs/02-architecture.md) for technical details.

## Requirements

- Python 3.10+
- tmux
- Claude Code

## License

MIT
