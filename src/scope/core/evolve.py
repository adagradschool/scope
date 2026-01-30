"""Evolution system for scope skill improvement.

Analyzes loop trajectories, critiques the skill text, proposes mutations,
and manages versioned skill candidates through a Pareto selection process.

Storage layout (all under ~/.scope/evolution/):
  versions/v{N}/skill.md, meta.json   — accepted versions
  staged/c-{hash12}/                   — candidate revisions pending review
  active                               — current version name (e.g. "v0")
  history.jsonl                        — append-only event log
"""

import difflib
import hashlib
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import orjson

from scope.core.project import get_project_identifier
from scope.core.state import ensure_scope_dir, load_loop_state
from scope.hooks.install import SCOPE_SKILL_CONTENT, get_claude_skills_dir


# ---------------------------------------------------------------------------
# Storage utilities
# ---------------------------------------------------------------------------


def get_evolution_dir() -> Path:
    """Return ~/.scope/evolution/, creating it if needed."""
    evo_dir = Path.home() / ".scope" / "evolution"
    evo_dir.mkdir(parents=True, exist_ok=True)
    return evo_dir


def get_active_version() -> str:
    """Read the active file and return the current version name (e.g. 'v0')."""
    active_file = get_evolution_dir() / "active"
    if not active_file.exists():
        init_baseline()
    return active_file.read_text().strip()


def get_active_skill_path() -> Path:
    """Return the path to the active version's skill.md."""
    version = get_active_version()
    return get_evolution_dir() / "versions" / version / "skill.md"


def get_active_skill() -> str:
    """Read and return the active version's skill.md content."""
    return get_active_skill_path().read_text()


def init_baseline() -> None:
    """Snapshot SCOPE_SKILL_CONTENT as v0 if it doesn't already exist."""
    evo_dir = get_evolution_dir()
    v0_dir = evo_dir / "versions" / "v0"
    if v0_dir.exists():
        return

    v0_dir.mkdir(parents=True, exist_ok=True)
    (v0_dir / "skill.md").write_text(SCOPE_SKILL_CONTENT)
    (v0_dir / "meta.json").write_bytes(
        orjson.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "baseline",
            }
        )
    )
    (evo_dir / "active").write_text("v0")


def list_versions() -> list[dict]:
    """Return metadata for all versions, sorted by version number."""
    versions_dir = get_evolution_dir() / "versions"
    if not versions_dir.exists():
        return []

    result = []
    for vdir in sorted(versions_dir.iterdir()):
        if not vdir.is_dir():
            continue
        meta_file = vdir / "meta.json"
        if not meta_file.exists():
            continue
        meta = orjson.loads(meta_file.read_bytes())
        meta["version"] = vdir.name
        result.append(meta)
    return result


def list_staged() -> list[dict]:
    """Return metadata for all staged candidates."""
    staged_dir = get_evolution_dir() / "staged"
    if not staged_dir.exists():
        return []

    result = []
    for cdir in sorted(staged_dir.iterdir()):
        if not cdir.is_dir():
            continue
        meta_file = cdir / "meta.json"
        if not meta_file.exists():
            continue
        meta = orjson.loads(meta_file.read_bytes())
        meta["candidate_id"] = cdir.name
        result.append(meta)
    return result


def append_history(event: dict) -> None:
    """Append a JSON line to history.jsonl, adding timestamp if not present."""
    if "timestamp" not in event:
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
    history_path = get_evolution_dir() / "history.jsonl"
    with history_path.open("ab") as f:
        f.write(orjson.dumps(event) + b"\n")


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def compute_diff(current: str, proposed: str) -> str:
    """Compute a unified diff between current and proposed skill text."""
    current_lines = current.splitlines(keepends=True)
    proposed_lines = proposed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        current_lines,
        proposed_lines,
        fromfile="current/skill.md",
        tofile="proposed/skill.md",
    )
    return "".join(diff)


def stage_candidate(
    session_id: str, project_id: str, critique: dict, proposed_skill: str
) -> str:
    """Stage a candidate skill revision.

    Hashes the proposed text to create a candidate ID, writes all artifacts
    to staged/c-{hash12}/, and appends a history event.

    Returns the candidate ID.
    """
    hash12 = hashlib.sha256(proposed_skill.encode()).hexdigest()[:12]
    candidate_id = f"c-{hash12}"

    candidate_dir = get_evolution_dir() / "staged" / candidate_id
    candidate_dir.mkdir(parents=True, exist_ok=True)

    # Write skill text
    (candidate_dir / "skill.md").write_text(proposed_skill)

    # Write critique
    (candidate_dir / "critique.json").write_bytes(orjson.dumps(critique))

    # Write diff against active skill
    current_skill = get_active_skill()
    diff_text = compute_diff(current_skill, proposed_skill)
    (candidate_dir / "diff.patch").write_text(diff_text)

    # Write metadata
    active_version = get_active_version()
    scores = critique.get("scores", {})
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "loop_session_id": session_id,
        "project": project_id,
        "scores": scores,
        "parent_version": active_version,
    }
    (candidate_dir / "meta.json").write_bytes(orjson.dumps(meta))

    append_history(
        {
            "event": "staged",
            "candidate_id": candidate_id,
            "session_id": session_id,
            "project": project_id,
            "parent_version": active_version,
            "scores": scores,
        }
    )

    return candidate_id


