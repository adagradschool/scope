---
id: s-ac0b
status: done
deps: []
links: []
created: 2026-01-29T19:17:27Z
type: feature
priority: 1
tags: [dag-orchestration, primitive-2]
---
# D1: Result Piping

Add --pipe flag to scope spawn. The result of a completed session is automatically injected into the next session's contract. The child doesn't start until the parent is done. Cleaner than --after + scope wait because the child starts with the parent's result already in its contract — no wasted context on wait output parsing.

## Acceptance Criteria

- scope spawn --pipe <session_id> delays child start until parent completes
- Parent's result text is injected into the child's contract automatically
- Multiple pipes supported: --pipe id1,id2 combines both results into contract
- Child's contract clearly attributes piped content ('The previous session produced: ...')
- No scope wait needed — piping replaces the wait-based handoff for sequential chains
- Works with existing --after flag (--pipe is --after + result injection)

