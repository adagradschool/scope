# Scope Project Knowledge

## Project Identity
- Repository: `scope`
- Python package: `scopeai` (`pyproject.toml`)
- Runtime identity: a CLI/TUI substrate for subagent orchestration in Claude Code, with primitives like `spawn`, `wait`, and `poll` (`README.md`).

## Architecture Snapshot
- Source root: `src/scope/`
- Core modules:
  - `commands/`: user-facing CLI commands (`spawn`, `wait`, `poll`, `abort`, `resume`, `setup`, `workflow`, etc.)
  - `core/`: session/state/project/tmux/loop primitives
  - `tui/`: Textual dashboard app and widgets
  - `hooks/`: Claude hook installation and handling
- Entry point: `src/scope/cli.py` (Click group, `scope` command + subcommands).

## State and Storage Model
- Session state is filesystem-backed and project-scoped via `src/scope/core/project.py` and `src/scope/core/state.py`.
- Effective storage base: `~/.scope/repos/{project-identifier}/`
  - `sessions/{session_id}/` stores task, state, parent, tmux, timestamps, loop artifacts.
  - `next_id` and lock files support deterministic, concurrent-safe ID allocation.
- Lifecycle/terminal states used in command flows include `done`, `aborted`, `failed`, and `exited`.

## Primary Workflows and Commands
- `scope`: launches the TUI (with tmux session/window management in `cli.py`).
- `scope spawn <prompt> --checker ...`: creates a session and runs a doer-checker loop.
- `scope wait <id...>`: blocks until session(s) hit terminal states.
- `scope poll <id>`: retrieves current status/result signal.
- `scope setup`: installs/refreshes hooks and dependency setup.
- Related lifecycle commands: `abort`, `resume`, `workflow`, `trajectory`, `exit`, `update`, `uninstall`, `evolve`, `rubric`.

## Tooling Baseline
- Python: `>=3.10`
- Core deps: Click, Textual, orjson, watchfiles (`pyproject.toml`)
- Dev/test deps: pytest, pytest-xdist, pytest-asyncio, ruff
- Task runner and workflows: `justfile` recipes (`format`, `lint`, `test`, `check`)
- Package/runtime workflow commonly uses `uv` (`README.md`, `justfile`).

## Repository Landmarks
- `README.md`: positioning, quick start, and orchestration patterns.
- `docs/`: philosophy, UX, architecture, orchestration guidance.
- `tests/`: command and core behavior regression coverage.
- `workflows/`: scripted orchestration workflow examples.
- `plans/`: project planning artifacts.
- `.tickets/`: ticket and execution metadata used by this workspace.

## Practical Guidance for Agents
- Prefer minimally invasive edits in command/core modules where behavior is sensitive.
- Treat session lifecycle and state transitions as regression-prone; validate with targeted tests.
- Keep CLI help text and docs aligned whenever command behavior or flags change.