def apply_candidate(candidate_id: str) -> None:
    """Promote a staged candidate to a new active version.

    Reads the candidate's skill.md and critique scores, creates a new
    version directory, updates the active pointer, writes the skill to
    the Claude skills directory, removes the staged directory, and
    appends a history event.
    """
    evo_dir = get_evolution_dir()
    candidate_dir = evo_dir / "staged" / candidate_id

    skill_text = (candidate_dir / "skill.md").read_text()
    meta = orjson.loads((candidate_dir / "meta.json").read_bytes())
    scores = meta.get("scores", {})
    parent_version = meta.get("parent_version", get_active_version())

    # Determine next version number
    versions_dir = evo_dir / "versions"
    existing = [
        int(d.name[1:])
        for d in versions_dir.iterdir()
        if d.is_dir() and d.name.startswith("v") and d.name[1:].isdigit()
    ]
    next_num = max(existing) + 1 if existing else 0
    version_id = f"v{next_num}"

    # Create version directory
    version_dir = versions_dir / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "skill.md").write_text(skill_text)
    (version_dir / "meta.json").write_bytes(
        orjson.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "evolution",
                "parent": parent_version,
                "scores": scores,
            }
        )
    )

    # Update active pointer
    (evo_dir / "active").write_text(version_id)

    # Write skill to Claude skills directory
    skill_dir = get_claude_skills_dir() / "scope"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_text)

    # Remove staged candidate
    shutil.rmtree(candidate_dir)

    append_history(
        {
            "event": "applied",
            "candidate_id": candidate_id,
            "version": version_id,
            "parent": parent_version,
            "scores": scores,
        }
    )


def reject_candidate(candidate_id: str) -> None:
    """Remove a staged candidate and log the rejection."""
    candidate_dir = get_evolution_dir() / "staged" / candidate_id
    shutil.rmtree(candidate_dir)

    append_history(
        {
            "event": "rejected",
            "candidate_id": candidate_id,
        }
    )


def rollback(version_id: str) -> None:
    """Roll back the active skill to a specific version.

    Verifies the version exists, updates the active pointer, and writes
    the skill to the Claude skills directory.
    """
    evo_dir = get_evolution_dir()
    version_dir = evo_dir / "versions" / version_id

    if not version_dir.exists():
        raise FileNotFoundError(f"Version {version_id} not found")

    skill_text = (version_dir / "skill.md").read_text()

    # Update active pointer
    (evo_dir / "active").write_text(version_id)

    # Write skill to Claude skills directory
    skill_dir = get_claude_skills_dir() / "scope"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_text)

    append_history(
        {
            "event": "rollback",
            "version": version_id,
        }
    )


# ---------------------------------------------------------------------------
# Pareto selection
# ---------------------------------------------------------------------------

SCORE_AXES = ("pattern_adherence", "instantiation_quality", "enforcement_quality")


def pareto_select(candidates: list[dict]) -> list[dict]:
    """Return the Pareto-optimal candidates.

    A candidate is dominated if another candidate is >= on all score axes
    and strictly > on at least one. Non-dominated candidates are returned.
    """

    def _dominates(a: dict, b: dict) -> bool:
        """Return True if a dominates b."""
        a_scores = a.get("scores", {})
        b_scores = b.get("scores", {})
        all_geq = all(
            a_scores.get(axis, 0.0) >= b_scores.get(axis, 0.0) for axis in SCORE_AXES
        )
        any_gt = any(
            a_scores.get(axis, 0.0) > b_scores.get(axis, 0.0) for axis in SCORE_AXES
        )
        return all_geq and any_gt

    non_dominated = []
    for i, candidate in enumerate(candidates):
        dominated = False
        for j, other in enumerate(candidates):
            if i != j and _dominates(other, candidate):
                dominated = True
                break
        if not dominated:
            non_dominated.append(candidate)
    return non_dominated


# ---------------------------------------------------------------------------
# Subagent functions
# ---------------------------------------------------------------------------


