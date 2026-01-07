"""Estimate command for scope.

Estimate context cost for a task before deciding atomic vs composite.
"""

import re
from pathlib import Path

import click
import orjson


def extract_file_references(task: str, cwd: Path) -> list[Path]:
    """Extract file paths and patterns from a task description.

    Looks for:
    - Explicit paths: src/foo.py, ./bar.ts, /abs/path.js
    - Patterns: *.py, test_*.py, **/*.ts
    - Common references: "the X file", "in X.py"
    """
    files: list[Path] = []

    # Pattern 1: Explicit file paths (with extensions)
    path_pattern = r"[\w./\\-]+\.\w{1,4}"
    for match in re.finditer(path_pattern, task):
        candidate = match.group()
        # Skip URLs
        if "://" in candidate:
            continue
        path = cwd / candidate
        if path.exists() and path.is_file():
            files.append(path)

    # Pattern 2: Glob patterns
    glob_pattern = r"\*+\.?\w*"
    for match in re.finditer(glob_pattern, task):
        pattern = match.group()
        try:
            for path in cwd.rglob(pattern.lstrip("*").lstrip("/")):
                if path.is_file() and path not in files:
                    files.append(path)
        except Exception:
            pass

    # Pattern 3: Common file name references without path
    # e.g., "trajectory.py", "the cli module"
    name_pattern = r"\b(\w+\.(?:py|ts|js|tsx|jsx|rs|go|java|cpp|c|h))\b"
    for match in re.finditer(name_pattern, task, re.IGNORECASE):
        name = match.group(1)
        # Search for this file in common locations
        for found in cwd.rglob(name):
            if found.is_file() and found not in files:
                files.append(found)

    return files


def estimate_tokens(files: list[Path]) -> dict:
    """Estimate token count from files.

    Heuristic: ~15 tokens per line of code.
    """
    total_lines = 0
    file_stats = []

    for path in files:
        try:
            lines = len(path.read_text().splitlines())
            total_lines += lines
            file_stats.append(
                {
                    "file": str(path),
                    "lines": lines,
                }
            )
        except Exception:
            pass

    # Tokens estimate: 15 tokens per line (conservative)
    tokens_est = total_lines * 15

    # Add overhead for edits, analysis, conversation
    # Roughly 1.5x multiplier for a typical task
    tokens_with_overhead = int(tokens_est * 1.5)

    return {
        "files": file_stats,
        "file_count": len(file_stats),
        "total_lines": total_lines,
        "tokens_est": tokens_est,
        "tokens_with_overhead": tokens_with_overhead,
    }


def recommend(tokens_with_overhead: int, file_count: int) -> str:
    """Recommend atomic vs composite based on estimates."""
    # No files detected = unclear task, needs exploration first
    if file_count == 0:
        return "unclear"

    # Thresholds
    if file_count <= 2 and tokens_with_overhead < 20000:
        return "atomic"
    elif file_count >= 4 or tokens_with_overhead > 40000:
        return "composite"
    else:
        return "borderline"


@click.command()
@click.argument("task")
@click.option(
    "--files", "-f", multiple=True, help="Explicit files to include in estimate"
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed file breakdown")
def estimate(task: str, files: tuple[str, ...], verbose: bool) -> None:
    """Estimate context cost for a task.

    Analyzes the task description to identify likely files,
    counts lines, and estimates token usage.

    Returns a recommendation: atomic, composite, or borderline.

    Examples:

        scope estimate "fix the bug in trajectory.py"

        scope estimate "refactor auth across all modules"

        scope estimate "update cli.py" --files src/scope/cli.py
    """
    cwd = Path.cwd()

    # Collect files from task description
    detected_files = extract_file_references(task, cwd)

    # Add explicitly specified files
    for f in files:
        path = Path(f)
        if not path.is_absolute():
            path = cwd / f
        if path.exists() and path.is_file() and path not in detected_files:
            detected_files.append(path)

    # Estimate tokens
    stats = estimate_tokens(detected_files)

    # Make recommendation
    rec = recommend(stats["tokens_with_overhead"], stats["file_count"])

    # Build output
    output = {
        "task": task[:100] + "..." if len(task) > 100 else task,
        "file_count": stats["file_count"],
        "total_lines": stats["total_lines"],
        "tokens_est": stats["tokens_est"],
        "tokens_with_overhead": stats["tokens_with_overhead"],
        "recommend": rec,
    }

    if verbose:
        output["files"] = stats["files"]

    click.echo(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode())
