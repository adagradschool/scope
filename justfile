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

# Format code
format:
    uv run ruff format src/

# Lint code
lint:
    uv run ruff check src/

# Run tests
test:
    uv run pytest tests/ -v

# Run all checks (format, lint, test)
check: format lint test

# Run scope top
top:
    uv run scope top

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
