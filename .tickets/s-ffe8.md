---
id: s-ffe8
status: open
deps: []
links: []
created: 2026-01-29T19:18:49Z
type: feature
priority: 2
tags: [ecosystem]
---
# Agent Backends

scope spawn --agent codex 'task' — support non-Claude-Code agents. Abstract the tmux session creation in spawn.py to support different CLI invocations. Strategic insurance: if Scope works with any agent CLI, it becomes the universal substrate regardless of what any vendor ships. Also enables cost optimization (cheap model for exploration, expensive for implementation).

## Acceptance Criteria

- scope spawn --agent <backend> 'task' spawns a session using a non-Claude agent CLI
- At least two backends supported: claude (default) and one other (codex, aider, or gemini-cli)
- Backend abstraction in spawn.py: command construction is configurable per backend
- tmux session management works identically regardless of backend
- Existing hooks (context-gate, stop, etc.) work with non-Claude backends where applicable
- Session metadata records which backend was used

