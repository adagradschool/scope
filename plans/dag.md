# Declarative DAG Orchestration

## Motivation

Currently, Claude must mentally track task dependencies and manually orchestrate execution:

```bash
# Claude has to think: "task 3 depends on 1 and 2, so I wait first"
id1=$(scope spawn "research auth patterns")
id2=$(scope spawn "audit current codebase")
scope wait $id1 $id2
id3=$(scope spawn "implement auth based on research and audit")
scope wait $id3
```

This has problems:
1. **Cognitive load** — Claude tracks DAG in its reasoning, burning context
2. **Arbitrary decisions** — No principled heuristics for when to spawn vs inline
3. **Manual orchestration** — Every dependency requires explicit `wait` calls
4. **Verbose results** — Child outputs pass through verbatim, no compression

Research into context management frameworks (ROMA, Beads, Dropstone, Honcho) reveals common patterns:
- **ROMA**: Explicit Planner module builds DAG, Aggregator compresses results
- **Beads**: First-class dependency tracking (`bd dep add X Y`)
- **Dropstone**: Logic-preserving compression (50:1 ratio)
- **Honcho**: Cached representations of accumulated knowledge

We can externalize DAG orchestration to Scope, letting Claude declare intent rather than manage execution.

---

## Proposed UX

### 1. Declarative Dependencies (`--after`)

```bash
# Declare the DAG, Scope handles orchestration
scope spawn "research auth patterns" --id research
scope spawn "audit current codebase" --id audit
scope spawn "implement auth" --id implement --after research,audit

# Single wait for the terminal node
scope wait implement
```

Scope automatically:
- Queues `implement` until `research` and `audit` complete
- Passes relevant results as context to dependent tasks
- Handles failure propagation (if `research` fails, `implement` never starts)

### 2. Auto-Aggregation (`--summarize`)

```bash
# Get compressed synthesis instead of raw concatenation
scope wait --summarize research audit implement

# Or per-spawn, compress before passing to dependents
scope spawn "implement auth" --after research,audit --summarize-inputs
```

Child results are compressed before parent sees them — like WebFetch's built-in summarization but for spawn results.

### 3. Atomicity Hints (future)

```bash
# Ask Scope whether to spawn or inline
scope estimate "implement user auth given codebase at ./src"
# → ~85k tokens expected, recommend: spawn

scope estimate "fix typo in README"
# → ~2k tokens expected, recommend: inline
```

---

## Data Model Changes

### Session State

```
~/.scope/repos/<repo>/sessions/<id>/
├── state          # pending | queued | running | done | failed | aborted
├── task           # original prompt
├── result         # final output
├── parent         # parent session id
├── depends_on     # NEW: comma-separated list of dependency IDs
├── alias          # NEW: optional human-readable name (--id flag)
└── ...
```

### New States

| State | Meaning |
|-------|---------|
| `pending` | Created, no dependencies, ready to run |
| `queued` | Has unmet dependencies, waiting |
| `running` | Executing in tmux |
| `done` | Completed successfully |
| `failed` | Exited with error |
| `aborted` | User aborted |

---

## Implementation Slices

### Slice D1: Alias support (`--id`)

**Goal:** `scope spawn "task" --id myname` allows referencing by name.

**Files:**
- `src/scope/core/session.py` — add `alias` field
- `src/scope/core/state.py` — lookup by alias or numeric ID
- `src/scope/commands/spawn.py` — `--id` flag

**Test:** `scope spawn "x" --id foo && scope poll foo` works.

---

### Slice D2: Dependency declaration (`--after`)

**Goal:** `scope spawn "task" --after dep1,dep2` declares dependencies.

**Files:**
- `src/scope/core/session.py` — add `depends_on` field
- `src/scope/commands/spawn.py` — `--after` flag, parse dependencies
- `src/scope/core/state.py` — write depends_on file

**Test:** Spawn with `--after`, verify depends_on file contains IDs.

---

### Slice D3: Queued state and dependency resolution

**Goal:** Sessions with unmet dependencies start in `queued` state, auto-start when ready.

**Files:**
- `src/scope/core/orchestrator.py` — NEW: watches for completed sessions, starts queued dependents
- `src/scope/commands/spawn.py` — set state=queued if has dependencies
- `src/scope/tui/app.py` — show queued state in UI

