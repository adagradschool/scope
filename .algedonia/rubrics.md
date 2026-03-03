# Scope / ScopeAI Code Review Rubrics

Use these rubrics when reviewing changes in this repository. They are specific to the `scope` Python CLI + orchestration codebase.

## 1. Correctness and Contracts

- CLI behavior must match declared command contracts in `src/scope/cli.py` and `README.md` examples.
- Session lifecycle changes must preserve core state transitions (`pending/running/done/aborted`) and parent-child semantics.
- `scope` remains a substrate, not a scheduler: avoid adding implicit orchestration logic that conflicts with documented primitives (`spawn`, `poll`, `wait`).
- Filesystem-backed state and tmux interactions must fail safely (clear error paths, no silent corruption of `.scope/` session state).

## 2. Code Clarity and Maintainability

- Keep boundaries clear across `commands/`, `core/`, `hooks/`, and `tui/`; avoid leaking command parsing into core logic.
- Prefer small, composable functions with explicit inputs/outputs over hidden global coupling.
- Preserve typed, readable Python (the package is marked `Typing :: Typed`): add type annotations for new public or non-trivial helpers.
- Error messages should be actionable for terminal users (what failed, where, and what to do next).

## 3. CLI and UX Expectations

- Any command change must keep CLI help text, options, and output shape stable unless the change explicitly includes a contract update.
- Human-facing output should be concise and script-safe; machine-consumed output (for orchestration) must remain deterministic.
- Changes affecting tmux behavior should avoid breaking attach/detach workflows and nested session usability.
- New user-facing behavior should include updated docs in `README.md` or `docs/` when applicable.

## 4. Testing Expectations (`pytest`)

- Behavior changes require tests in `tests/` that cover the intended path and at least one edge/error path.
- Orchestration-sensitive changes should include cases for session lineage, waiting/polling, and abort behavior.
- Hook/setup changes should include tests for idempotence and safe re-entry.
- Regressions should be reproduced by a failing test before fix when practical.
- Run repository-standard tests with `uv run pytest` (parallel mode is available through `just test`).

## 5. Lint and Style Expectations

- Lint/style must pass with repository tooling: `ruff check` and `ruff format` (see `just lint` and `just format`).
- Follow existing code style and module layout; avoid introducing one-off patterns unless justified.
- Keep diffs focused: no unrelated refactors mixed into behavior changes.
- Prefer non-destructive changes and explicit migrations for state/schema format updates.

## 6. Documentation and Operational Safety

- If command semantics change, update usage examples and operational guidance where users learn them first (`README.md`, `docs/01-ux.md`, `docs/03-orchestration-patterns.md`).
- Changes that affect session state files or hooks should document compatibility and recovery steps.
- Security-sensitive changes (shell commands, file writes, subprocess/tmux invocation) should be reviewed for injection and path safety risks.

## Review Exit Criteria

A change is ready when:

- Functionality aligns with Scope's stated model and contracts.
- Tests demonstrate the new behavior and guard important failure modes.
- Ruff formatting/lint checks pass.
- Documentation is updated for user-visible behavior changes.
- Diff scope is minimal and understandable.
