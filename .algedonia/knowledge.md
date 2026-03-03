# Scope / ScopeAI Repository Knowledge

## Project Identity

- Repository name: `scope`
- Python distribution: `scopeai` (from `pyproject.toml`)
- Primary CLI entrypoint: `scope` via `scope.cli:main`
- Companion hook entrypoint: `scope-hook` via `scope.hooks.handler:main`
- Supported Python: `>=3.10`

## Purpose

Scope provides subagent orchestration primitives for Claude Code sessions.

- It is intentionally a substrate (visibility + control primitives), not an autonomous scheduler.
- Core operational model: spawn bounded subagents with fresh context, then observe/poll/wait via filesystem + tmux-backed sessions.
- Main value proposition in docs: reduce "context rot" in long-running work by delegating focused tasks to separate sessions.

## Key User Surfaces

- CLI commands in `src/scope/commands/` and registration in `src/scope/cli.py`.
- TUI dashboard in `src/scope/tui/app.py` launched by running `scope` without a subcommand.
- Setup/install hooks flow in `src/scope/commands/setup.py` and `src/scope/hooks/install.py`.
- Session orchestration primitives used by humans/agents: `spawn`, `poll`, `wait`, plus lifecycle controls like `abort`/`resume`.

## High-Level Architecture

- `src/scope/commands/`: Click command handlers and CLI-facing behaviors.
- `src/scope/core/`: orchestration internals (session/state/config/tmux/contract/loop/evolution helpers).
- `src/scope/hooks/`: Claude Code hook installation and runtime hook handler logic.
- `src/scope/tui/`: Textual-based control panel and interaction layer.
- `src/scope/workflow.py` and `commands/workflow_cmd.py`: workflow-oriented orchestration interfaces.

## Tooling and Conventions

- Dependency/runtime management is uv-based (`uv.lock`, `justfile` recipes).
- Lint/format: Ruff (`uv run ruff check src/`, `uv run ruff format src/`).
- Tests: Pytest (parallel recipe in `just test`, sequential in `just test-seq`).
- Build backend: Hatchling.

## Canonical Docs and Where to Look

- Product overview, philosophy, quick start, and command examples: `README.md`.
- Design intent and constraints: `docs/00-philosophy.md`.
- User interaction model and TUI expectations: `docs/01-ux.md`.
- Architectural decomposition and component model: `docs/02-architecture.md`.
- Orchestration patterns and strategy framing: `docs/03-orchestration-patterns.md`.
- Test behavior expectations and edge cases: `tests/`.

## Practical Orientation for Contributors

- Treat session state consistency and tmux lifecycle handling as critical paths.
- Keep CLI output/contracts stable unless intentionally versioned/documented.
- When modifying orchestration behavior, review both implementation (`src/scope/core/*`) and user guidance (`README.md`, `docs/*`) together.
