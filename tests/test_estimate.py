"""Tests and evaluation benchmark for scope estimate command."""

import pytest
from click.testing import CliRunner

import orjson

from scope.commands.estimate import estimate, extract_file_references, recommend


@pytest.fixture
def cli_runner():
    return CliRunner()


# --- Unit tests for helper functions ---


def test_recommend_atomic():
    """Low file count and low tokens should be atomic."""
    assert recommend(5000, 1) == "atomic"
    assert recommend(15000, 2) == "atomic"
    assert recommend(19999, 2) == "atomic"


def test_recommend_composite():
    """High file count or high tokens should be composite."""
    assert recommend(50000, 2) == "composite"
    assert recommend(10000, 5) == "composite"
    assert recommend(45000, 4) == "composite"


def test_recommend_borderline():
    """Edge cases should be borderline."""
    assert recommend(25000, 3) == "borderline"
    assert recommend(35000, 2) == "borderline"


def test_recommend_unclear():
    """Zero files should be unclear."""
    assert recommend(0, 0) == "unclear"
    assert recommend(100, 0) == "unclear"  # tokens but no files = still unclear


def test_extract_file_references_explicit_path(tmp_path):
    """Should find explicitly named files."""
    (tmp_path / "foo.py").write_text("# test")
    files = extract_file_references("fix the bug in foo.py", tmp_path)
    assert len(files) == 1
    assert files[0].name == "foo.py"


def test_extract_file_references_multiple_files(tmp_path):
    """Should find multiple files mentioned."""
    (tmp_path / "foo.py").write_text("# test")
    (tmp_path / "bar.py").write_text("# test")
    files = extract_file_references("update foo.py and bar.py", tmp_path)
    assert len(files) == 2


def test_extract_file_references_nested_path(tmp_path):
    """Should find files in subdirectories."""
    subdir = tmp_path / "src"
    subdir.mkdir()
    (subdir / "cli.py").write_text("# test")
    files = extract_file_references("fix src/cli.py", tmp_path)
    assert len(files) == 1
    assert "cli.py" in str(files[0])


def test_extract_file_references_no_match(tmp_path):
    """Should return empty when no files match."""
    files = extract_file_references("do something vague", tmp_path)
    assert len(files) == 0


# --- Evaluation benchmark ---

# Each case: (task_description, expected_recommendation, description)
BENCHMARK_CASES = [
    # ATOMIC tasks - single file, clear scope
    ("fix the bug in trajectory.py", "atomic", "single file fix"),
    ("add a docstring to cli.py", "atomic", "single file documentation"),
    ("Update src/scope/commands/poll.py to add --trajectory flag", "atomic", "single file update with path"),

    # ATOMIC tasks - two files
    ("refactor spawn.py and poll.py to share common session loading logic", "atomic", "two file refactor"),

    # COMPOSITE tasks - many files
    ("refactor cli.py, spawn.py, poll.py, abort.py to use a plugin system", "composite", "multi-file refactor"),

    # UNCLEAR tasks - exploration needed
    ("explore how the hooks system works", "unclear", "exploration task"),
    ("come up with a plan for storing agent trajectory in the session file system", "unclear", "planning task"),
    ("update all commands to use the new error handling pattern", "unclear", "vague multi-file"),
    ("investigate the performance issue", "unclear", "investigation task"),

    # BORDERLINE tasks - moderate complexity
    ("update tmux.py and state.py to handle new session types", "borderline|atomic", "two large files"),
]


@pytest.fixture
def scope_codebase(tmp_path):
    """Create a mock codebase structure similar to scope."""
    src = tmp_path / "src" / "scope"
    src.mkdir(parents=True)

    # Create files with realistic sizes
    files = {
        "cli.py": 130,
        "trajectory.py": 120,
        "state.py": 450,
        "tmux.py": 600,
        "session.py": 80,
        "setup.py": 50,
    }
    for name, lines in files.items():
        (src / name).write_text("\n".join([f"# line {i}" for i in range(lines)]))

    commands = src / "commands"
    commands.mkdir()
    for name in ["spawn.py", "poll.py", "abort.py", "wait.py"]:
        (commands / name).write_text("\n".join([f"# line {i}" for i in range(100)]))

    return tmp_path


def test_benchmark_evaluation(cli_runner, scope_codebase, monkeypatch):
    """Run the evaluation benchmark and report accuracy."""
    monkeypatch.chdir(scope_codebase / "src" / "scope")

    results = []
    for task, expected, description in BENCHMARK_CASES:
        result = cli_runner.invoke(estimate, [task])
        assert result.exit_code == 0, f"Failed on: {task}"

        output = orjson.loads(result.output)
        actual = output["recommend"]

        # Handle multiple acceptable answers (e.g., "atomic|borderline")
        expected_options = expected.split("|")
        passed = actual in expected_options

        results.append({
            "task": description,
            "expected": expected,
            "actual": actual,
            "passed": passed,
        })

    # Calculate accuracy
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    accuracy = passed / total * 100

    # Print report
    print(f"\n{'='*60}")
    print(f"ESTIMATE BENCHMARK RESULTS: {passed}/{total} ({accuracy:.0f}%)")
    print(f"{'='*60}")
    for r in results:
        status = "✓" if r["passed"] else "✗"
        print(f"{status} {r['task']}: expected={r['expected']}, actual={r['actual']}")
    print(f"{'='*60}\n")

    # Assert minimum accuracy threshold
    assert accuracy >= 80, f"Accuracy {accuracy:.0f}% below 80% threshold"


# --- CLI integration tests ---


def test_estimate_cli_basic(cli_runner, scope_codebase, monkeypatch):
    """Test basic CLI invocation."""
    monkeypatch.chdir(scope_codebase / "src" / "scope")

    result = cli_runner.invoke(estimate, ["fix cli.py"])

    assert result.exit_code == 0
    output = orjson.loads(result.output)
    assert "recommend" in output
    assert "file_count" in output
    assert "tokens_est" in output


def test_estimate_cli_verbose(cli_runner, scope_codebase, monkeypatch):
    """Test verbose output includes file list."""
    monkeypatch.chdir(scope_codebase / "src" / "scope")

    result = cli_runner.invoke(estimate, ["fix cli.py", "--verbose"])

    assert result.exit_code == 0
    output = orjson.loads(result.output)
    assert "files" in output
    assert len(output["files"]) > 0


def test_estimate_cli_explicit_files(cli_runner, scope_codebase, monkeypatch):
    """Test explicit file specification."""
    monkeypatch.chdir(scope_codebase / "src" / "scope")

    result = cli_runner.invoke(estimate, ["do something", "-f", "cli.py", "-f", "state.py"])

    assert result.exit_code == 0
    output = orjson.loads(result.output)
    assert output["file_count"] == 2
    assert output["recommend"] != "unclear"  # explicit files should not be unclear
