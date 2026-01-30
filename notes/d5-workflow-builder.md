# D5: Workflow Builder — Loops as Atoms

## Summary

Two ways to run loops:

1. **`scope spawn`** — single loop, stays as the public CLI command for one-off tasks
2. **`scope workflow`** — runs a Python file that sequences multiple loops programmatically

Remove `--after`/`--pipe` DAG primitives. The Workflow builder replaces them — it sequences phases explicitly in Python instead of declaring a dependency graph.

Any session inside a loop can call `scope exit "reason"` to halt the entire workflow with an explicit explanation. This is the course-correction primitive — clean, intentional, and the reason propagates back to the caller.

### Single loop (unchanged)

```bash
scope spawn "Write tests for auth" --checker "pytest tests/"
```

### Multi-phase workflow

```bash
scope workflow workflows/tdd.py
```

```python
# workflows/tdd.py
from scope import Workflow

wf = Workflow("tdd")
wf.phase("red", task="Write failing tests for src/auth", checker="pytest tests/")
wf.phase("green", task="Make tests pass", checker="pytest tests/", max_iterations=5)
wf.phase("refactor", task="Refactor for clarity", checker="agent: Review. ACCEPT/RETRY")
results = wf.run()

# If any phase called `scope exit`, results contain the reason
for name, r in results.items():
    if r.verdict == "exit":
        print(f"Workflow stopped at {name}: {r.exit_reason}")
```

## Steps

### 1. Extract loop engine into `src/scope/core/loop.py`

Move from `spawn.py` into a new public module:
- `run_loop()` — the doer-checker loop, now returns `LoopResult`
- `spawn_and_run()` — creates session + tmux window + sends contract + runs loop + returns `LoopResult`
- Helper functions: `wait_for_sessions`, `read_result`, `parse_verdict`, `spawn_session`, `send_contract`
- Constants: `TERMINAL_STATES`, `CONTRACT_CHUNK_SIZE`, `PENDING_TASK`

New dataclass:
```python
@dataclass
class LoopResult:
    session_id: str
    verdict: str        # "accept" | "terminate" | "max_iterations" | "exit"
    iterations: int
    history: list[dict]
    result_text: str
    exit_reason: str    # populated when verdict == "exit"
```

`spawn.py` keeps its public CLI interface but delegates the loop execution to `spawn_and_run()` from the loop module.

### 2. Add `scope exit` command: `src/scope/commands/exit.py`

```
scope exit "Auth module uses event-driven pattern, need to redesign"
```

- Sets session state to `"exited"`
- Persists the reason to `exit_reason` file in the session directory
- Session terminates cleanly

The loop engine detects the `"exited"` state after waiting:
- Reads the `exit_reason` file
- Returns `LoopResult(verdict="exit", exit_reason=reason)`

State changes:
- `state.py` gets `save_exit_reason(session_id, reason)` and `load_exit_reason(session_id)`

### 3. Remove `--after`, `--pipe`, and DAG code

**Delete:**
- `src/scope/core/dag.py`
- `tests/test_dag.py`
- `tests/test_pipe.py`

**Modify `spawn.py`:** Remove `--after`, `--pipe` options and all dependency resolution/cycle-detection/pipe-collection code. Keep `spawn` as a public command — it's the single-loop entry point.

**Modify `session.py`:** Remove `depends_on` field from `Session` dataclass.

**Modify `state.py`:** Remove `depends_on` read/write in `save_session()`/`load_session()`, remove `get_dependencies()`.

**Keep** `generate_contract()` parameters (`depends_on`, `prior_results`, `phase`, etc.) — the workflow builder uses them directly.

### 4. Create the Workflow builder: `src/scope/workflow.py`

Three classes:

- **`Phase`** — dataclass: name, task, checker, max_iterations, checker_model, model, on_fail, pipe_from (list of phase names), file_scope, verify. Has a `result: PhaseResult | None` populated after execution.

- **`PhaseResult`** — dataclass: phase_name, loop_result (LoopResult), passed (bool). Properties: `result_text`, `verdict`, `exit_reason`.

