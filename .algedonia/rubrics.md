# Scope Engineering Rubric

## Purpose
Use this rubric when implementing tickets in `scope` (package `scopeai`). Prioritize safe behavior changes in orchestration workflows over cosmetic refactors.

## 1. Behavioral Safety
- Preserve existing CLI/TUI semantics unless the ticket explicitly changes behavior.
- Treat session lifecycle behavior as high-risk: `spawn`, `wait`, `poll`, `abort`, `resume`, `workflow`, and top-level `scope` launch behavior.
- Keep session state transitions deterministic and filesystem-backed; avoid introducing hidden in-memory state that can desynchronize from `~/.scope/repos/{project}/sessions/`.
- Maintain alias resolution, session ID generation, and parent-child session lineage correctness.

## 2. Testing Expectations
- Any behavioral change to commands or lifecycle logic must include/adjust tests under `tests/`.
- Prefer targeted command-level coverage (for example `tests/test_spawn.py`, `tests/test_wait.py`, `tests/test_poll.py`, `tests/test_abort.py`, `tests/test_resume.py`, `tests/test_workflow_cmd.py`).
- Validate both success and failure paths, including terminal states (`done`, `aborted`, `failed`, `exited`) and non-zero exit codes.
- Run relevant local checks before handoff (`ruff format`, `ruff check`, and affected pytest scope).

## 3. Code Quality
- Keep diffs small and intention-revealing; avoid broad rewrites without clear need.
- Preserve typed interfaces and dataclass contracts in `src/scope/core` and `src/scope/workflow.py`.
- Eliminate dead code and duplication; prefer extracting shared helpers over copy/paste across command modules.
- Keep command error messages actionable: include cause and concrete fix where possible.

## 4. Docs and UX Consistency
- If user-visible behavior changes, update all relevant surfaces in the same ticket: command help text, `README.md`, and any impacted docs in `docs/`.
- Ensure examples reflect real command flags and current defaults.
- Keep terminology consistent: sessions, aliases, lifecycle states, and checker/rubric language.

## 5. Operational Robustness
- Use atomic or lock-protected filesystem operations where concurrency is possible (for example ID generation).
- Handle missing files, missing sessions, and tmux failures explicitly with clear non-zero exits.
- Prefer idempotent setup/update paths for hooks and environment bootstrapping.
- Never silently swallow state corruption risks; fail fast with diagnostics.

## Done Criteria
- Behavior is preserved or intentionally changed per ticket scope.
- Tests and checks cover the modified behavior.
- Docs/help output are synchronized with behavior.
- Changes are readable, minimal, and safe for concurrent orchestration usage.
