# D6: Verifier NLU — Rubric-Driven Verification

## The Change

`--checker` is always rubric-driven internally. The rubric is the universal verification model. Existing shorthand (`"pytest tests/"`, `"agent: ..."`) is preserved as sugar that gets converted to a rubric.

## UX Design

### 1. `--checker` — Always a Rubric

```bash
# Rubric file (primary path)
scope spawn "Implement search" --checker rubric.md

# Shell command sugar → internally becomes rubric with just ## Gates
scope spawn "Fix bug" --checker "pytest tests/"

# Agent prompt sugar → internally becomes rubric with just ## Criteria
scope spawn "Fix bug" --checker "agent: Review for correctness"
```

**Internal conversion:**

`--checker "pytest tests/"` becomes:
```markdown
## Gates
- `pytest tests/`
```

`--checker "agent: Review for correctness"` becomes:
```markdown
## Criteria
- Review for correctness
```

Everything flows through the same rubric evaluation pipeline.

### 2. Rubric Format

```markdown
# Search Feature

## Gates
- `pytest tests/test_search.py`
- `ruff check src/search/`

## Criteria
- Search results are relevant to query intent, not just keyword matching
- Empty queries, special characters, and very long queries handled gracefully
- Error states show user-friendly messages, not stack traces

## Nice to Have
- Performance: search returns within 200ms for typical queries
- Code follows existing naming conventions in the module

## Notes
Context for the checker agent (not scored).
The search uses Elasticsearch. Focus on the API layer.
```

- **Gates**: Shell commands. Deterministic pass/fail.
- **Criteria**: Natural language must-haves. Any failure → RETRY.
- **Nice to Have**: Advisory. Noted in feedback, don't block ACCEPT.
- **Notes**: Background context for the checker agent.

All sections are optional. A rubric with only `## Gates` behaves like today's shell checker. A rubric with only `## Criteria` behaves like today's agent checker. The power is in combining them.

### 3. Composite Verification

Every iteration runs the full rubric:

```
1. Run all gates (shell commands)
2. Run NLU checker (agent evaluates criteria + nice-to-haves)
   — agent receives gate results as context
3. Composite verdict:
   — Any gate FAIL or any must-have criterion FAIL → RETRY
   — All gates PASS + all must-have PASS → ACCEPT
   — Nice-to-have failures → noted, don't block ACCEPT
```

When there are no `## Criteria` or `## Nice to Have` sections (gates-only rubric), skip the agent checker — just run gates. When there are no `## Gates` (criteria-only rubric), skip gates — just run the agent checker. When both exist, run both compositely.

The agent checker sees gate results in its contract for holistic reasoning.

### 4. Mid-Loop Rubric Editing

Rubric file is read fresh each iteration. Edit, save, next iteration uses it. No pause.

**TUI**: Press `r` on a loop session → opens rubric in `$EDITOR`.
**CLI**: `scope rubric <session-id>` → opens rubric in `$EDITOR`.

For sugar-created rubrics (from inline `--checker` strings), the synthetic rubric is saved to `sessions/{id}/rubric.md` at spawn time, making it editable mid-loop just like file-based rubrics. This means even a simple `--checker "pytest tests/"` spawn can have criteria added mid-loop by editing the generated rubric.

### 5. TUI Display

Collapsed:

```
v 0   Implement search          running   loop    iter 2/3
    Iter 0                      done      do
    check                       done      check   2/3 must  1/2 nice  gates:1/2
    Iter 1                      done      do
    check                       done      check   3/3 must  2/2 nice  gates:2/2
    Iter 2                      running   do
```

Expanded (Space):

```
    check                       done      check   2/3 must  1/2 nice  gates:1/2
        gates:
          pytest tests/                           FAIL
          ruff check                              PASS
        must-have:
          1. relevance                            PASS
          2. edge cases                           FAIL - no empty query handling
          3. error messages                       PASS
        nice-to-have:
          1. performance                          PASS
          2. naming conventions                   FAIL - inconsistent
```

Per-criterion counts parsed best-effort from agent response. Falls back to just the verdict if parsing fails.

For gates-only rubrics, display simplifies to just gate results. For criteria-only, just criteria.

### 6. Checker Contract (Rubric Mode)

When criteria exist, the agent checker receives:

```markdown
# Role
You are a checker. Evaluate the doer's output against each criterion.

# Gate Results
- `pytest tests/test_search.py` — FAIL
- `ruff check src/search/` — PASS

## Gate Output
[test output here]

# Must-Have Criteria
For each, state PASS or FAIL with a brief explanation.

1. Search results are relevant to query intent, not just keyword matching
2. Empty queries, special characters, and very long queries handled gracefully
3. Error states show user-friendly messages, not stack traces

# Nice-to-Have Criteria
Evaluate each. These don't block acceptance but should be noted.

1. Performance: search returns within 200ms for typical queries
2. Code follows existing naming conventions in the module

# Notes
The search uses Elasticsearch. Focus on the API layer.

# Doer Output
[summarized result]

# Iteration
This is iteration 1.

# Prior Iterations
- Iteration 0: **RETRY** — gate pytest failed, criterion 2 failed

# Verdict
ACCEPT — all gates pass AND all must-have criteria pass
RETRY — any gate or must-have fails (provide specific feedback)
TERMINATE — fundamentally broken
```

### 7. State Persistence

```json
{
  "rubric_path": "/abs/path/to/rubric.md",
  "max_iterations": 3,
  "history": [
    {
      "iteration": 0,
      "doer_session": "0",
      "gates": [
        {"command": "pytest tests/", "verdict": "pass"},
        {"command": "ruff check", "verdict": "fail", "output": "..."}
      ],
      "criteria_summary": "2/3 must  1/2 nice",
      "verdict": "retry",
      "feedback": "...",
      "rubric_hash": "a1b2c3"
    }
  ]
}
```

- Rubric always materialized to `sessions/{id}/rubric.md` (even for sugar inputs).
- Content hash per iteration tracks mid-loop edits.
- `rubric_path` points to the session-local copy.

## Files to Modify

| File | Change |
|------|--------|
| `src/scope/core/loop.py` | Rubric parsing, composite verification, hot-reload, sugar→rubric conversion |
| `src/scope/core/contract.py` | Rubric-aware checker contract with gate results + must/nice sections |
| `src/scope/commands/spawn.py` | Checker value detection (file vs sugar), rubric materialization |
| `src/scope/tui/widgets/session_tree.py` | Per-criterion summary, expandable detail rows |
| `src/scope/tui/app.py` | `r` keybinding for rubric editing |
| `src/scope/core/state.py` | Rubric path + hash + structured gate results in loop state |
