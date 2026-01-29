---
id: s-6b3b
status: open
deps: [s-2bfe]
links: []
created: 2026-01-29T19:17:04Z
type: feature
priority: 1
tags: [feedback-loops, primitive-1]
---
# F4: Pattern Commitment

When an agent commits to a pattern (TDD, RALPH, map-reduce), Scope enforces it through contract re-injection — persistent reminding that prevents accidental drift while allowing deliberate deviation. Each agent loads the skill it wants; the parent can bias but doesn't choose. Scope registers the pattern and re-injects state after each sub-agent completes.

## Acceptance Criteria

- When an agent commits to a skill, Scope registers the pattern and its phases
- After each sub-agent completes, Scope re-injects pattern state into the agent's context ('Pattern: TDD. Completed: red. Next: green. Prior result: ...')
- Agent can deliberately deviate but must explicitly state why — drift is conscious, not accidental
- Parent agent can bias which skill a child should use but does not choose for it
- Pattern state survives context growth (solves the memory/attention drift problem)

