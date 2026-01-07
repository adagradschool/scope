"""Tests for trajectory functions in hooks.handler and core.state."""

from datetime import datetime, timezone
from pathlib import Path

import orjson
import pytest

from scope.core.session import Session
from scope.core.state import (
    has_trajectory,
    load_trajectory,
    load_trajectory_index,
    save_session,
)
from scope.hooks.handler import build_trajectory_index, copy_trajectory


# --- Fixtures ---


@pytest.fixture
def sample_transcript_jsonl(tmp_path):
    """Create a sample transcript JSONL file with typical content."""
    transcript_file = tmp_path / "transcript.jsonl"
    entries = [
        {
            "type": "user",
            "timestamp": "2024-01-15T10:00:00Z",
            "message": {"content": "Help me fix the auth bug"},
        },
        {
            "type": "assistant",
            "timestamp": "2024-01-15T10:00:05Z",
            "message": {
                "model": "claude-3-5-sonnet-20241022",
                "content": [
                    {"type": "text", "text": "I'll help you fix the auth bug."},
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "Read",
                        "input": {"file_path": "/src/auth.py"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "timestamp": "2024-01-15T10:00:10Z",
            "message": {"content": "Great, please continue"},
        },
        {
            "type": "assistant",
            "timestamp": "2024-01-15T10:00:30Z",
            "message": {
                "model": "claude-3-5-sonnet-20241022",
                "content": [
                    {"type": "text", "text": "Found the issue."},
                    {
                        "type": "tool_use",
                        "id": "toolu_02",
                        "name": "Edit",
                        "input": {"file_path": "/src/auth.py"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_03",
                        "name": "Read",
                        "input": {"file_path": "/src/auth.py"},
                    },
                ],
            },
        },
        {
            "type": "assistant",
            "timestamp": "2024-01-15T10:00:45Z",
            "message": {
                "content": [{"type": "text", "text": "The bug is now fixed!"}],
            },
        },
    ]
    lines = [orjson.dumps(entry).decode() for entry in entries]
    transcript_file.write_text("\n".join(lines))
    return transcript_file


@pytest.fixture
def minimal_transcript_jsonl(tmp_path):
    """Create a minimal transcript with just one turn."""
    transcript_file = tmp_path / "minimal.jsonl"
    entries = [
        {
            "type": "user",
            "timestamp": "2024-01-15T12:00:00Z",
            "message": {"content": "Hello"},
        },
        {
            "type": "assistant",
            "timestamp": "2024-01-15T12:00:01Z",
            "message": {
                "model": "claude-3-5-haiku-20241022",
                "content": [{"type": "text", "text": "Hello! How can I help?"}],
            },
        },
    ]
    lines = [orjson.dumps(entry).decode() for entry in entries]
    transcript_file.write_text("\n".join(lines))
    return transcript_file


@pytest.fixture
def empty_transcript_jsonl(tmp_path):
    """Create an empty transcript file."""
    transcript_file = tmp_path / "empty.jsonl"
    transcript_file.write_text("")
    return transcript_file


@pytest.fixture
def malformed_transcript_jsonl(tmp_path):
    """Create a transcript with some malformed lines."""
    transcript_file = tmp_path / "malformed.jsonl"
    content = """{not valid json
{"type": "user", "message": {"content": "valid"}}
also invalid
{"type": "assistant", "message": {"content": [{"type": "text", "text": "response"}]}}
"""
    transcript_file.write_text(content)
    return transcript_file


@pytest.fixture
def setup_session_with_trajectory(mock_scope_base):
    """Create a session directory and populate with trajectory files."""

    def _create(session_id: str, trajectory_entries: list[dict], index: dict | None = None):
        session = Session(
            id=session_id,
            task="Test task",
            parent="",
            state="done",
            tmux_session=f"scope-{session_id}",
            created_at=datetime.now(timezone.utc),
        )
        save_session(session)

        session_dir = mock_scope_base / "sessions" / session_id

        # Write trajectory JSONL
        lines = [orjson.dumps(entry).decode() for entry in trajectory_entries]
        (session_dir / "trajectory.jsonl").write_text("\n".join(lines))

        # Write index if provided
        if index:
            (session_dir / "trajectory_index.json").write_bytes(
                orjson.dumps(index, option=orjson.OPT_INDENT_2)
            )

        return session_dir

    return _create


# --- Tests for build_trajectory_index ---


def test_build_trajectory_index_basic(sample_transcript_jsonl):
    """Test build_trajectory_index extracts correct stats from transcript."""
    index = build_trajectory_index(str(sample_transcript_jsonl))

    assert index is not None
    assert index["turn_count"] == 5  # 2 user + 3 assistant
    assert index["model"] == "claude-3-5-sonnet-20241022"
    assert index["tool_calls"] == ["Read", "Edit", "Read"]
    assert index["tool_summary"] == {"Read": 2, "Edit": 1}
    assert index["duration_seconds"] == 45  # 10:00:00 to 10:00:45


def test_build_trajectory_index_minimal(minimal_transcript_jsonl):
    """Test build_trajectory_index with minimal transcript."""
    index = build_trajectory_index(str(minimal_transcript_jsonl))

    assert index is not None
    assert index["turn_count"] == 2
    assert index["model"] == "claude-3-5-haiku-20241022"
    assert index["tool_calls"] == []
    assert index["tool_summary"] == {}
    assert index["duration_seconds"] == 1


def test_build_trajectory_index_empty(empty_transcript_jsonl):
    """Test build_trajectory_index with empty file returns empty stats."""
    index = build_trajectory_index(str(empty_transcript_jsonl))

    assert index is not None
    assert index["turn_count"] == 0
    assert index["tool_calls"] == []
    assert index["tool_summary"] == {}
    assert index["model"] is None
    assert index["duration_seconds"] is None


def test_build_trajectory_index_malformed(malformed_transcript_jsonl):
    """Test build_trajectory_index handles malformed JSON gracefully."""
    index = build_trajectory_index(str(malformed_transcript_jsonl))

    assert index is not None
    # Should only count the valid lines
    assert index["turn_count"] == 2  # 1 user + 1 assistant


def test_build_trajectory_index_missing_file(tmp_path):
    """Test build_trajectory_index returns None for missing file."""
    index = build_trajectory_index(str(tmp_path / "nonexistent.jsonl"))

    assert index is None


def test_build_trajectory_index_no_timestamps(tmp_path):
    """Test build_trajectory_index when timestamps are missing."""
    transcript_file = tmp_path / "no_timestamps.jsonl"
    entries = [
        {"type": "user", "message": {"content": "Hello"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}},
    ]
    lines = [orjson.dumps(entry).decode() for entry in entries]
    transcript_file.write_text("\n".join(lines))

    index = build_trajectory_index(str(transcript_file))

    assert index is not None
    assert index["duration_seconds"] is None
    assert index["turn_count"] == 2


# --- Tests for copy_trajectory ---


def test_copy_trajectory_success(sample_transcript_jsonl, tmp_path):
    """Test copy_trajectory copies file and creates index."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = copy_trajectory(str(sample_transcript_jsonl), session_dir)

    assert result is True
    assert (session_dir / "trajectory.jsonl").exists()
    assert (session_dir / "trajectory_index.json").exists()

    # Verify content was copied correctly
    original = sample_transcript_jsonl.read_text()
    copied = (session_dir / "trajectory.jsonl").read_text()
    assert original == copied

    # Verify index content
    index = orjson.loads((session_dir / "trajectory_index.json").read_bytes())
    assert index["turn_count"] == 5
    assert index["tool_calls"] == ["Read", "Edit", "Read"]


def test_copy_trajectory_missing_file(tmp_path):
    """Test copy_trajectory returns False for missing source."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = copy_trajectory(str(tmp_path / "nonexistent.jsonl"), session_dir)

    assert result is False
    assert not (session_dir / "trajectory.jsonl").exists()


def test_copy_trajectory_empty_file(empty_transcript_jsonl, tmp_path):
    """Test copy_trajectory handles empty transcript."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = copy_trajectory(str(empty_transcript_jsonl), session_dir)

    assert result is True
    assert (session_dir / "trajectory.jsonl").exists()
    # Index should still be created even for empty file
    assert (session_dir / "trajectory_index.json").exists()


def test_copy_trajectory_preserves_metadata(sample_transcript_jsonl, tmp_path):
    """Test copy_trajectory preserves file metadata via shutil.copy2."""
    import time

    session_dir = tmp_path / "session"
    session_dir.mkdir()

    # Get original mtime
    original_stat = sample_transcript_jsonl.stat()

    # Small delay to ensure we can detect timing differences
    time.sleep(0.01)

    copy_trajectory(str(sample_transcript_jsonl), session_dir)

    # Verify mtime is preserved (copy2 behavior)
    copied_stat = (session_dir / "trajectory.jsonl").stat()
    assert abs(original_stat.st_mtime - copied_stat.st_mtime) < 1.0


# --- Tests for load_trajectory ---


def test_load_trajectory_success(setup_session_with_trajectory):
    """Test load_trajectory returns parsed entries."""
    entries = [
        {"type": "user", "message": {"content": "Hello"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}},
    ]
    setup_session_with_trajectory("0", entries)

    result = load_trajectory("0")

    assert result is not None
    assert len(result) == 2
    assert result[0]["type"] == "user"
    assert result[1]["type"] == "assistant"


def test_load_trajectory_missing_session(mock_scope_base):
    """Test load_trajectory returns None for nonexistent session."""
    result = load_trajectory("nonexistent")

    assert result is None


def test_load_trajectory_no_trajectory_file(mock_scope_base):
    """Test load_trajectory returns None when trajectory file doesn't exist."""
    # Create session without trajectory
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = load_trajectory("0")

    assert result is None


def test_load_trajectory_empty_file(setup_session_with_trajectory, mock_scope_base):
    """Test load_trajectory handles empty file."""
    # Create session manually with empty trajectory
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "trajectory.jsonl").write_text("")

    result = load_trajectory("0")

    assert result == []


def test_load_trajectory_skips_malformed_lines(mock_scope_base):
    """Test load_trajectory skips malformed JSON lines."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    trajectory_content = """{invalid json
{"type": "user", "message": {"content": "valid"}}
also invalid
{"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}
"""
    (mock_scope_base / "sessions" / "0" / "trajectory.jsonl").write_text(trajectory_content)

    result = load_trajectory("0")

    assert result is not None
    assert len(result) == 2
    assert result[0]["type"] == "user"
    assert result[1]["type"] == "assistant"


# --- Tests for load_trajectory_index ---


def test_load_trajectory_index_success(setup_session_with_trajectory):
    """Test load_trajectory_index returns parsed index."""
    entries = [{"type": "user", "message": {"content": "Hello"}}]
    index = {
        "turn_count": 2,
        "tool_calls": ["Read"],
        "tool_summary": {"Read": 1},
        "duration_seconds": 30,
        "model": "claude-3-5-sonnet-20241022",
    }
    setup_session_with_trajectory("0", entries, index)

    result = load_trajectory_index("0")

    assert result is not None
    assert result["turn_count"] == 2
    assert result["tool_calls"] == ["Read"]
    assert result["model"] == "claude-3-5-sonnet-20241022"


def test_load_trajectory_index_missing_session(mock_scope_base):
    """Test load_trajectory_index returns None for nonexistent session."""
    result = load_trajectory_index("nonexistent")

    assert result is None


def test_load_trajectory_index_no_index_file(mock_scope_base):
    """Test load_trajectory_index returns None when index file doesn't exist."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = load_trajectory_index("0")

    assert result is None


def test_load_trajectory_index_malformed_json(mock_scope_base):
    """Test load_trajectory_index returns None for malformed JSON."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    (mock_scope_base / "sessions" / "0" / "trajectory_index.json").write_text("{invalid")

    result = load_trajectory_index("0")

    assert result is None


# --- Tests for has_trajectory ---


def test_has_trajectory_true(setup_session_with_trajectory):
    """Test has_trajectory returns True when trajectory exists."""
    entries = [{"type": "user", "message": {"content": "Hello"}}]
    setup_session_with_trajectory("0", entries)

    result = has_trajectory("0")

    assert result is True


def test_has_trajectory_false_no_file(mock_scope_base):
    """Test has_trajectory returns False when file doesn't exist."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = has_trajectory("0")

    assert result is False


def test_has_trajectory_false_no_session(mock_scope_base):
    """Test has_trajectory returns False for nonexistent session."""
    result = has_trajectory("nonexistent")

    assert result is False


def test_has_trajectory_with_nested_session(setup_session_with_trajectory):
    """Test has_trajectory works with nested session IDs."""
    # Create parent first
    parent = Session(
        id="0",
        task="Parent",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(parent)

    # Create child with trajectory
    entries = [{"type": "user", "message": {"content": "Child task"}}]
    setup_session_with_trajectory("0.1", entries)

    assert has_trajectory("0") is False
    assert has_trajectory("0.1") is True


# --- Tests for trajectory CLI command ---


from click.testing import CliRunner

from scope.commands.trajectory import trajectory


@pytest.fixture
def cli_runner():
    """Create a Click CLI test runner."""
    return CliRunner()


def test_trajectory_cli_default_shows_summary(
    cli_runner, setup_session_with_trajectory
):
    """Test that trajectory command shows summary by default."""
    entries = [
        {"type": "user", "message": {"content": "Hello"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}},
    ]
    index = {
        "turn_count": 2,
        "tool_calls": ["Read"],
        "tool_summary": {"Read": 1},
        "duration_seconds": 30,
        "model": "claude-3-5-sonnet-20241022",
    }
    setup_session_with_trajectory("0", entries, index)

    result = cli_runner.invoke(trajectory, ["0"])

    assert result.exit_code == 0
    output = orjson.loads(result.output)
    assert output["turn_count"] == 2
    assert output["tool_calls"] == ["Read"]
    assert output["model"] == "claude-3-5-sonnet-20241022"


def test_trajectory_cli_full_flag(cli_runner, setup_session_with_trajectory):
    """Test that --full flag shows pretty-printed trajectory."""
    entries = [
        {"type": "user", "message": {"content": "Hello world"}},
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hi there"}]},
        },
    ]
    index = {"turn_count": 2, "tool_calls": [], "tool_summary": {}}
    setup_session_with_trajectory("0", entries, index)

    result = cli_runner.invoke(trajectory, ["0", "--full"])

    assert result.exit_code == 0
    assert "USER:" in result.output
    assert "ASSISTANT:" in result.output


def test_trajectory_cli_json_flag(cli_runner, setup_session_with_trajectory):
    """Test that --json flag outputs raw JSONL."""
    entries = [
        {"type": "user", "message": {"content": "Hello"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hi"}]}},
    ]
    index = {"turn_count": 2, "tool_calls": [], "tool_summary": {}}
    setup_session_with_trajectory("0", entries, index)

    result = cli_runner.invoke(trajectory, ["0", "--json"])

    assert result.exit_code == 0
    lines = result.output.strip().split("\n")
    assert len(lines) == 2
    # Verify each line is valid JSON
    parsed = [orjson.loads(line) for line in lines]
    assert parsed[0]["type"] == "user"
    assert parsed[1]["type"] == "assistant"


def test_trajectory_cli_session_not_found(cli_runner, mock_scope_base):
    """Test error when session doesn't exist."""
    result = cli_runner.invoke(trajectory, ["nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_trajectory_cli_no_trajectory(cli_runner, mock_scope_base):
    """Test error when session exists but has no trajectory."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="running",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)

    result = cli_runner.invoke(trajectory, ["0"])

    assert result.exit_code == 1
    assert "No trajectory found" in result.output


def test_trajectory_cli_no_index_file(cli_runner, mock_scope_base):
    """Test error when trajectory exists but index is missing (default mode)."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    # Create trajectory file but no index
    session_dir = mock_scope_base / "sessions" / "0"
    (session_dir / "trajectory.jsonl").write_text('{"type": "user"}\n')

    result = cli_runner.invoke(trajectory, ["0"])

    assert result.exit_code == 1
    assert "No trajectory index found" in result.output


def test_trajectory_cli_json_flag_bypasses_index(cli_runner, mock_scope_base):
    """Test that --json works even without index file."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    # Create trajectory file but no index
    session_dir = mock_scope_base / "sessions" / "0"
    (session_dir / "trajectory.jsonl").write_text('{"type": "user", "content": "hi"}\n')

    result = cli_runner.invoke(trajectory, ["0", "--json"])

    assert result.exit_code == 0
    parsed = orjson.loads(result.output.strip())
    assert parsed["type"] == "user"


def test_trajectory_cli_full_flag_bypasses_index(cli_runner, mock_scope_base):
    """Test that --full works even without index file."""
    session = Session(
        id="0",
        task="Test",
        parent="",
        state="done",
        tmux_session="scope-0",
        created_at=datetime.now(timezone.utc),
    )
    save_session(session)
    # Create trajectory file but no index
    session_dir = mock_scope_base / "sessions" / "0"
    (session_dir / "trajectory.jsonl").write_text('{"type": "user", "content": "hi"}\n')

    result = cli_runner.invoke(trajectory, ["0", "--full"])

    assert result.exit_code == 0
    assert "USER:" in result.output or "[user]" in result.output
