---
id: s-b41d
status: open
deps: []
links: []
created: 2026-01-29T19:17:57Z
type: feature
priority: 2
tags: [dag-orchestration, primitive-2]
---
# D4: Conditional Branching

Spawn sessions conditionally based on prior session outcomes. scope spawn --on-fail <id> and --on-pass <id>. The orchestrator reads the prior result and decides success/failure — intelligence in the loop, not a structured schema. Enables DAGs with error recovery and fast paths.

## Acceptance Criteria

- scope spawn --on-fail <id> 'fix task' only runs if the referenced session failed
- scope spawn --on-pass <id> 'next task' only runs if the referenced session passed
- Pass/fail determination is made by the orchestrator agent reading the result (not a structured field)
- Conditional sessions that don't trigger are marked as skipped, not failed
- Composes with --pipe (conditional + result injection)
- Enables retry patterns: --on-fail combined with re-spawning the same task