- **`Workflow`** — builder class:
  - `__init__(name)` — stores name
  - `phase(name, task, checker, ..., pipe=None, on_fail="stop")` — registers a phase, returns `Phase`
  - `run()` — executes all phases sequentially, returns `dict[str, PhaseResult]`

Execution model in `run()`:
1. Iterate phases in registration order
2. Collect prior results: explicit `pipe=` sources, or auto-pipe from immediately preceding phase
4. Call `spawn_and_run()` with task, checker, prior_results, phase name
5. Store result; check verdict:
   - `"exit"` — always stop, propagate reason
   - `"accept"` — continue to next phase
   - `"terminate"` or `"max_iterations"` — check `on_fail`: `"stop"` (default), `"continue"`, `"retry:N"`
6. Return all results

### 5. Add `scope workflow` CLI command: `src/scope/commands/workflow_cmd.py`

```
scope workflow workflows/tdd.py
```

- Takes a positional argument: path to a Python file
- Loads and executes the file via `importlib` (the file calls `wf.run()` itself)
- Prints results summary on completion

Register in `cli.py`: `main.add_command(workflow)`.

### 6. Update exports: `src/scope/__init__.py`

```python
from scope.workflow import Workflow, Phase, PhaseResult
```

### 7. Tests

**New:**
- `tests/test_workflow.py` — builder API (mock `spawn_and_run`): phase registration, auto-piping, explicit piping, on_fail strategies, exit propagation, run returns results
- `tests/test_workflow_cmd.py` — CLI: help output, missing file error
- `tests/test_loop.py` — extracted loop: parse_verdict tests (moved from test_spawn), LoopResult dataclass, read_result
- `tests/test_exit.py` — exit command: sets state, persists reason, loaded correctly

**Update:**
- `tests/test_spawn.py` — remove --after/--pipe/verdict tests
- `tests/test_contract.py` — keep as-is

**Delete:**
- `tests/test_dag.py`, `tests/test_pipe.py`

## Implementation Order

1. Extract loop engine (pure refactor, tests pass)
2. Make `run_loop` return `LoopResult` (update spawn to use it)
3. Extract `spawn_and_run()` (spawn becomes thin wrapper)
4. Add `scope exit` command + state helpers
5. Wire exit detection into loop engine
6. Create Workflow builder + tests
7. Create `scope workflow` command
8. Remove --after/--pipe/depends_on/dag.py
9. Update exports

## Files Modified

| File | Action |
|------|--------|
| `src/scope/core/loop.py` | **Create** — extracted loop engine |
| `src/scope/commands/exit.py` | **Create** — `scope exit` command |
| `src/scope/workflow.py` | **Create** — Workflow builder API |
| `src/scope/commands/workflow_cmd.py` | **Create** — `scope workflow` CLI |
| `src/scope/commands/spawn.py` | Simplify — delegates loop to `spawn_and_run()` |
| `src/scope/core/session.py` | Remove `depends_on` field |
| `src/scope/core/state.py` | Remove depends_on persistence, remove `get_dependencies()`, add exit_reason helpers |
| `src/scope/core/dag.py` | **Delete** |
| `src/scope/cli.py` | Add `workflow` and `exit` commands |
| `src/scope/__init__.py` | Export Workflow, Phase, PhaseResult |

## Verification

```bash
# Unit tests
pytest tests/ -v

# Smoke test: builder API
python -c "from scope import Workflow; wf = Workflow('test'); wf.phase('p1', task='hello', checker='true')"

# Smoke test: exit command
scope exit "testing exit reason"

# Integration: run a workflow file
scope workflow examples/hello.py
```

## Design Note: `scope exit` as Course Correction

The key insight: abort is destructive ("something went wrong"), but exit is intentional ("I've determined this path won't work, here's why").

Any agent inside any loop can call `scope exit "reason"` to cleanly halt the workflow. The reason propagates back through:

```
Agent → scope exit "reason" → session state=exited, exit_reason file
  → loop engine detects exited state → LoopResult(verdict="exit", exit_reason=...)
    → Workflow.run() stops pipeline → returns results with exit reason
      → caller sees exactly why and where the workflow stopped
```

This gives agents the power to course-correct without the orchestrator needing to anticipate every failure mode.
