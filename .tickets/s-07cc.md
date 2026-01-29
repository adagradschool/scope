---
id: s-07cc
status: done
deps: []
links: []
created: 2026-01-29T19:18:16Z
type: feature
priority: 1
tags: [context-management, primitive-3]
---
# C1: Contract Enrichment

Extend contract.py to build richer contracts. Today contracts are minimal (dependency wait + task prompt). Enrich with: phase metadata ('you are in the RED phase'), parent intent ('orchestrator goal is X, your sub-goal is Y'), relevant prior results, scoped file context ('only modify files in src/auth/'). contract.py is 39 lines today.

## Acceptance Criteria

- Contracts include phase metadata when spawned as part of a phased workflow
- Contracts include parent intent / orchestrator goal context
- Contracts include relevant prior results from piped sessions
- Contracts can include file scope constraints ('only modify files in src/auth/')
- Contract generation is extensible — new context types can be added without rewriting the generator
- Sub-agents start with sufficient context to begin work immediately without re-discovery

