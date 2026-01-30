"""Tests for the evolution system (scope.core.evolve)."""

from pathlib import Path
from unittest.mock import MagicMock

import orjson
import pytest

from scope.core.evolve import (
    append_history,
    apply_candidate,
    build_critique_prompt,
    build_mutation_prompt,
    collect_loop_files,
    compute_diff,
    get_active_skill,
    get_active_skill_path,
    get_active_version,
    get_evolution_dir,
    init_baseline,
    list_staged,
    list_versions,
    pareto_select,
    reject_candidate,
    rollback,
    run_critique,
    run_mutation,
    run_evolution,
    spawn_evolution,
    stage_candidate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_SKILL = "# Fake Skill\n\nThis is a test skill.\n"


def _setup_evo_dir(tmp_path):
    """Create a minimal evolution dir with v0 baseline."""
    evo_dir = tmp_path / "evolution"
    v0_dir = evo_dir / "versions" / "v0"
    v0_dir.mkdir(parents=True)
    (v0_dir / "skill.md").write_text(FAKE_SKILL)
    (v0_dir / "meta.json").write_bytes(
        orjson.dumps({"created_at": "2024-01-01T00:00:00+00:00", "source": "baseline"})
    )
    (evo_dir / "active").write_text("v0")
    return evo_dir


def _patch_evo_dir(monkeypatch, evo_dir):
    """Patch get_evolution_dir to return evo_dir."""
    monkeypatch.setattr(
        "scope.core.evolve.get_evolution_dir", lambda: evo_dir
    )


def _patch_skills_dir(monkeypatch, tmp_path):
    """Patch get_claude_skills_dir to return a tmp_path subdir."""
    skills_dir = tmp_path / "claude_skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "scope.core.evolve.get_claude_skills_dir", lambda: skills_dir
    )
    return skills_dir


# ---------------------------------------------------------------------------
# 1. Baseline / storage
# ---------------------------------------------------------------------------


def test_get_evolution_dir(tmp_path, monkeypatch):
    """get_evolution_dir creates and returns ~/.scope/evolution/."""
    monkeypatch.setattr(
        "scope.core.evolve.Path.home", lambda: tmp_path
    )
    evo_dir = get_evolution_dir()
    assert evo_dir == tmp_path / ".scope" / "evolution"
    assert evo_dir.exists()


def test_init_baseline(tmp_path, monkeypatch):
    """init_baseline creates v0 with SCOPE_SKILL_CONTENT."""
    evo_dir = tmp_path / "evolution"
    _patch_evo_dir(monkeypatch, evo_dir)
    monkeypatch.setattr(
        "scope.core.evolve.SCOPE_SKILL_CONTENT", FAKE_SKILL
    )

    init_baseline()

    v0_dir = evo_dir / "versions" / "v0"
    assert v0_dir.exists()
    assert (v0_dir / "skill.md").read_text() == FAKE_SKILL
    meta = orjson.loads((v0_dir / "meta.json").read_bytes())
    assert meta["source"] == "baseline"
    assert (evo_dir / "active").read_text() == "v0"


def test_init_baseline_idempotent(tmp_path, monkeypatch):
    """init_baseline does nothing if v0 already exists."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    original_text = (evo_dir / "versions" / "v0" / "skill.md").read_text()
    init_baseline()
    assert (evo_dir / "versions" / "v0" / "skill.md").read_text() == original_text


# ---------------------------------------------------------------------------
# 2. Active version
# ---------------------------------------------------------------------------


def test_get_active_version(tmp_path, monkeypatch):
    """get_active_version reads the active file."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    assert get_active_version() == "v0"


def test_get_active_skill_path(tmp_path, monkeypatch):
    """get_active_skill_path returns path to active skill.md."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    path = get_active_skill_path()
    assert path == evo_dir / "versions" / "v0" / "skill.md"


def test_get_active_skill(tmp_path, monkeypatch):
    """get_active_skill returns the content of the active skill."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    assert get_active_skill() == FAKE_SKILL


# ---------------------------------------------------------------------------
# 3. Stage candidate
# ---------------------------------------------------------------------------