**Implementation:**
- Background watcher (or hook-triggered) checks: "did a session complete? are any queued sessions now unblocked?"
- Unblocked = all dependencies in `done` state
- On unblock: inject dependency results into contract, start session

**Test:**
```bash
scope spawn "task1" --id t1
scope spawn "task2" --after t1  # starts queued
# complete t1
# t2 auto-starts
```

---

### Slice D4: Dependency result injection

**Goal:** Dependent tasks receive results from their dependencies.

**Files:**
- `src/scope/core/contract.py` — inject dependency results into contract
- `src/scope/core/orchestrator.py` — gather results before starting dependent

**Contract format:**
```markdown
## Task
{original task}

## Context from Dependencies

### research (0.0)
{result from research session}

### audit (0.1)
{result from audit session}
```

**Test:** Spawn dependent, verify contract.md includes dependency results.

---

### Slice D5: Auto-aggregation (`--summarize`)

**Goal:** Compress results before injecting into dependents.

**Files:**
- `src/scope/core/summarizer.py` — NEW: LLM-based result compression
- `src/scope/commands/spawn.py` — `--summarize-inputs` flag
- `src/scope/commands/wait.py` — `--summarize` flag
- `src/scope/core/orchestrator.py` — summarize before injection if flag set

**Test:** Spawn with `--summarize-inputs`, verify contract has compressed (not verbatim) results.

---

### Slice D6: Failure propagation

**Goal:** If a dependency fails, dependent tasks fail without starting.

**Files:**
- `src/scope/core/orchestrator.py` — check for failed dependencies
- `src/scope/core/state.py` — add `failed_reason` field

**Behavior:**
- If any dependency is `failed` or `aborted`, mark dependent as `failed`
- Set `failed_reason` to "dependency X failed"
- Propagate transitively through DAG

**Test:** Spawn chain A → B → C, abort A, verify B and C marked failed.

---

### Slice D7: TUI DAG visualization

**Goal:** Show dependency relationships in TUI.

**Files:**
- `src/scope/tui/widgets/session_tree.py` — render dependencies
- `src/scope/tui/app.py` — show blocked-by indicator

**Display:**
```
0   research         done     2m ago
0.1 audit            done     1m ago
0.2 implement        running  [after: research, audit]
0.3 deploy           queued   [after: implement]
```

**Test:** Visual inspection of DAG in TUI.

---

## Summary

| Slice | Feature | Complexity |
|-------|---------|------------|
| D1 | `--id` alias | Low |
| D2 | `--after` declaration | Low |
| D3 | Queued state + auto-start | Medium |
| D4 | Result injection | Medium |
| D5 | Auto-aggregation | Medium |
| D6 | Failure propagation | Low |
| D7 | TUI visualization | Low |

**Recommended order:** D1 → D2 → D3 → D4 → D6 → D7 → D5

D5 (summarization) is optional but high-value. D1-D4 form the core DAG functionality.

---

## Open Questions

1. **Cycle detection** — Should Scope validate DAG has no cycles at spawn time? → **Yes**
2. **Partial failure** — If 2/3 dependencies complete, should dependent get partial context? → **No, wait for all**
3. **Dynamic dependencies** — Can a running session add dependencies mid-execution? → **Future**
4. **Summarization model** — Use same model as parent, or dedicated fast/cheap model? → **Future (D5)**

---

# Implementation Plan

## Architecture Decision

**Sessions self-manage their dependencies.** When spawned with `--after`, the session itself calls `scope wait` on its dependencies and uses the results. No external orchestrator needed.

This is simpler than a queued state + orchestrator approach:
- Session spawns immediately
- Contract tells session to run `scope wait dep1 dep2` first
- Session gets results from wait output and proceeds

## Scope: D1-D4, D6 (no D5/D7)

---

## Slice D1: Alias Support (`--id`)

**`src/scope/core/session.py`**
- Add `alias: str` field to Session dataclass (default empty string)
- Add "failed" to VALID_STATES

