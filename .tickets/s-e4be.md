---
id: s-e4be
status: open
deps: []
links: []
created: 2026-01-29T19:18:38Z
type: feature
priority: 2
tags: [context-management, primitive-3]
---
# C3: Orchestrator Context Protection

Keep the orchestrator's context lean by providing summarized views by default. Today the orchestrator reads full results from every sub-agent, accumulating context. Provide summary mode: 'session X succeeded, changed 3 files, tests pass' with drill-down on demand for full details.

## Acceptance Criteria

- scope wait --summary <id> returns a compact summary instead of full result
- Summary includes: pass/fail, files changed count, test status, key outcome
- Orchestrator can drill down with scope wait <id> (full) when judgment requires it
- poll already returns compact status (see C2)
- Orchestrator can coordinate 10+ sessions without context exhaustion
- Summary generation does not require an additional LLM call (extracted from result metadata)

