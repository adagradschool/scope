---
id: s-2bfe
status: open
deps: []
links: []
created: 2026-01-29T19:16:35Z
type: feature
priority: 1
tags: [feedback-loops, primitive-1]
---
# F1: Feedback Signal Quality

Give the orchestrator concrete, actionable signals about sub-agent output by running real verification tools (linting, unit tests, integration tests, e2e tests, type checking) against the working tree after each sub-agent completes. Results are injected into the orchestrator's context. Rubric and verification criteria are defined upfront in the contract or skill.

## Acceptance Criteria

- After a sub-agent completes, Scope automatically runs verification commands and injects results into the orchestrator's context
- Verification output includes: test pass/fail counts, lint warnings, type check status
- Orchestrator receives structured feedback like 'tests 47/50 passing, lint clean, types clean' rather than just 'session finished'
- Verification criteria are defined in the contract or skill, not a static config file
- Orchestrator can act on signals: retry, spawn fix session, or accept and move on