def test_stage_candidate(tmp_path, monkeypatch):
    """stage_candidate writes skill, critique, diff, meta and returns candidate id."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    proposed = "# Improved Skill\n\nBetter instructions.\n"
    critique = {
        "scores": {"pattern_adherence": 0.9, "instantiation_quality": 0.8, "enforcement_quality": 0.7}
    }

    cid = stage_candidate("sess-1", "proj-1", critique, proposed)

    assert cid.startswith("c-")
    cdir = evo_dir / "staged" / cid
    assert (cdir / "skill.md").read_text() == proposed
    assert (cdir / "diff.patch").exists()
    assert (cdir / "critique.json").exists()

    meta = orjson.loads((cdir / "meta.json").read_bytes())
    assert meta["loop_session_id"] == "sess-1"
    assert meta["project"] == "proj-1"
    assert meta["parent_version"] == "v0"
    assert meta["scores"]["pattern_adherence"] == 0.9

    # History event appended
    history = (evo_dir / "history.jsonl").read_bytes()
    event = orjson.loads(history.strip())
    assert event["event"] == "staged"
    assert event["candidate_id"] == cid


# ---------------------------------------------------------------------------
# 4. Apply candidate
# ---------------------------------------------------------------------------


def test_apply_candidate(tmp_path, monkeypatch):
    """apply_candidate promotes staged candidate to new version."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)
    skills_dir = _patch_skills_dir(monkeypatch, tmp_path)

    proposed = "# V1 Skill\n"
    critique = {"scores": {"pattern_adherence": 0.9, "instantiation_quality": 0.8, "enforcement_quality": 0.7}}
    cid = stage_candidate("sess-1", "proj-1", critique, proposed)

    apply_candidate(cid)

    # New version created
    v1_dir = evo_dir / "versions" / "v1"
    assert v1_dir.exists()
    assert (v1_dir / "skill.md").read_text() == proposed

    # Active pointer updated
    assert (evo_dir / "active").read_text() == "v1"

    # Skill written to claude skills dir
    assert (skills_dir / "scope" / "SKILL.md").read_text() == proposed

    # Staged dir removed
    assert not (evo_dir / "staged" / cid).exists()

    # History has both staged and applied events
    lines = (evo_dir / "history.jsonl").read_bytes().strip().split(b"\n")
    events = [orjson.loads(line) for line in lines]
    assert events[-1]["event"] == "applied"
    assert events[-1]["version"] == "v1"


# ---------------------------------------------------------------------------
# 5. Reject candidate
# ---------------------------------------------------------------------------


def test_reject_candidate(tmp_path, monkeypatch):
    """reject_candidate removes staged dir and logs rejection."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    proposed = "# Rejected Skill\n"
    cid = stage_candidate("sess-1", "proj-1", {}, proposed)
    assert (evo_dir / "staged" / cid).exists()

    reject_candidate(cid)

    assert not (evo_dir / "staged" / cid).exists()
    lines = (evo_dir / "history.jsonl").read_bytes().strip().split(b"\n")
    last_event = orjson.loads(lines[-1])
    assert last_event["event"] == "rejected"
    assert last_event["candidate_id"] == cid


# ---------------------------------------------------------------------------
# 6. Rollback
# ---------------------------------------------------------------------------


def test_rollback(tmp_path, monkeypatch):
    """rollback reverts active pointer and writes skill to skills dir."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)
    skills_dir = _patch_skills_dir(monkeypatch, tmp_path)

    # Create v1
    v1_dir = evo_dir / "versions" / "v1"
    v1_dir.mkdir(parents=True)
    (v1_dir / "skill.md").write_text("# V1\n")
    (v1_dir / "meta.json").write_bytes(orjson.dumps({"source": "evolution"}))
    (evo_dir / "active").write_text("v1")

    rollback("v0")

    assert (evo_dir / "active").read_text() == "v0"
    assert (skills_dir / "scope" / "SKILL.md").read_text() == FAKE_SKILL

    lines = (evo_dir / "history.jsonl").read_bytes().strip().split(b"\n")
    last = orjson.loads(lines[-1])
    assert last["event"] == "rollback"
    assert last["version"] == "v0"