def collect_loop_files(session_id: str) -> dict:
    """Collect all file paths relevant to a completed loop session.

    Returns a dict with keys: loop_state, skill, task, result, trajectories.
    """
    scope_dir = ensure_scope_dir()
    session_dir = scope_dir / "sessions" / session_id

    loop_state = load_loop_state(session_id)

    loop_state_path = session_dir / "loop_state.json"
    skill_path = get_active_skill_path()
    task_path = session_dir / "task"
    result_path = session_dir / "result"

    trajectories: list[dict] = []
    if loop_state and "history" in loop_state:
        for entry in loop_state["history"]:
            iteration = entry.get("iteration", 0)
            doer_sid = entry.get("doer_session", "")
            if doer_sid:
                doer_traj = scope_dir / "sessions" / doer_sid / "trajectory.jsonl"
                trajectories.append(
                    {
                        "session_id": doer_sid,
                        "role": "doer",
                        "iteration": iteration,
                        "trajectory": doer_traj,
                    }
                )

            checker_sid = entry.get("checker_session", "")
            if checker_sid:
                checker_traj = scope_dir / "sessions" / checker_sid / "trajectory.jsonl"
                trajectories.append(
                    {
                        "session_id": checker_sid,
                        "role": "checker",
                        "iteration": iteration,
                        "trajectory": checker_traj,
                    }
                )

    return {
        "loop_state": loop_state_path,
        "skill": skill_path,
        "task": task_path,
        "result": result_path,
        "trajectories": trajectories,
    }


