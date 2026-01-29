---
id: s-aaca
status: open
deps: []
links: []
created: 2026-01-29T19:17:47Z
type: feature
priority: 2
tags: [dag-orchestration, primitive-2]
---
# D3: Richer Dependency Expressions

Extend dependency expressions beyond --after (wait for all). Add --after-any (wait for first), --gate N (wait for N of M), fan-out helpers (scope fan-out --task X --items a,b,c), and fan-in (scope fan-in --reduce X --sources a,b,c). Let the orchestrator think in workflow patterns rather than individual spawns.

## Acceptance Criteria

- scope spawn --after-any id1,id2 starts when the first dependency completes
- scope spawn --gate 2 id1,id2,id3 starts when any 2 of 3 complete
- scope fan-out --task 'test module' --items a,b,c spawns N parallel sessions
- scope fan-in --reduce 'merge results' --wait-for a,b,c spawns after all sources complete
- Fan-out/fan-in are convenience wrappers over spawn + after
- All expressions compose with --pipe and conditional flags