def test_rollback_nonexistent_version(tmp_path, monkeypatch):
    """rollback raises FileNotFoundError for missing version."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    with pytest.raises(FileNotFoundError, match="v99"):
        rollback("v99")


# ---------------------------------------------------------------------------
# 7. Pareto selection
# ---------------------------------------------------------------------------


def test_pareto_select_single():
    """Single candidate is always non-dominated."""
    candidates = [{"scores": {"pattern_adherence": 0.5, "instantiation_quality": 0.5, "enforcement_quality": 0.5}}]
    result = pareto_select(candidates)
    assert len(result) == 1


def test_pareto_select_dominance():
    """Dominated candidate is removed."""
    a = {"id": "a", "scores": {"pattern_adherence": 0.9, "instantiation_quality": 0.9, "enforcement_quality": 0.9}}
    b = {"id": "b", "scores": {"pattern_adherence": 0.5, "instantiation_quality": 0.5, "enforcement_quality": 0.5}}
    result = pareto_select([a, b])
    assert len(result) == 1
    assert result[0]["id"] == "a"


def test_pareto_select_non_dominated():
    """Two non-dominated candidates both survive."""
    a = {"id": "a", "scores": {"pattern_adherence": 0.9, "instantiation_quality": 0.3, "enforcement_quality": 0.5}}
    b = {"id": "b", "scores": {"pattern_adherence": 0.3, "instantiation_quality": 0.9, "enforcement_quality": 0.5}}
    result = pareto_select([a, b])
    assert len(result) == 2


def test_pareto_select_empty():
    """Empty list returns empty."""
    assert pareto_select([]) == []


# ---------------------------------------------------------------------------
# 8. Diff
# ---------------------------------------------------------------------------


def test_compute_diff():
    """compute_diff returns a unified diff string."""
    current = "line1\nline2\nline3\n"
    proposed = "line1\nmodified\nline3\n"
    diff = compute_diff(current, proposed)
    assert "---" in diff
    assert "+++" in diff
    assert "-line2" in diff
    assert "+modified" in diff


def test_compute_diff_identical():
    """compute_diff returns empty string for identical inputs."""
    text = "same\n"
    assert compute_diff(text, text) == ""


# ---------------------------------------------------------------------------
# 9. List versions / staged
# ---------------------------------------------------------------------------


def test_list_versions(tmp_path, monkeypatch):
    """list_versions returns metadata sorted by version."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    versions = list_versions()
    assert len(versions) == 1
    assert versions[0]["version"] == "v0"
    assert versions[0]["source"] == "baseline"


def test_list_versions_empty(tmp_path, monkeypatch):
    """list_versions returns empty when no versions dir."""
    evo_dir = tmp_path / "evolution"
    evo_dir.mkdir(parents=True)
    _patch_evo_dir(monkeypatch, evo_dir)

    assert list_versions() == []


