# Scope Tech Debt Reconnaissance (2026-03-03)

## Project Context
- Repository: `scope`
- Package: `scopeai`
- Focus areas reviewed: CLI commands, core lifecycle/state modules, TUI interaction paths, hook integration, CI/lint/test setup.

## Method
- Read architecture and product context from `README.md`, `.algedonia/knowledge.md`, and source layout.
- Ran quality checks:
  - `uv run pytest -q` -> `438 passed`
  - `uv run ruff check src` -> clean
  - `uv run ruff check src tests` -> fails with 15 issues (all in tests)
- Performed targeted static scan for lifecycle-risk patterns (state handling, tmux orchestration, error swallowing, duplicated orchestration code).

## Highest-Leverage Actions (Prioritized)

### 1. Harden platform compatibility and project-root detection
**Why high leverage**
- Breaks first-run behavior on systems without `git` on `PATH`, despite code intending fallback behavior.
- Packaging metadata currently claims `Operating System :: OS Independent` while core logic uses Unix-only `fcntl` locks.

**Evidence**
- `src/scope/core/project.py:15-23` catches only `subprocess.CalledProcessError`; `FileNotFoundError` is not handled for missing `git`.
- `src/scope/core/state.py` and `src/scope/core/lru.py` rely on `fcntl`.
- `pyproject.toml:25` declares OS independence.

**Impact**
- Installation/runtime surprises on non-Unix environments.
- Inconsistent packaging promises versus actual runtime constraints.

### 2. Unify duplicated session spawn/resume bootstrap logic
**Why high leverage**
- Same sensitive lifecycle steps are copied across CLI and TUI flows, increasing regression risk and inconsistency.
- Future fixes to spawn/resume behavior require multi-file synchronization.

**Evidence**
- Near-identical window creation + env wiring + pane option + hook install patterns in:
  - `src/scope/commands/spawn.py:193-224`
  - `src/scope/commands/resume.py:102-141`
  - `src/scope/tui/app.py:261-295`
  - `src/scope/tui/app.py:412-437`

**Impact**
- Higher maintenance cost and drift in lifecycle behavior under load/failure.

### 3. Reduce silent exception swallowing in critical tmux/UI paths
**Why high leverage**
- Failures in stateful orchestration steps can be hidden, making issues non-deterministic and hard to diagnose.
- Particularly risky for pane/session metadata (`@scope_session_id`) that drives session routing and UX behavior.

**Evidence**
- Multiple `except TmuxError: pass` and broad `except Exception: pass` patterns in:
  - `src/scope/commands/spawn.py:210-217`, `313-317`, `329-332`
  - `src/scope/commands/resume.py:130-136`
  - `src/scope/tui/app.py:273-320`, `372-380`, `426-445`, `463-466`
  - `src/scope/tui/widgets/session_tree.py:365-366`, `419-420`, `489-490`

**Impact**
- Hidden partial-failure states.
- Harder incident triage and increased user confusion when UI/actions partially fail.

### 4. Close quality gate gap: CI and local recipes do not lint tests
**Why high leverage**
- Current guardrails miss a growing class of code hygiene issues in tests.
- Existing debt is measurable and already present.

**Evidence**
- `justfile:24-25` runs `ruff check src/` only.
- `.github/workflows/ci.yml:30-31` delegates lint to `just lint`, therefore also excluding tests.
- `uv run ruff check src tests` reports 15 violations (unused imports/vars and import order in tests).

**Impact**
- Slower test maintenance and less trustworthy signal from CI quality checks.

### 5. Make wait-summary status inference deterministic and less fragile
**Why medium leverage**
- `wait --summary` computes test status from loose keyword matching and may report false fail/pass.
- Summary generation depends on external `claude -p` call with timeout/fallback behavior.

**Evidence**
- Keyword heuristics in `src/scope/commands/wait.py:254-265` (`"failed"`, `"error"`, `"passed"`, etc.).
- External summarizer dependency in `src/scope/commands/wait.py:232-241` via `src/scope/core/summarize.py:37-57`.

**Impact**
- Non-deterministic operator signals in automation pipelines.
- Reduced confidence in session outcome summaries.

## Secondary Opportunities
- Tighten exception granularity in `src/scope/commands/evolve.py` (many `except Exception as e` blocks).
- Add richer diagnostics/telemetry for tmux failure points where suppression remains intentional.

## Ticketization Plan
1. #3 `Handle missing git and align platform metadata with fcntl usage`
   - Scope: Harden root detection fallback, align platform metadata/docs with runtime locking constraints.
   - Maps to finding: 1
2. #4 `Extract shared session bootstrap helper for CLI and TUI`
   - Scope: Consolidate duplicated spawn/resume setup paths into one lifecycle bootstrap abstraction.
   - Maps to finding: 2
3. #6 `Replace silent tmux/UI exception swallowing with actionable diagnostics`
   - Scope: Remove or narrow `pass`-based handling in critical paths; emit actionable diagnostics on recoverable errors.
   - Maps to finding: 3
4. #5 `Include tests in lint gate and fix existing Ruff violations`
   - Scope: Lint `src/` + `tests/` consistently in local/CI, remediate current violations.
   - Maps to finding: 4
5. #7 `Make scope wait --summary test-status and summary output deterministic`
   - Scope: Replace fragile keyword heuristics with deterministic status/summary behavior and edge-case coverage.
   - Maps to finding: 5

## Recommended Execution Order
1. #3
2. #4
3. #6
4. #5
5. #7

## Notes
- This document is reconnaissance only; no implementation changes are included.