def build_critique_prompt(loop_files: dict) -> str:
    """Build the task prompt for a critique subagent.

    Instructs the agent to read relevant files and produce a structured
    JSON critique with three scored axes.
    """
    lines = [
        "You are a skill evolution critic. Analyze the following loop execution",
        "and critique the scope skill text that guided it.",
        "",
        "## Files to read",
        "",
        f"- Skill text: {loop_files['skill']}",
        f"- Loop state: {loop_files['loop_state']}",
        f"- Task: {loop_files['task']}",
        f"- Result: {loop_files['result']}",
        "",
    ]

    if loop_files["trajectories"]:
        lines.append("## Trajectories")
        lines.append("")
        for t in loop_files["trajectories"]:
            lines.append(
                f"- {t['role']} iteration {t['iteration']} "
                f"(session {t['session_id']}): {t['trajectory']}"
            )
        lines.append("")

    lines.extend(
        [
            "## Critique Instructions",
            "",
            "Evaluate the skill text on three axes, each scored 0.0 to 1.0:",
            "",
            "1. **pattern_adherence** — Did agents follow the patterns described",
            "   in the skill? Were instructions clear enough to follow?",
            "2. **instantiation_quality** — Did the skill guide agents to make",
            "   good decisions for this specific task? Were examples helpful?",
            "3. **enforcement_quality** — Were constraints and limits actually",
            "   enforced? Did agents respect recursion guards, depth limits, etc?",
            "",
            "For each axis provide:",
            "- `score`: float 0.0–1.0",
            "- `findings`: list of specific observations",
            "- `suggestions`: list of concrete improvements",
            "",
            "## Output Format",
            "",
            "Output ONLY a JSON object (no other text) with this structure:",
            "",
            "```json",
            "{",
            '  "scores": {',
            '    "pattern_adherence": 0.8,',
            '    "instantiation_quality": 0.7,',
            '    "enforcement_quality": 0.9',
            "  },",
            '  "axes": {',
            '    "pattern_adherence": {',
            '      "score": 0.8,',
            '      "findings": ["..."],',
            '      "suggestions": ["..."]',
            "    },",
            '    "instantiation_quality": {',
            '      "score": 0.7,',
            '      "findings": ["..."],',
            '      "suggestions": ["..."]',
            "    },",
            '    "enforcement_quality": {',
            '      "score": 0.9,',
            '      "findings": ["..."],',
            '      "suggestions": ["..."]',
            "    }",
            "  }",
            "}",
            "```",
        ]
    )

    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extract a JSON object from text, trying code blocks first then raw."""
    # Try to find JSON in a code block
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return orjson.loads(match.group(1).strip())
    # Try raw JSON — find first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return orjson.loads(text[start : end + 1])
    raise ValueError("No JSON found in text")


def _extract_skill_text(text: str) -> str:
    """Extract skill text from a markdown code block or return raw text."""
    match = re.search(r"```(?:markdown|md)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fall back to the full text (trim whitespace)
    return text.strip()


def run_critique(session_id: str) -> dict:
    """Run a critique subagent on a completed loop session.

    Collects loop files, builds the critique prompt, spawns a scope
    subagent with a validation checker, and parses the JSON result.
    """
    loop_files = collect_loop_files(session_id)
    prompt = build_critique_prompt(loop_files)

    checker = (
        "agent: Validate the output contains valid JSON critique with "
        "axes scores. ACCEPT if valid JSON with all 3 axes "
        "(pattern_adherence, instantiation_quality, enforcement_quality). "
        "RETRY otherwise."
    )

    result = subprocess.run(
        [
            "scope",
            "spawn",
            prompt,
            "--checker",
            checker,
            "--max-iterations",
            "2",
        ],
        capture_output=True,
        text=True,
    )

    spawned_id = result.stdout.strip()
    if not spawned_id:
        raise RuntimeError(f"Failed to spawn critique agent: {result.stderr.strip()}")

    # Wait for the critique session to complete
    subprocess.run(["scope", "wait", spawned_id], capture_output=True, text=True)

    # Read result
    scope_dir = ensure_scope_dir()
    result_file = scope_dir / "sessions" / spawned_id / "result"
    if not result_file.exists():
        raise RuntimeError(f"Critique session {spawned_id} produced no result file")

    raw = result_file.read_text()
    return _extract_json(raw)


def build_mutation_prompt(critique: dict, skill_path: Path) -> str:
    """Build the prompt for a mutation subagent.

    Instructs the agent to read the current skill, apply critique
    suggestions, and output the complete rewritten skill text.
    """
    suggestions = []
    axes = critique.get("axes", {})
    for axis_name, axis_data in axes.items():
        for s in axis_data.get("suggestions", []):
            suggestions.append(f"- [{axis_name}] {s}")

    suggestions_text = "\n".join(suggestions) if suggestions else "- (no suggestions)"

    lines = [
        "You are a skill text editor. Your job is to make MINIMAL, TARGETED",
        "changes to the scope skill based on critique feedback.",
        "",
        f"## Read the current skill at: {skill_path}",
        "",
        "## Critique suggestions to apply:",
        "",
        suggestions_text,
        "",
        "## Instructions",
        "",
        "1. Read the skill file above.",
        "2. Apply ONLY the suggested improvements. Do NOT restructure,",
        "   rewrite from scratch, or change things not mentioned.",
        "3. Preserve the existing YAML frontmatter and overall structure.",
        "4. Output the COMPLETE rewritten skill text in a markdown code block:",
        "",
        "```markdown",
        "... full skill text here ...",
        "```",
        "",
        "Make minimal changes. Every edit must trace back to a suggestion.",
    ]

    return "\n".join(lines)


def run_mutation(critique: dict) -> str:
    """Run a mutation subagent that rewrites the skill based on critique.

    Spawns a scope subagent with the mutation prompt, waits for
    completion, and extracts the proposed skill text.
    """
    skill_path = get_active_skill_path()
    prompt = build_mutation_prompt(critique, skill_path)

    checker = (
        "agent: Verify the output contains a complete scope skill text "
        "in a markdown code block. It should have YAML frontmatter and "
        "all major sections. ACCEPT if complete. RETRY otherwise."
    )

    result = subprocess.run(
        [
            "scope",
            "spawn",
            prompt,
            "--checker",
            checker,
            "--max-iterations",
            "2",
        ],
        capture_output=True,
        text=True,
    )

    spawned_id = result.stdout.strip()
    if not spawned_id:
        raise RuntimeError(f"Failed to spawn mutation agent: {result.stderr.strip()}")

    subprocess.run(["scope", "wait", spawned_id], capture_output=True, text=True)

    scope_dir = ensure_scope_dir()
    result_file = scope_dir / "sessions" / spawned_id / "result"
    if not result_file.exists():
        raise RuntimeError(f"Mutation session {spawned_id} produced no result file")

    raw = result_file.read_text()
    return _extract_skill_text(raw)


def run_evolution(session_id: str, project_id: str) -> str:
    """Orchestrate a full evolution cycle: critique → mutate → stage.

    Returns the candidate ID of the staged revision.
    """
    print(f"Evolution: collecting loop files for session {session_id}")
    collect_loop_files(session_id)

    print("Evolution: running critique subagent")
    critique = run_critique(session_id)

    print("Evolution: running mutation subagent")
    proposed_skill = run_mutation(critique)

    print("Evolution: staging candidate")
    candidate_id = stage_candidate(session_id, project_id, critique, proposed_skill)
    print(f"Evolution: staged candidate {candidate_id}")

    return candidate_id


def spawn_evolution(session_id: str) -> None:
    """Spawn evolution as a non-blocking subprocess.

    Called from spawn.py after a loop completes. Launches `scope evolve run`
    in the background so it doesn't block the caller.
    """
    project_id = get_project_identifier()
    subprocess.Popen(
        ["scope", "evolve", "run", "--session", session_id, "--project", project_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