**`src/scope/core/state.py`**
- In `save_session()`: write `alias` file
- In `load_session()`: read `alias` file
- Add `resolve_id(id_or_alias: str) -> str | None`: look up by alias or numeric ID
- Add `load_session_by_alias(alias: str) -> Session | None`

**`src/scope/commands/spawn.py`**
- Add `--id` option
- Validate alias uniqueness at spawn time
- Save alias to session

**`src/scope/commands/poll.py`**
- Use `resolve_id()` to support alias lookup

**`src/scope/commands/wait.py`**
- Use `resolve_id()` to support alias lookup

**Tests:** `tests/test_spawn.py`, `tests/test_state.py`
- Test `--id foo` creates alias file
- Test `scope poll foo` works
- Test duplicate alias rejected

---

## Slice D2: Dependency Declaration (`--after`)

**`src/scope/core/session.py`**
- Add `depends_on: list[str]` field (default empty list)

**`src/scope/core/state.py`**
- In `save_session()`: write `depends_on` file (comma-separated IDs)
- In `load_session()`: read `depends_on` file
- Add `get_dependencies(session_id: str) -> list[str]`: resolve aliases to IDs

**`src/scope/commands/spawn.py`**
- Add `--after` option (comma-separated list)
- Resolve aliases to IDs before saving
- Validate all dependencies exist

**`src/scope/core/dag.py`** (NEW)
- `detect_cycle(new_session_id: str, depends_on: list[str]) -> bool`
- Simple DFS cycle detection

**Tests:** `tests/test_dag.py` (NEW)
- Test `--after dep1,dep2` creates depends_on file
- Test cycle detection rejects `A --after B` when B depends on A

---

## Slice D3: Self-Managed Dependencies

Sessions with `--after` spawn immediately but the contract instructs them to wait first:

**`src/scope/core/contract.py`**
- Update signature: `generate_contract(prompt: str, depends_on: list[str] | None = None)`
- If depends_on provided, prepend wait instruction

**Contract format:**
```markdown
# Dependencies

Before starting, wait for your dependencies to complete:
\`\`\`bash
scope wait research audit
\`\`\`

Use the results from these sessions to inform your work.

# Task

{original task}
```

**`src/scope/commands/spawn.py`**
- Pass `depends_on` list to `generate_contract()`

**Tests:** `tests/test_contract.py`
- Test contract includes wait instruction when depends_on provided

---

## Slice D4: Enhanced Wait Output

**`src/scope/commands/wait.py`**
- Improve output format for multiple sessions
- Include session alias in output headers if available

**Output format:**
```
[research (0.0)]
{result from research}

[audit (0.1)]
{result from audit}
```

**Tests:** `tests/test_wait.py`
- Test multi-session wait includes clear headers

---

## Slice D6: Failure Handling

**`src/scope/commands/wait.py`**
- Add "failed" to TERMINAL_STATES
- Exit code 3 if any dependency failed (distinct from 2=aborted)
- Output failure reason if available

**`src/scope/core/state.py`**
- Add `save_failed_reason(session_id: str, reason: str)`
- Add `get_failed_reason(session_id: str) -> str | None`

**`src/scope/core/session.py`**
- Add "failed" to VALID_STATES

**Tests:** `tests/test_wait.py`
- Test wait returns exit code 3 when dependency failed

---

## File Summary

| File | Action |
|------|--------|
| `src/scope/core/session.py` | Modify: add alias, depends_on, "failed" state |
| `src/scope/core/state.py` | Modify: save/load new fields, resolve_id, failed_reason |
| `src/scope/core/contract.py` | Modify: add dependency wait instructions |
| `src/scope/core/dag.py` | Create: cycle detection |
| `src/scope/commands/spawn.py` | Modify: --id, --after flags |
| `src/scope/commands/wait.py` | Modify: resolve aliases, better multi-session output, failed state |
| `src/scope/commands/poll.py` | Modify: resolve aliases |
| `tests/test_dag.py` | Create: cycle detection tests |

---

## Implementation Order

1. **D1**: alias support (`--id` flag, resolve_id)
2. **D2**: `--after` declaration + cycle detection
3. **D3**: contract generates wait instructions for deps
4. **D4**: enhanced wait output with aliases
5. **D6**: failure handling in wait
