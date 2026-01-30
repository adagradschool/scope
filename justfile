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
    scope setup

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

# Bump version, tag, and push: just bump minor OR just bump patch
bump type:
    #!/usr/bin/env bash
    set -euo pipefail
    branch=$(git branch --show-current)
    [[ "$branch" == "main" ]] || { echo "Error: must be on main branch (currently on $branch)"; exit 1; }
    git pull
    current=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
    IFS='.' read -r major minor patch <<< "$current"
    case "{{type}}" in
        minor) new_version="$major.$((minor + 1)).0" ;;
        patch) new_version="$major.$minor.$((patch + 1))" ;;
        *) echo "Usage: just bump [minor|patch]"; exit 1 ;;
    esac
    echo "Bump version: $current -> $new_version (will tag, push, and create PR)"
    read -p "Proceed? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
    git checkout -b "release/v$new_version"
    sed -i '' "s/^version = \"$current\"/version = \"$new_version\"/" pyproject.toml
    git add pyproject.toml
    git commit -m "bump: v$new_version"
    git tag "v$new_version"
    git push origin HEAD --tags
    gh pr create --title "Release" --body "v$new_version"
    echo "Pushed v$new_version and created PR"
