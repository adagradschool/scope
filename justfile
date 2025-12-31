# Default recipe
default:
    @just --list

# Install dependencies
install:
    uv sync

# Install in development mode
dev:
    uv sync --dev
    uv pip install -e .

# Install locally as tool (force reinstall)
local:
    uv tool install . --force --reinstall

# Format code
format:
    uv run ruff format src/

# Lint code
lint:
    uv run ruff check src/

# Run tests (parallel)
test:
    uv run pytest tests/ -n auto -q

# Run tests (sequential)
test-seq:
    uv run pytest tests/ -v

# Run all checks (format, lint, test)
check: format lint test

# Run scope TUI
tui:
    uv run scope

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +

# Kill all scope tmux sessions and remove global scope directory
nuke:
    #!/usr/bin/env bash
    tmux list-sessions -F '#{session_name}' 2>/dev/null | grep '^scope-' | xargs -I {} tmux kill-session -t {} 2>/dev/null || true
    rm -rf ~/.scope
    echo "Killed all scope sessions and removed ~/.scope/"
