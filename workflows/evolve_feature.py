#!/usr/bin/env python3
"""Workflow: Implement F5 Skill Evolution feature.

Sequences scope spawn phases to build the evolution system.
Run with: python workflows/evolve_feature.py
"""

import subprocess
import sys


def spawn_and_wait(task: str, checker: str, phase_name: str, **kwargs) -> str:
    """Spawn a scope session and wait for it to complete."""
    cmd = [
        "scope", "spawn", task,
        "--checker", checker,
        "--id", phase_name,
        "--max-iterations", str(kwargs.get("max_iterations", 3)),
    ]
    if kwargs.get("dangerously_skip_permissions"):
        cmd.append("--dangerously-skip-permissions")

    print(f"\n{'='*60}")
    print(f"PHASE: {phase_name}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd, capture_output=True, text=True)
    session_id = result.stdout.strip().split("\n")[0]  # first line is session ID
    if result.returncode != 0:
        print(f"FAILED phase {phase_name}: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Phase {phase_name} completed (session {session_id})")
    return session_id


# ============================================================================
# CHECKER SCRIPTS
# ============================================================================
# Each phase uses a bash checker script that combines mechanical validation
# (ruff, imports, function existence) with structural quality checks
# (no dead code, no stubs, no placeholder logic, correct signatures).

PHASE1_CHECKER = r"""
set -e
cd /Users/ada/fun/scope

# 1. Lint — no warnings allowed
ruff check src/scope/core/evolve.py

# 2. Import — module must load cleanly
python -c "import scope.core.evolve"

# 3. Every specified function must exist with correct signatures
python -c "
import inspect
from scope.core.evolve import (
    get_evolution_dir,
    get_active_version,
    get_active_skill_path,
    get_active_skill,
    init_baseline,
    list_versions,
    list_staged,
    append_history,
    compute_diff,
    stage_candidate,
    apply_candidate,
    reject_candidate,
    rollback,
    pareto_select,
    collect_loop_files,
    build_critique_prompt,
    run_critique,
    build_mutation_prompt,
    run_mutation,
    run_evolution,
    spawn_evolution,
)

# Verify return type annotations exist on key functions
sig = inspect.signature(get_evolution_dir)
assert sig.return_annotation is not inspect.Parameter.empty, 'get_evolution_dir missing return annotation'

sig = inspect.signature(get_active_version)
assert sig.return_annotation is not inspect.Parameter.empty, 'get_active_version missing return annotation'

sig = inspect.signature(collect_loop_files)
params = list(sig.parameters.keys())
assert 'session_id' in params, 'collect_loop_files missing session_id param'

sig = inspect.signature(stage_candidate)
params = list(sig.parameters.keys())
assert 'session_id' in params, 'stage_candidate missing session_id'
assert 'project_id' in params, 'stage_candidate missing project_id'
assert 'critique' in params, 'stage_candidate missing critique'
assert 'proposed_skill' in params, 'stage_candidate missing proposed_skill'

sig = inspect.signature(pareto_select)
params = list(sig.parameters.keys())
assert 'candidates' in params, 'pareto_select missing candidates param'

sig = inspect.signature(run_evolution)
params = list(sig.parameters.keys())
assert 'session_id' in params, 'run_evolution missing session_id'
assert 'project_id' in params, 'run_evolution missing project_id'

sig = inspect.signature(spawn_evolution)
params = list(sig.parameters.keys())
assert 'session_id' in params, 'spawn_evolution missing session_id'

print('All 21 functions present with correct signatures')
"

# 4. No dead code: every defined function must be in the public API list above
python -c "
import ast, sys

with open('src/scope/core/evolve.py') as f:
    tree = ast.parse(f.read())

EXPECTED = {
    'get_evolution_dir', 'get_active_version', 'get_active_skill_path',
    'get_active_skill', 'init_baseline', 'list_versions', 'list_staged',
    'append_history', 'compute_diff', 'stage_candidate', 'apply_candidate',
    'reject_candidate', 'rollback', 'pareto_select', 'collect_loop_files',
    'build_critique_prompt', 'run_critique', 'build_mutation_prompt',
    'run_mutation', 'run_evolution', 'spawn_evolution',
}

defined = set()
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        defined.add(node.name)

# Allow private helpers prefixed with _
unexpected = {f for f in defined if not f.startswith('_')} - EXPECTED
if unexpected:
    print(f'FAIL: unexpected public functions: {unexpected}', file=sys.stderr)
    sys.exit(1)

# Check that no function body is just 'pass' or 'raise NotImplementedError'
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        body = node.body
        # Skip if only docstring + pass/raise
        stmts = [s for s in body if not isinstance(s, ast.Expr) or not isinstance(s.value, (ast.Constant, ast.Str))]
        if len(stmts) == 1:
            s = stmts[0]
            if isinstance(s, ast.Pass):
                print(f'FAIL: {node.name} is a stub (pass)', file=sys.stderr)
                sys.exit(1)
            if isinstance(s, ast.Raise) and isinstance(s.exc, ast.Call):
                if hasattr(s.exc.func, 'id') and s.exc.func.id == 'NotImplementedError':
                    print(f'FAIL: {node.name} is a stub (NotImplementedError)', file=sys.stderr)
                    sys.exit(1)
        if len(stmts) == 0:
            print(f'FAIL: {node.name} is empty (only docstring)', file=sys.stderr)
            sys.exit(1)

print('No dead code, no stubs, no empty functions')
"

# 5. No unused imports
python -c "
import ast, sys

with open('src/scope/core/evolve.py') as f:
    source = f.read()
    tree = ast.parse(source)

imports = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name
            imports.append(name)
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            name = alias.asname or alias.name
            imports.append(name)

# Check each imported name is used in the source (crude but effective)
for name in imports:
    # Count occurrences beyond the import line itself
    parts = name.split('.')
    check_name = parts[-1]  # for 'foo.bar', check 'bar'
    count = source.count(check_name)
    if count <= 1:
        print(f'WARNING: {check_name} imported but may be unused (only {count} occurrence)', file=sys.stderr)
        # Don't fail on this — ruff already catches it, this is advisory

print('Import usage check complete')
"

# 6. Verify orjson is used (not json stdlib) for JSON operations
python -c "
with open('src/scope/core/evolve.py') as f:
    source = f.read()

if 'import json' in source and 'import orjson' not in source:
    print('FAIL: must use orjson, not stdlib json', file=__import__('sys').stderr)
    __import__('sys').exit(1)

print('Uses orjson correctly')
"

echo "PHASE 1 CHECKER: ALL PASSED"
"""

PHASE2_CHECKER = r"""
set -e
cd /Users/ada/fun/scope

# 1. Lint
ruff check src/scope/commands/evolve.py

# 2. Import
python -c "import scope.commands.evolve"

# 3. Verify all Click commands exist and are properly structured
python -c "
import click
from scope.commands.evolve import evolve

assert isinstance(evolve, click.MultiCommand) or isinstance(evolve, click.Group), \
    'evolve must be a click.Group'

# Get all registered subcommands
ctx = click.Context(evolve)
commands = evolve.list_commands(ctx)
print(f'Found commands: {commands}')

REQUIRED = {'run', 'status', 'diff', 'apply', 'reject', 'rollback', 'history', 'versions'}
missing = REQUIRED - set(commands)
if missing:
    print(f'FAIL: missing subcommands: {missing}')
    __import__('sys').exit(1)

extra = set(commands) - REQUIRED
if extra:
    print(f'FAIL: unexpected subcommands: {extra}')
    __import__('sys').exit(1)

# Verify 'run' has --session option
run_cmd = evolve.get_command(ctx, 'run')
param_names = [p.name for p in run_cmd.params]
assert 'session' in param_names, 'run command missing --session option'

# Verify 'apply' takes candidate_id argument
apply_cmd = evolve.get_command(ctx, 'apply')
param_names = [p.name for p in apply_cmd.params]
assert 'candidate_id' in param_names, 'apply missing candidate_id param'

# Verify 'reject' takes candidate_id argument
reject_cmd = evolve.get_command(ctx, 'reject')
param_names = [p.name for p in reject_cmd.params]
assert 'candidate_id' in param_names, 'reject missing candidate_id param'

# Verify 'rollback' takes version_id argument
rollback_cmd = evolve.get_command(ctx, 'rollback')
param_names = [p.name for p in rollback_cmd.params]
assert 'version_id' in param_names, 'rollback missing version_id param'

# Verify 'diff' has optional candidate_id
diff_cmd = evolve.get_command(ctx, 'diff')
param_names = [p.name for p in diff_cmd.params]
assert 'candidate_id' in param_names, 'diff missing candidate_id param'

print('All 8 subcommands present with correct parameters')
"

# 4. No stubs or empty command bodies
python -c "
import ast, sys

with open('src/scope/commands/evolve.py') as f:
    tree = ast.parse(f.read())

for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        body = node.body
        stmts = [s for s in body if not isinstance(s, ast.Expr) or not isinstance(s.value, (ast.Constant, ast.Str))]
        if len(stmts) == 1 and isinstance(stmts[0], ast.Pass):
            # Allow the group function itself to have pass
            if node.name == 'evolve':
                continue
            print(f'FAIL: {node.name} is a stub (pass)', file=sys.stderr)
            sys.exit(1)
        if len(stmts) == 0 and node.name != 'evolve':
            print(f'FAIL: {node.name} is empty', file=sys.stderr)
            sys.exit(1)

print('No stub commands')
"

# 5. Verify imports are from scope.core.evolve (not reimplementing logic)
python -c "
with open('src/scope/commands/evolve.py') as f:
    source = f.read()

if 'from scope.core.evolve import' not in source:
    print('FAIL: must import from scope.core.evolve', file=__import__('sys').stderr)
    __import__('sys').exit(1)

print('Correctly delegates to core module')
"

echo "PHASE 2 CHECKER: ALL PASSED"
"""

PHASE3_CHECKER = r"""
set -e
cd /Users/ada/fun/scope

# 1. Lint all modified files
ruff check src/scope/commands/spawn.py src/scope/cli.py src/scope/hooks/install.py src/scope/tui/widgets/session_tree.py

# 2. Import chain works
python -c "from scope.commands.evolve import evolve; from scope.cli import main; print('import ok')"

# 3. Verify evolve command is registered in CLI
python -c "
import click
from scope.cli import main

ctx = click.Context(main)
commands = main.list_commands(ctx)
assert 'evolve' in commands, f'evolve not registered in CLI. Found: {commands}'
print(f'evolve registered in CLI (commands: {commands})')
"

# 4. Verify spawn.py has evolution trigger
python -c "
with open('src/scope/commands/spawn.py') as f:
    source = f.read()

assert 'SCOPE_EVOLUTION_ENABLED' in source, 'spawn.py missing SCOPE_EVOLUTION_ENABLED check'
assert 'spawn_evolution' in source, 'spawn.py missing spawn_evolution call'

# Verify the trigger is AFTER run_loop, not before
loop_pos = source.index('run_loop(')
evolve_pos = source.index('spawn_evolution')
assert evolve_pos > loop_pos, 'spawn_evolution must come after run_loop'

print('spawn.py evolution trigger correctly placed')
"

# 5. Verify install.py has baseline init
python -c "
with open('src/scope/hooks/install.py') as f:
    source = f.read()

assert 'init_baseline' in source, 'install.py missing init_baseline call'

# Verify it's inside ensure_setup (after line 487ish)
lines = source.split('\n')
in_ensure_setup = False
found = False
for line in lines:
    if 'def ensure_setup' in line:
        in_ensure_setup = True
    if in_ensure_setup and 'init_baseline' in line:
        found = True
        break

assert found, 'init_baseline not inside ensure_setup function'
print('install.py baseline init correctly placed')
"

# 6. Verify session_tree.py has evolve mode detection
python -c "
with open('src/scope/tui/widgets/session_tree.py') as f:
    source = f.read()

assert 'evolve_target' in source, 'session_tree.py missing evolve_target marker check'
assert 'evolve' in source, 'session_tree.py missing evolve mode'
print('session_tree.py evolve detection present')
"

# 7. Verify NO unrelated changes — check file sizes haven't ballooned
python -c "
import os, sys

LIMITS = {
    'src/scope/commands/spawn.py': 420,     # was 356, allow ~60 extra lines
    'src/scope/cli.py': 160,                # was 140, allow ~20 extra lines
    'src/scope/hooks/install.py': 600,      # was 571, allow ~30 extra lines
    'src/scope/tui/widgets/session_tree.py': 480,  # was 444, allow ~36 extra lines
}

for path, limit in LIMITS.items():
    lines = len(open(path).readlines())
    if lines > limit:
        print(f'FAIL: {path} has {lines} lines (limit {limit}) — too many changes', file=sys.stderr)
        sys.exit(1)
    print(f'{path}: {lines} lines (limit {limit}) OK')
"

echo "PHASE 3 CHECKER: ALL PASSED"
"""

PHASE4_CHECKER = r"""
set -e
cd /Users/ada/fun/scope

# 1. Lint
ruff check tests/test_evolve.py

# 2. Run all tests — must pass
python -m pytest tests/test_evolve.py -x -v --tb=short 2>&1

# 3. Verify minimum test count — at least 15 tests
python -c "
import ast, sys

with open('tests/test_evolve.py') as f:
    tree = ast.parse(f.read())

tests = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
print(f'Found {len(tests)} tests: {tests}')
if len(tests) < 15:
    print(f'FAIL: need at least 15 tests, found {len(tests)}', file=sys.stderr)
    sys.exit(1)
"

# 4. Verify key test categories are covered
python -c "
import ast, sys

with open('tests/test_evolve.py') as f:
    tree = ast.parse(f.read())

tests = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
test_str = ' '.join(tests)

categories = {
    'baseline/init': any(w in test_str for w in ['baseline', 'init']),
    'active_version': 'active' in test_str,
    'stage': 'stage' in test_str,
    'apply': 'apply' in test_str,
    'reject': 'reject' in test_str,
    'rollback': 'rollback' in test_str,
    'pareto': 'pareto' in test_str,
    'diff': 'diff' in test_str,
    'collect_loop': any(w in test_str for w in ['collect', 'loop_files']),
    'critique_prompt': any(w in test_str for w in ['critique', 'prompt']),
}

missing = [cat for cat, found in categories.items() if not found]
if missing:
    print(f'FAIL: missing test categories: {missing}', file=sys.stderr)
    sys.exit(1)

print(f'All {len(categories)} test categories covered')
"

# 5. No tests use real subprocess / scope spawn (must be mocked)
python -c "
with open('tests/test_evolve.py') as f:
    source = f.read()

# Should use monkeypatch/mock, not actually call scope spawn
if 'subprocess.run([\"scope\"' in source and 'monkeypatch' not in source and 'mock' not in source.lower():
    print('FAIL: tests must mock subprocess calls, not run real scope spawn')
    __import__('sys').exit(1)

print('Tests properly mock external calls')
"

echo "PHASE 4 CHECKER: ALL PASSED"
"""

# ============================================================================
# TASK PROMPTS
# ============================================================================

# ---------------------------------------------------------------------------
# Phase 1: Create src/scope/core/evolve.py — ALL core logic
# ---------------------------------------------------------------------------
PHASE1_TASK = r"""Create the file src/scope/core/evolve.py with the complete evolution system for scope skill improvement.

## Context

This is the scope project at /Users/ada/fun/scope. It's a CLI orchestration tool for Claude Code subagents.
Key existing files you should read first:
- src/scope/core/state.py — session state management patterns (use _get_scope_dir, ensure_scope_dir patterns)
- src/scope/core/project.py — get_global_scope_base(), get_project_identifier()
- src/scope/core/loop.py — LoopResult dataclass, run_loop(), loop_state.json format
- src/scope/hooks/install.py — SCOPE_SKILL_CONTENT (the skill text), install_scope_skill(), get_claude_skills_dir()

## Storage Layout

All evolution data lives under ~/.scope/evolution/ (global, since the scope skill is global).

```
~/.scope/evolution/
  versions/
    v0/
      skill.md              # Baseline snapshot of SCOPE_SKILL_CONTENT
      meta.json             # { "created_at", "source": "baseline" }
    v1/
      skill.md              # First accepted revision
      meta.json             # { "created_at", "source": "evolution", "parent": "v0", "scores": {...} }
  staged/
    c-{hash12}/             # One dir per candidate (hash of proposed skill text)
      skill.md              # Candidate skill text
      critique.json         # Structured critique
      diff.patch            # Unified diff vs current active version
      meta.json             # { "created_at", "loop_session_id", "project", "scores", "parent_version" }
  active                    # Plain text: current version name, e.g. "v0"
  history.jsonl             # Append-only log of events
```

## Functions to implement

Every function must have a real implementation — no stubs, no pass, no NotImplementedError.

### Storage utilities (no LLM calls):
- `get_evolution_dir() -> Path` — returns ~/.scope/evolution/, creates if needed
- `get_active_version() -> str` — reads `active` file, returns e.g. "v0"
- `get_active_skill_path() -> Path` — returns path to active version's skill.md
- `get_active_skill() -> str` — reads active version's skill.md content
- `init_baseline()` — snapshot SCOPE_SKILL_CONTENT as v0 if versions/v0 doesn't exist. Import SCOPE_SKILL_CONTENT from scope.hooks.install. Write skill.md and meta.json (with created_at ISO timestamp and source "baseline"). Write "v0" to active file.
- `list_versions() -> list[dict]` — metadata for all versions (read each meta.json, add "version" key)
- `list_staged() -> list[dict]` — metadata for all staged candidates (read each meta.json, add "candidate_id" key)
- `append_history(event: dict)` — append JSON line to history.jsonl (add timestamp if not present)

### File operations:
- `compute_diff(current: str, proposed: str) -> str` — use difflib.unified_diff, return as string
- `stage_candidate(session_id: str, project_id: str, critique: dict, proposed_skill: str) -> str` — hash proposed_skill (hashlib.sha256, first 12 chars) to make candidate ID "c-{hash12}". Write staged/c-{hash}/skill.md, critique.json, diff.patch (vs active skill), meta.json. Return candidate ID. Append history event.
- `apply_candidate(candidate_id: str)` — read staged candidate's skill.md and critique scores. Determine next version number (v0, v1, v2...). Create versions/vN/ with skill.md and meta.json (source="evolution", parent=active version, scores from critique). Update active file. Write skill to ~/.claude/skills/scope/SKILL.md (use get_claude_skills_dir from hooks.install). Remove from staged. Append history event.
- `reject_candidate(candidate_id: str)` — remove staged dir (shutil.rmtree). Append history event.
- `rollback(version_id: str)` — verify version exists. Set active file. Write skill to ~/.claude/skills/scope/SKILL.md. Append history event.

### Pareto selection:
- `pareto_select(candidates: list[dict]) -> list[dict]` — each candidate has "scores" dict with keys "pattern_adherence", "instantiation_quality", "enforcement_quality". A candidate is Pareto-dominated if another candidate is >= on all axes and > on at least one. Return non-dominated candidates.

### Subagent functions (these call scope spawn via subprocess):
- `collect_loop_files(session_id: str) -> dict` — load loop_state.json for the session. Collect file paths: loop_state path, active skill path, task file, result file, and for each history entry collect doer trajectory (trajectory.jsonl) and checker trajectory if checker_session exists. Return dict: {"loop_state": Path, "skill": Path, "task": Path, "result": Path, "trajectories": [{"session_id": str, "role": "doer"|"checker", "iteration": int, "trajectory": Path}]}
  Use ensure_scope_dir() from state module to get project scope dir. Session dirs are at scope_dir/sessions/{id}/.

- `build_critique_prompt(loop_files: dict) -> str` — build task prompt for critique subagent. List all file paths for the agent to read. Include 3-axis critique instructions (pattern_adherence, instantiation_quality, enforcement_quality) each scored 0.0-1.0 with findings list and suggestions list. Request JSON output with the critique structure.

- `run_critique(session_id: str) -> dict` — call collect_loop_files, build_critique_prompt, then run subprocess: scope spawn "{prompt}" --checker "agent: Validate the output contains valid JSON critique with axes scores. ACCEPT if valid JSON with all 3 axes. RETRY otherwise." --max-iterations 2. Wait for completion, read the result file, parse JSON from it (find JSON in code block or raw). Return critique dict.

- `build_mutation_prompt(critique: dict, skill_path: Path) -> str` — build prompt that says: read the skill at {path}, apply the critique suggestions (include them), output the COMPLETE rewritten skill text. Make MINIMAL targeted changes. Output the full skill text in a markdown code block.

- `run_mutation(critique: dict) -> str` — call build_mutation_prompt, spawn subagent, wait, read result, extract skill text from code block. Return proposed skill text.

- `run_evolution(session_id: str, project_id: str)` — orchestrate: collect_loop_files → run_critique → run_mutation → stage_candidate. Print status at each step. Return candidate_id.

- `spawn_evolution(session_id: str)` — called from spawn.py after run_loop. Runs run_evolution in a subprocess (non-blocking). Uses the current project_id from get_project_identifier(). Spawns as: subprocess.Popen(["scope", "evolve", "run", "--session", session_id], ...) so it's non-blocking.

## Important patterns
- Use `orjson` for JSON (the project uses it everywhere — `orjson.loads`, `orjson.dumps`)
- Use `from pathlib import Path`
- Use `from datetime import datetime, timezone` for timestamps (datetime.now(timezone.utc).isoformat())
- Import SCOPE_SKILL_CONTENT from scope.hooks.install
- Import get_claude_skills_dir from scope.hooks.install
- Import ensure_scope_dir, load_loop_state from scope.core.state
- Import get_project_identifier from scope.core.project
- For subprocess calls to scope spawn, use subprocess.run with capture_output=True, text=True
- Use hashlib.sha256 for hashing
- Use shutil.rmtree for directory removal
- Use difflib.unified_diff for diffs
- Do NOT leave any unused imports, dead code, or stub functions

Write ONLY the file src/scope/core/evolve.py. Do not modify any other files.
"""

# ---------------------------------------------------------------------------
# Phase 2: Create src/scope/commands/evolve.py — CLI commands
# ---------------------------------------------------------------------------
PHASE2_TASK = r"""Create the file src/scope/commands/evolve.py with Click CLI commands for the scope evolution system.

## Context

Read these files first:
- src/scope/core/evolve.py — the core evolution module you're building CLI for (just created)
- src/scope/commands/spawn.py — example of how commands are structured in this project
- src/scope/cli.py — how commands are registered

## Commands to implement

Use Click with a group command `evolve` containing subcommands:

```python
@click.group()
def evolve():
    # docstring: Skill evolution - critique, mutate, and improve the scope skill.
    pass
```

Subcommands (all 8 required, no stubs):

### scope evolve run --session <id>
Run evolution against a completed loop session. Calls run_evolution(session_id, project_id).
Print the candidate_id on success.

### scope evolve status
Show all staged candidates. Highlight Pareto front candidates.
Call list_staged(), then pareto_select() on those with scores.
Print a table: candidate_id, created_at, loop_session_id, overall score, pareto (yes/no).

### scope evolve diff [candidate_id]
Show unified diff for a candidate. If no ID given, pick the best Pareto candidate (highest overall score).
Read diff.patch from the staged candidate dir. Print it.

### scope evolve apply <candidate_id>
Apply a staged candidate as new version. Calls apply_candidate(candidate_id).
Print confirmation with new version name.

### scope evolve reject <candidate_id>
Reject and remove a staged candidate. Calls reject_candidate(candidate_id).
Print confirmation.

### scope evolve rollback <version_id>
Rollback to a specific version. Calls rollback(version_id).
Print confirmation.

### scope evolve history
Show evolution event log. Read history.jsonl, print each event (timestamp, type, details).

### scope evolve versions
List all skill versions. Calls list_versions().
Print table: version, created_at, source, parent.
Mark the active version with *.

## Patterns
- Use click.echo() for output
- Use click.style() for coloring (e.g. Pareto candidates in green)
- Import functions from scope.core.evolve — delegate ALL logic there, do not reimplement
- Import get_project_identifier from scope.core.project
- Handle errors with try/except and click.echo(..., err=True) + raise SystemExit(1)
- Follow the same style as other command files in commands/
- Every subcommand must have a real implementation — no pass, no NotImplementedError, no TODO

Write ONLY src/scope/commands/evolve.py.
"""

# ---------------------------------------------------------------------------
# Phase 3: Modify existing files — spawn.py, cli.py, install.py, session_tree.py
# ---------------------------------------------------------------------------
PHASE3_TASK = r"""Modify 4 existing files to integrate the evolution system into scope.

Read ALL of these files first before making any changes:
- src/scope/commands/spawn.py
- src/scope/cli.py
- src/scope/hooks/install.py
- src/scope/tui/widgets/session_tree.py
- src/scope/core/evolve.py (the new file, for reference)
- src/scope/commands/evolve.py (the new file, for reference)

## Changes required — make ONLY these changes, nothing else:

### 1. src/scope/commands/spawn.py
After the run_loop() call (around line 348-355), add evolution trigger:

After this existing code:
```python
    if not skip_loop:
        run_loop(
            session_id=session_id,
            prompt=prompt,
            checker=checker,
            max_iterations=max_iterations,
            checker_model=checker_model or model,
            dangerously_skip_permissions=dangerously_skip_permissions,
        )
```

Add:
```python
        # Spawn evolution subagent (opt-in via env var)
        if os.environ.get("SCOPE_EVOLUTION_ENABLED"):
            from scope.core.evolve import spawn_evolution
            spawn_evolution(session_id)
```

Note: `os` is already imported. The spawn_evolution call should be inside the `if not skip_loop:` block, after run_loop returns.

### 2. src/scope/cli.py
Add import and register the evolve command. Add this import near the other command imports:
```python
from scope.commands.evolve import evolve
```

And add this registration near the other add_command calls:
```python
main.add_command(evolve)
```

### 3. src/scope/hooks/install.py
In the `ensure_setup()` function (starts around line 487), add a call to init_baseline() for evolution.
Add it AFTER the skill installation block (after line 524) and BEFORE the tmux hooks block.

Add:
```python
    # Initialize evolution baseline (snapshot v0 of skill)
    try:
        from scope.core.evolve import init_baseline
        init_baseline()
    except Exception as e:
        if not quiet:
            print(f"Warning: Failed to init evolution baseline: {e}", file=sys.stderr)
```

### 4. src/scope/tui/widgets/session_tree.py
In `_build_tree()`, add detection of evolution sessions. An evolution session has a file called `evolve_target` in its session directory. When building tree nodes, check for this file and set mode="evolve" if found.

Find where normal (non-loop) sessions create TreeNode objects and add a check:
```python
# Check if this is an evolution session
evolve_marker = session_dir / "evolve_target"
if evolve_marker.exists():
    mode = "evolve"
```

You'll need to construct the session_dir path. Look at how the existing code accesses session directories — it uses the session objects. The session dir path follows the pattern from state.py: scope_dir/sessions/{session.id}/

## CRITICAL RULES
- Make MINIMAL changes. Do not refactor, reorganize, or "improve" existing code.
- Do not add comments to code you didn't write.
- Do not remove or modify any existing functionality.
- Do not add unused imports.
- Do not leave any dead code behind.
- Only add what's specified above — nothing more.
"""

# ---------------------------------------------------------------------------
# Phase 4: Create tests/test_evolve.py
# ---------------------------------------------------------------------------
PHASE4_TASK = r"""Create the file tests/test_evolve.py with comprehensive tests for the evolution system.

## Context

Read these files first:
- src/scope/core/evolve.py — the module under test
- tests/test_loop.py — example test patterns used in this project
- tests/test_state.py — another test example

## Tests to write

Use pytest. Use tmp_path fixture for filesystem tests. Use monkeypatch to mock subprocess calls and imports.
ALL tests must actually pass. Do NOT write tests that rely on unimplemented features or real subprocess calls.

### Storage utility tests:
1. test_get_evolution_dir_creates — verify get_evolution_dir() creates ~/.scope/evolution/ and returns it. Use monkeypatch to override Path.home().
2. test_init_baseline_creates_v0 — call init_baseline() with a tmp evolution dir. Verify versions/v0/skill.md contains SCOPE_SKILL_CONTENT, meta.json has source="baseline", active file contains "v0".
3. test_init_baseline_idempotent — call init_baseline() twice, verify v0 unchanged.
4. test_get_active_version — after init_baseline, verify get_active_version() returns "v0".
5. test_get_active_skill — after init_baseline, verify get_active_skill() returns the skill content.
6. test_list_versions — after init_baseline, verify list_versions() returns one entry with version="v0".

### File operation tests:
7. test_compute_diff — compute_diff("hello\n", "hello\nworld\n") produces a diff containing "+world".
8. test_stage_candidate — after init_baseline, stage a candidate with mock critique and proposed skill. Verify staged dir exists with skill.md, critique.json, diff.patch, meta.json.
9. test_apply_candidate — stage then apply. Verify new version v1 created, active is "v1", staged dir removed. Verify skill.md written to claude skills dir (mock get_claude_skills_dir).
10. test_reject_candidate — stage then reject. Verify staged dir removed, history event logged.
11. test_rollback — apply a candidate (creating v1), then rollback to v0. Verify active is "v0".

### Pareto selection tests:
12. test_pareto_select_single — single candidate is always on Pareto front.
13. test_pareto_select_dominated — candidate A dominates B (all scores >=, at least one >). Only A returned.
14. test_pareto_select_nondominated — A better on axis 1, B better on axis 2. Both returned.
15. test_pareto_select_equal — equal scores, both returned.

### Loop file collection tests:
16. test_collect_loop_files — create a mock session dir with loop_state.json, task, result, trajectory.jsonl files. Verify collect_loop_files returns correct paths.

### Prompt building tests:
17. test_build_critique_prompt — verify prompt includes file paths and 3-axis instructions.

### Integration test:
18. test_run_evolution_mocked — monkeypatch run_critique to return a mock critique dict, monkeypatch run_mutation to return proposed skill text. Call run_evolution. Verify a staged candidate is created.

## Important patterns for tests
- Use tmp_path for all file operations
- Monkeypatch `scope.core.evolve.get_evolution_dir` to return a tmp_path subdir for isolation
- For apply_candidate/rollback tests, also monkeypatch the skill output dir (the function that resolves ~/.claude/skills/scope/) so it writes to tmp
- Use `orjson` for JSON assertions (the project uses orjson)
- For collect_loop_files, monkeypatch `ensure_scope_dir` to return the tmp dir, and create the expected file structure manually
- Mock ALL subprocess/spawn calls — no real scope spawn in tests
- Every test must be self-contained and actually pass when run

Write ONLY tests/test_evolve.py.
"""


# ---------------------------------------------------------------------------
# Run phases sequentially
# ---------------------------------------------------------------------------
def main():
    phases = [
        ("evolve-core", PHASE1_TASK, PHASE1_CHECKER, 3),
        ("evolve-cli", PHASE2_TASK, PHASE2_CHECKER, 3),
        ("evolve-integrate", PHASE3_TASK, PHASE3_CHECKER, 3),
        ("evolve-tests", PHASE4_TASK, PHASE4_CHECKER, 5),
    ]

    results = {}
    for phase_name, task, checker, max_iter in phases:
        print(f"\n{'='*60}")
        print(f"STARTING PHASE: {phase_name}")
        print(f"{'='*60}\n")

        session_id = spawn_and_wait(
            task, checker, phase_name, max_iterations=max_iter
        )
        results[phase_name] = session_id

    print(f"\n{'='*60}")
    print("ALL PHASES COMPLETE")
    print(f"{'='*60}")
    for name, sid in results.items():
        print(f"  {name}: session {sid}")


if __name__ == "__main__":
    main()
