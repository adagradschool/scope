# The Philosophy of Scope

**`scope` - Spawn bounded, purpose-specific subagents. Preserve your context. Maintain visibility and control.**

## The Problem Space

**Claude Code is bottlenecked by context, not capability.**

The underlying models are extraordinarily powerful, and the harness—tooling, file access, shell execution—is robust. But the real constraint is the finite context window, and more importantly, how developers manage information flow through it.

The community response has been ad hoc: Markdown files as external memory, manual summarization, copy-pasting state between sessions. These are symptoms of a missing abstraction.

## The Subagent Paradigm

Subagents represent the correct architectural response to this constraint. They are:

- **Scoped**: Finite context, bounded task
- **Purpose-specific**: One job, clear success criteria
- **Ephemeral**: Spawn, execute, return, terminate

The key insight is framing subagents as **function calls, not autonomous entities**. A subagent is:

```
f(inputs) → outputs
```

The internal reasoning is an implementation detail. You care about the contract: what goes in, what comes out.

## The Gap

Current subagent implementations violate this abstraction by being **opaque** and **non-interactive**. When a subagent drifts—and on long trajectories, it will—you have no mechanism to:

- Observe what it's doing in real-time
- Intervene to correct course
- Inspect the intermediate state

We want subagents that behave like function calls but remain **tangible**—debuggable, interruptible, steerable.

## Core Values

These principles guide every design decision in scope:

### 1. Transparency Over Magic

You should always know what's happening. No black boxes. The subagent's state is your state.

### 2. Control Over Autonomy

The agent works for you, not instead of you. Intervention is a first-class feature, not an escape hatch.

### 3. Contracts Over Conversations

Inputs and outputs are explicit. The subagent has a job spec, not vibes.

### 4. Minimalism Over Ceremony

One command to spawn. One interface to observe. Zero configuration to start.

## The Key Insight

**Claude Code's native Task tool is opaque by design.** It optimizes for context preservation by hiding details.

**Scope is transparent by design.** It optimizes for operator visibility and intervention.

Same underlying capability (spawning Claude Code sessions), different philosophy.

## What is Scope?

Scope is an **agent management system for Claude Code**.

Each subagent is not a degraded or simplified agent—it's a full Claude Code session with:

- **Pre-injected context** (the input contract)
- **A termination condition** (the output contract)
- **Awareness that it's scoped** (it knows to finish and return, not wander)

You, the operator, see all sessions in a multiplexed view. You can attach to any session, interact with it directly, then detach. The subagent continues whether you're watching or not.

## The Name

"Scope" evokes multiple meanings developers understand:

- **Oscilloscope, telescope**: You're looking into the subagent (visibility)
- **Scope as in boundary**: Finite, bounded context
- **Scope as in visibility range**: You can see into it

Short, one syllable, CLI-friendly.

## Nesting

Subagents can spawn children. Each child is a full scope with its own contract.

```
0           ← top-level
├ 0.0       ← child of 0
│ └ 0.0.0   ← grandchild
└ 0.1       ← child of 0
1           ← top-level (sibling to 0)
```

Rules:

- A scope completes only when all its children complete
- Aborting a parent aborts all descendants
- Each scope can be attached independently

The lineage is implicit via environment variables. When a scope spawns a child, the parent ID is inherited.

## Reliability Through Hooks

We don't rely on the model to self-report its activity. That's fragile.

Instead, scope uses Claude Code's hooks system:

- **PostToolUse**: After every tool call, we capture what the agent is doing
- **Stop**: When the session ends, we mark it complete

The model only has one job: write its result when done. Everything else is observed automatically.

## Two Interfaces

Scope has exactly two interfaces:

**For Claude Code (programmatic):**
```bash
scope spawn "task description" --input X --output Y  # → session ID
scope poll <id>                                       # → status, activity, result
scope wait <id> [<id2> ...]                          # → blocks until complete
```

**For the human operator (interactive):**
```bash
scope  # Opens the control panel
```

## The Filesystem is the IPC Layer

All state lives in `.scope/sessions/`:

```
.scope/
├── next_id
└── sessions/
    └── 0/
        ├── task          # One-line description
        ├── contract.md   # Injected prompt
        ├── parent        # Parent session ID (empty for root)
        ├── state         # running | done | aborted
        ├── activity      # Current action (live-updated by hooks)
        └── result        # Final output
```

Everything is inspectable with `cat`, `tail`, `watch`, `grep`. The entire Unix toolkit works.

## Summary

Scope exists because:

1. Context management is the bottleneck, not capability
2. Subagents should be function calls with contracts, not autonomous entities
3. Opacity breeds distrust; transparency enables intervention
4. The filesystem is a better IPC layer than sockets for this use case
5. Two interfaces (programmatic + TUI) cover all needs without complexity