def test_list_staged(tmp_path, monkeypatch):
    """list_staged returns metadata for staged candidates."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    stage_candidate("s1", "p1", {"scores": {}}, "# Candidate\n")
    staged = list_staged()
    assert len(staged) == 1
    assert staged[0]["candidate_id"].startswith("c-")


def test_list_staged_empty(tmp_path, monkeypatch):
    """list_staged returns empty when no staged dir."""
    evo_dir = tmp_path / "evolution"
    evo_dir.mkdir(parents=True)
    _patch_evo_dir(monkeypatch, evo_dir)

    assert list_staged() == []


# ---------------------------------------------------------------------------
# 10. Append history
# ---------------------------------------------------------------------------


def test_append_history(tmp_path, monkeypatch):
    """append_history writes JSONL and adds timestamp."""
    evo_dir = tmp_path / "evolution"
    evo_dir.mkdir(parents=True)
    _patch_evo_dir(monkeypatch, evo_dir)

    append_history({"event": "test", "data": 42})
    append_history({"event": "test2"})

    lines = (evo_dir / "history.jsonl").read_bytes().strip().split(b"\n")
    assert len(lines) == 2
    first = orjson.loads(lines[0])
    assert first["event"] == "test"
    assert first["data"] == 42
    assert "timestamp" in first


def test_append_history_preserves_timestamp(tmp_path, monkeypatch):
    """append_history does not overwrite existing timestamp."""
    evo_dir = tmp_path / "evolution"
    evo_dir.mkdir(parents=True)
    _patch_evo_dir(monkeypatch, evo_dir)

    append_history({"event": "x", "timestamp": "custom"})
    line = orjson.loads((evo_dir / "history.jsonl").read_bytes().strip())
    assert line["timestamp"] == "custom"


# ---------------------------------------------------------------------------
# 11. Collect loop files
# ---------------------------------------------------------------------------


def test_collect_loop_files(tmp_path, monkeypatch):
    """collect_loop_files returns paths for session artifacts."""
    scope_dir = tmp_path / "scope"
    session_dir = scope_dir / "sessions" / "sess-1"
    session_dir.mkdir(parents=True)
    (session_dir / "task").write_text("do stuff")
    (session_dir / "result").write_text("done")
    (session_dir / "loop_state.json").write_bytes(
        orjson.dumps({"history": [{"iteration": 0, "doer_session": "d1", "checker_session": "c1"}]})
    )

    monkeypatch.setattr("scope.core.evolve.ensure_scope_dir", lambda: scope_dir)
    monkeypatch.setattr(
        "scope.core.evolve.load_loop_state",
        lambda sid: {"history": [{"iteration": 0, "doer_session": "d1", "checker_session": "c1"}]},
    )
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    files = collect_loop_files("sess-1")
    assert files["task"] == session_dir / "task"
    assert files["result"] == session_dir / "result"
    assert len(files["trajectories"]) == 2
    assert files["trajectories"][0]["role"] == "doer"
    assert files["trajectories"][1]["role"] == "checker"


# ---------------------------------------------------------------------------
# 12. Build critique prompt
# ---------------------------------------------------------------------------


def test_build_critique_prompt():
    """build_critique_prompt includes file paths and scoring instructions."""
    loop_files = {
        "skill": Path("/fake/skill.md"),
        "loop_state": Path("/fake/loop_state.json"),
        "task": Path("/fake/task"),
        "result": Path("/fake/result"),
        "trajectories": [
            {"session_id": "d1", "role": "doer", "iteration": 0, "trajectory": Path("/fake/d1/trajectory.jsonl")},
        ],
    }
    prompt = build_critique_prompt(loop_files)
    assert "/fake/skill.md" in prompt
    assert "pattern_adherence" in prompt
    assert "instantiation_quality" in prompt
    assert "enforcement_quality" in prompt
    assert "doer iteration 0" in prompt


def test_build_critique_prompt_no_trajectories():
    """build_critique_prompt works with empty trajectories."""
    loop_files = {
        "skill": Path("/s"),
        "loop_state": Path("/l"),
        "task": Path("/t"),
        "result": Path("/r"),
        "trajectories": [],
    }
    prompt = build_critique_prompt(loop_files)
    assert "Trajectories" not in prompt


# ---------------------------------------------------------------------------
# 13. Build mutation prompt
# ---------------------------------------------------------------------------


def test_build_mutation_prompt():
    """build_mutation_prompt includes suggestions and skill path."""
    critique = {
        "axes": {
            "pattern_adherence": {"suggestions": ["Be clearer about X"]},
            "instantiation_quality": {"suggestions": []},
            "enforcement_quality": {"suggestions": ["Add depth guard"]},
        }
    }
    prompt = build_mutation_prompt(critique, Path("/fake/skill.md"))
    assert "/fake/skill.md" in prompt
    assert "Be clearer about X" in prompt
    assert "Add depth guard" in prompt


def test_build_mutation_prompt_no_suggestions():
    """build_mutation_prompt handles empty critique axes."""
    prompt = build_mutation_prompt({}, Path("/skill.md"))
    assert "(no suggestions)" in prompt


# ---------------------------------------------------------------------------
# 14. Run critique (mocked subprocess)
# ---------------------------------------------------------------------------


def test_run_critique(tmp_path, monkeypatch):
    """run_critique spawns subagent, waits, and parses JSON result."""
    scope_dir = tmp_path / "scope"
    spawned_dir = scope_dir / "sessions" / "critique-1"
    spawned_dir.mkdir(parents=True)
    critique_json = {
        "scores": {"pattern_adherence": 0.8, "instantiation_quality": 0.7, "enforcement_quality": 0.9},
        "axes": {},
    }
    (spawned_dir / "result").write_text(orjson.dumps(critique_json).decode())

    monkeypatch.setattr("scope.core.evolve.ensure_scope_dir", lambda: scope_dir)
    monkeypatch.setattr(
        "scope.core.evolve.collect_loop_files",
        lambda sid: {
            "skill": Path("/s"), "loop_state": Path("/l"),
            "task": Path("/t"), "result": Path("/r"), "trajectories": [],
        },
    )

    spawn_result = MagicMock()
    spawn_result.stdout = "critique-1\n"
    spawn_result.stderr = ""
    wait_result = MagicMock()

    call_count = {"n": 0}

    def fake_run(cmd, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return spawn_result
        return wait_result

    monkeypatch.setattr("scope.core.evolve.subprocess.run", fake_run)

    result = run_critique("sess-1")
    assert result["scores"]["pattern_adherence"] == 0.8


def test_run_critique_spawn_failure(tmp_path, monkeypatch):
    """run_critique raises if spawn returns empty stdout."""
    monkeypatch.setattr(
        "scope.core.evolve.collect_loop_files",
        lambda sid: {
            "skill": Path("/s"), "loop_state": Path("/l"),
            "task": Path("/t"), "result": Path("/r"), "trajectories": [],
        },
    )
    fail_result = MagicMock()
    fail_result.stdout = ""
    fail_result.stderr = "error"
    monkeypatch.setattr("scope.core.evolve.subprocess.run", lambda cmd, **kw: fail_result)

    with pytest.raises(RuntimeError, match="Failed to spawn critique"):
        run_critique("sess-1")


# ---------------------------------------------------------------------------
# 15. Run mutation (mocked subprocess)
# ---------------------------------------------------------------------------


def test_run_mutation(tmp_path, monkeypatch):
    """run_mutation spawns subagent and extracts skill text."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    scope_dir = tmp_path / "scope"
    spawned_dir = scope_dir / "sessions" / "mutate-1"
    spawned_dir.mkdir(parents=True)
    (spawned_dir / "result").write_text("```markdown\n# Mutated Skill\n```")

    monkeypatch.setattr("scope.core.evolve.ensure_scope_dir", lambda: scope_dir)

    spawn_result = MagicMock()
    spawn_result.stdout = "mutate-1\n"
    spawn_result.stderr = ""

    call_count = {"n": 0}

    def fake_run(cmd, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return spawn_result
        return MagicMock()

    monkeypatch.setattr("scope.core.evolve.subprocess.run", fake_run)

    result = run_mutation({"axes": {}})
    assert result == "# Mutated Skill"


# ---------------------------------------------------------------------------
# 16. Run evolution (mocked)
# ---------------------------------------------------------------------------


def test_run_evolution(tmp_path, monkeypatch):
    """run_evolution orchestrates critique → mutate → stage."""
    evo_dir = _setup_evo_dir(tmp_path)
    _patch_evo_dir(monkeypatch, evo_dir)

    monkeypatch.setattr(
        "scope.core.evolve.collect_loop_files",
        lambda sid: {"skill": Path("/s"), "loop_state": Path("/l"), "task": Path("/t"), "result": Path("/r"), "trajectories": []},
    )
    monkeypatch.setattr(
        "scope.core.evolve.run_critique",
        lambda sid: {"scores": {"pattern_adherence": 0.8, "instantiation_quality": 0.7, "enforcement_quality": 0.9}, "axes": {}},
    )
    monkeypatch.setattr(
        "scope.core.evolve.run_mutation",
        lambda critique: "# Evolved Skill\n",
    )

    cid = run_evolution("sess-1", "proj-1")
    assert cid.startswith("c-")
    assert (evo_dir / "staged" / cid / "skill.md").read_text() == "# Evolved Skill\n"


# ---------------------------------------------------------------------------
# 17. Spawn evolution (mocked Popen)
# ---------------------------------------------------------------------------


def test_spawn_evolution(monkeypatch):
    """spawn_evolution launches a background process."""
    monkeypatch.setattr("scope.core.evolve.get_project_identifier", lambda: "test-proj")

    popen_calls = []

    def fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        return MagicMock()

    monkeypatch.setattr("scope.core.evolve.subprocess.Popen", fake_popen)

    spawn_evolution("sess-1")

    assert len(popen_calls) == 1
    cmd = popen_calls[0]
    assert "scope" in cmd
    assert "evolve" in cmd
    assert "sess-1" in cmd
    assert "test-proj" in cmd
