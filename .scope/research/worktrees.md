# Git Worktree Research for Scope Integration

This document covers comprehensive research on git worktrees for integration into Scope's multi-agent orchestration system.

## 1. Git Worktree API

### Core Commands

| Command | Description |
|---------|-------------|
| `git worktree add <path> [<commit-ish>]` | Create a new worktree at path, checking out commit/branch |
| `git worktree list` | List all worktrees with their details |
| `git worktree remove <worktree>` | Remove a worktree (must be clean) |
| `git worktree prune` | Remove stale administrative files for deleted worktrees |
| `git worktree lock <worktree>` | Lock worktree to prevent automatic pruning |
| `git worktree unlock <worktree>` | Unlock a previously locked worktree |
| `git worktree move <worktree> <new-path>` | Move worktree to new location |
| `git worktree repair [<path>...]` | Repair corrupted worktree admin files |

### Flags for `git worktree add`

| Flag | Description |
|------|-------------|
| `-b <branch>` | Create new branch (fails if exists) |
| `-B <branch>` | Create new branch (resets if exists) |
| `-d`, `--detach` | Create worktree in detached HEAD state |
| `--orphan` | Create new unborn branch (empty index) |
| `--no-checkout` | Skip checkout (useful for sparse-checkout setup) |
| `--track` | Mark branch as tracking upstream |
| `--no-track` | Don't set up tracking |
| `--guess-remote` | Use remote-tracking branch if unique match |
| `--lock` | Keep worktree locked after creation |
| `--reason <string>` | Specify lock reason (with `--lock`) |
| `--relative-paths` | Use relative paths for internal links |
| `-f`, `--force` | Override safeguards (branch checked out elsewhere, etc.) |
| `-f -f` | Double force: for locked/missing paths |
| `-q`, `--quiet` | Suppress feedback messages |

### Flags for `git worktree list`

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Show additional info (lock reasons, prunable status) |
| `--porcelain` | Machine-readable format |
| `-z` | NUL-terminate lines (with `--porcelain`) |

### Flags for `git worktree prune`

| Flag | Description |
|------|-------------|
| `-n`, `--dry-run` | Report what would be removed without removing |
| `-v`, `--verbose` | Report all removals |
| `--expire <time>` | Only prune worktrees older than specified time |

### Flags for `git worktree remove`

| Flag | Description |
|------|-------------|
| `-f`, `--force` | Remove unclean worktrees or those with submodules |
| `-f -f` | Remove locked worktrees |

### Flags for `git worktree move`

| Flag | Description |
|------|-------------|
| `-f`, `--force` | Allow moving to existing paths |
| `-f -f` | Move locked worktrees |

## 2. Edge Cases

### Detached HEAD
- Create with `-d` or `--detach` flag
- Useful for fuzzing, testing, or throwaway experiments
- No branch association means no risk of accidental commits to wrong branch
- Command: `git worktree add -d <path>` or `git worktree add -d <path> <commit>`

### Nested Repositories
- Worktrees inside other git repositories can cause confusion
- Git uses `.git` file (not directory) in linked worktrees to point to main repo
- Detection must distinguish between `.git` file vs directory

### Submodules Warning
**NOT RECOMMENDED**: Making multiple checkouts of a superproject with submodules.

Limitations:
- Linked worktrees containing submodules cannot be moved
- Support for submodules is incomplete and experimental
- Submodules in worktrees default to detached HEAD state
- Different submodule branches in different worktrees can cause confusion
- Must use `--force` to remove worktrees with submodules

### Bare Repositories
- Bare repos can have linked worktrees
- `git worktree list` shows `(bare)` annotation for bare repos
- Bare repo serves as `$GIT_COMMON_DIR` for all linked worktrees

### Branch Already Checked Out Error
```
fatal: 'branch-name' is already checked out at '/path/to/other/worktree'
```
- By default, `add` refuses if branch is checked out elsewhere
- Override with `--force` flag
- This protection prevents concurrent edits to same branch

### Path Exists Error
```
fatal: '/path/to/worktree' already exists
```
- Cannot create worktree at existing path
- Override with `--force` if path is missing but metadata exists
- Use `--force --force` for locked missing paths

### Sparse Checkout
- Use `--no-checkout` to skip initial checkout
- Configure sparse-checkout patterns before running `git checkout`
- Useful for large monorepos where only partial checkout is needed

## 3. Detection Methods

### Comparing GIT_DIR vs GIT_COMMON_DIR

```bash
git_dir=$(git rev-parse --git-dir)
common_dir=$(git rev-parse --git-common-dir)

if [ "$git_dir" = "$common_dir" ]; then
    echo "Main worktree"
else
    echo "Linked worktree"
fi
```

**In main worktree:**
- `--git-dir` returns `/path/to/repo/.git`
- `--git-common-dir` returns `/path/to/repo/.git`
- Both are identical

**In linked worktree:**
- `--git-dir` returns `/path/to/repo/.git/worktrees/<name>`
- `--git-common-dir` returns `/path/to/repo/.git`
- Different paths indicate linked worktree

### .git File vs Directory Check

```bash
if [ -f ".git" ]; then
    echo "Linked worktree (.git is a file)"
    # Contents: gitdir: /path/to/main/.git/worktrees/<name>
elif [ -d ".git" ]; then
    echo "Main worktree or standalone repo (.git is a directory)"
fi
```

### Useful rev-parse Flags

| Flag | Description |
|------|-------------|
| `--git-dir` | Path to `.git` directory (worktree-specific in linked worktrees) |
| `--git-common-dir` | Path to shared `.git` directory |
| `--absolute-git-dir` | Absolute path to `.git` directory |
| `--show-toplevel` | Absolute path to worktree root |
| `--is-inside-work-tree` | Returns `true` or `false` |
| `--is-bare-repository` | Returns `true` or `false` |
| `--git-path <path>` | Resolves path using correct GIT_DIR/GIT_COMMON_DIR |

### Python Implementation

```python
import subprocess

def detect_worktree_status():
    """Detect if current directory is a main or linked worktree."""
    git_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-dir"],
        text=True
    ).strip()

    common_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"],
        text=True
    ).strip()

    # Normalize paths for comparison
    git_dir = os.path.realpath(git_dir)
    common_dir = os.path.realpath(common_dir)

    return {
        "is_linked_worktree": git_dir != common_dir,
        "git_dir": git_dir,
        "common_dir": common_dir,
        "worktree_name": os.path.basename(git_dir) if git_dir != common_dir else None
    }
```

## 4. Branch Naming

### Proposed Pattern: `scope/{session-id}/{task-slug}`

```
scope/abc123/fix-auth-bug
scope/def456/add-user-validation
scope/ghi789/refactor-database
```

**Components:**
- `scope/` - Namespace prefix identifying Scope-managed branches
- `{session-id}` - Unique session identifier (6-8 chars)
- `{task-slug}` - Slugified task description (lowercase, hyphens)

### Collision Handling with Numeric Suffixes

```python
def generate_branch_name(session_id: str, task_slug: str) -> str:
    """Generate unique branch name with collision handling."""
    base_name = f"scope/{session_id}/{task_slug}"

    # Check if branch exists
    existing = get_existing_branches_with_prefix(base_name)

    if not existing:
        return base_name

    # Find highest suffix and increment
    max_suffix = 0
    for branch in existing:
        if branch == base_name:
            max_suffix = max(max_suffix, 1)
        elif branch.startswith(f"{base_name}-"):
            try:
                suffix = int(branch.split("-")[-1])
                max_suffix = max(max_suffix, suffix + 1)
            except ValueError:
                continue

    return f"{base_name}-{max_suffix}" if max_suffix > 0 else base_name
```

**Example collision sequence:**
1. `scope/abc123/fix-auth` (first)
2. `scope/abc123/fix-auth-2` (collision)
3. `scope/abc123/fix-auth-3` (another collision)

### Slug Generation

```python
import re

def slugify(text: str, max_length: int = 50) -> str:
    """Convert task description to URL-safe slug."""
    # Lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower())
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    # Truncate to max length at word boundary
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit('-', 1)[0]
    return slug
```

## 5. Cleanup Semantics

### remove vs prune

| Operation | `git worktree remove` | `git worktree prune` |
|-----------|----------------------|---------------------|
| Purpose | Explicitly delete specific worktree | Clean up stale/orphaned metadata |
| Target | Named worktree path | All orphaned worktree entries |
| Requires | Worktree must exist (or use -f) | N/A - operates on metadata only |
| Clean check | Yes - fails if dirty | N/A |
| Branch deletion | No | No |

### Force Flag Behavior

| Flags | Behavior |
|-------|----------|
| (none) | Only clean worktrees, fails if dirty/locked |
| `-f` | Removes dirty worktrees (untracked files, modifications) |
| `-f -f` | Removes locked worktrees |

### Locked Worktree Handling

```bash
# Lock a worktree (prevents prune and accidental removal)
git worktree lock /path/to/worktree --reason "In use by Scope session abc123"

# Check lock status
git worktree list --verbose
# Output: /path/to/worktree  abcd123 [branch]
#         locked: In use by Scope session abc123

# Unlock before removal
git worktree unlock /path/to/worktree
git worktree remove /path/to/worktree

# Or force remove while locked
git worktree remove -f -f /path/to/worktree
```

### gc.worktreePruneExpire Configuration

```bash
# View current setting
git config gc.worktreePruneExpire

# Set grace period (default: immediate for stale worktrees)
git config gc.worktreePruneExpire "3.days.ago"

# Prune with custom expiry (overrides config)
git worktree prune --expire "1.week.ago"
```

### Scope Cleanup Strategy

```python
def cleanup_worktree(session_id: str, force: bool = False) -> None:
    """Clean up worktree for completed session."""
    worktree_path = get_worktree_path(session_id)
    branch_name = get_branch_name(session_id)

    # 1. Unlock if locked
    try:
        subprocess.run(["git", "worktree", "unlock", worktree_path], check=False)
    except:
        pass

    # 2. Remove worktree
    cmd = ["git", "worktree", "remove", worktree_path]
    if force:
        cmd.insert(3, "-f")
    subprocess.run(cmd, check=True)

    # 3. Optionally delete branch (if not merged)
    if should_delete_branch(branch_name):
        subprocess.run(["git", "branch", "-D", branch_name], check=True)

    # 4. Prune stale metadata
    subprocess.run(["git", "worktree", "prune"], check=True)
```

## 6. Scope Integration Points

### spawn.py Modifications

```python
# src/scope/spawn.py

def spawn_session(
    prompt: str,
    *,
    use_worktree: bool = False,
    worktree_base: str | None = None,
    inherit_worktree: bool = True,
) -> Session:
    """Spawn a new Scope session, optionally in a dedicated worktree."""

    session_id = generate_session_id()

    if use_worktree:
        # Create worktree for this session
        worktree_info = create_session_worktree(
            session_id=session_id,
            task_slug=slugify(prompt),
            base_path=worktree_base or os.environ.get("SCOPE_WORKTREE_BASE"),
        )
        working_dir = worktree_info.path
        env_additions = {
            "SCOPE_WORKTREE_PATH": worktree_info.path,
            "SCOPE_WORKTREE_BRANCH": worktree_info.branch,
            "SCOPE_PARENT_WORKTREE": os.getcwd(),
        }
    else:
        working_dir = os.getcwd()
        env_additions = {}

    # Spawn Claude Code in the working directory
    return spawn_claude_session(
        prompt=prompt,
        session_id=session_id,
        working_dir=working_dir,
        env=env_additions,
    )
```

### New worktree.py Module

```python
# src/scope/worktree.py

from dataclasses import dataclass
from pathlib import Path
import subprocess
import os

@dataclass
class WorktreeInfo:
    path: Path
    branch: str
    session_id: str
    is_detached: bool = False

def create_session_worktree(
    session_id: str,
    task_slug: str,
    base_path: str | None = None,
) -> WorktreeInfo:
    """Create a new worktree for a Scope session."""

    # Determine base path
    if base_path:
        worktree_base = Path(base_path)
    else:
        # Default: .scope/worktrees relative to repo root
        repo_root = get_repo_root()
        worktree_base = repo_root / ".scope" / "worktrees"

    worktree_base.mkdir(parents=True, exist_ok=True)

    # Generate branch name
    branch_name = generate_branch_name(session_id, task_slug)

    # Generate worktree path
    worktree_path = worktree_base / session_id

    # Create worktree with new branch
    subprocess.run([
        "git", "worktree", "add",
        "-b", branch_name,
        "--lock",
        "--reason", f"Scope session {session_id}",
        str(worktree_path),
    ], check=True)

    return WorktreeInfo(
        path=worktree_path,
        branch=branch_name,
        session_id=session_id,
    )

def remove_session_worktree(session_id: str, force: bool = False) -> None:
    """Remove worktree for completed session."""
    worktree_path = get_worktree_path(session_id)

    # Unlock first
    subprocess.run(["git", "worktree", "unlock", str(worktree_path)], check=False)

    # Remove worktree
    cmd = ["git", "worktree", "remove"]
    if force:
        cmd.append("-f")
    cmd.append(str(worktree_path))
    subprocess.run(cmd, check=True)

def list_session_worktrees() -> list[WorktreeInfo]:
    """List all Scope-managed worktrees."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )

    worktrees = []
    current = {}

    for line in result.stdout.split("\n"):
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[9:]}
        elif line.startswith("branch "):
            branch = line[7:]
            if branch.startswith("refs/heads/scope/"):
                current["branch"] = branch[11:]  # Remove refs/heads/
                current["session_id"] = branch.split("/")[2]
        elif line == "detached":
            current["is_detached"] = True

    if current and "session_id" in current:
        worktrees.append(current)

    return [WorktreeInfo(**w) for w in worktrees if "session_id" in w]

def is_in_worktree() -> bool:
    """Check if current directory is a linked worktree."""
    git_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-dir"],
        text=True,
    ).strip()
    common_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"],
        text=True,
    ).strip()
    return os.path.realpath(git_dir) != os.path.realpath(common_dir)

def get_repo_root() -> Path:
    """Get repository root (works from any worktree)."""
    common_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"],
        text=True,
    ).strip()
    # common_dir is /path/to/repo/.git, we want /path/to/repo
    return Path(common_dir).parent
```

### Session State Additions

```python
# Additions to session state dataclass

@dataclass
class SessionState:
    session_id: str
    prompt: str
    status: str
    # ... existing fields ...

    # New worktree fields
    worktree_path: Path | None = None
    worktree_branch: str | None = None
    parent_worktree: Path | None = None

    def is_in_worktree(self) -> bool:
        return self.worktree_path is not None
```

## 7. Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SCOPE_WORKTREE_BASE` | Base directory for creating worktrees | `/path/to/repo/.scope/worktrees` |
| `SCOPE_USE_WORKTREE` | Enable worktree mode for spawned sessions | `true`, `false`, `auto` |
| `SCOPE_WORKTREE_PATH` | Path to current session's worktree | `/path/to/repo/.scope/worktrees/abc123` |
| `SCOPE_WORKTREE_BRANCH` | Branch name for current worktree | `scope/abc123/fix-auth-bug` |
| `SCOPE_PARENT_WORKTREE` | Path to parent session's worktree (for inheritance) | `/path/to/repo` |

### Usage in Spawned Sessions

```python
# In spawned session, detect worktree context
import os

worktree_path = os.environ.get("SCOPE_WORKTREE_PATH")
worktree_branch = os.environ.get("SCOPE_WORKTREE_BRANCH")
parent_worktree = os.environ.get("SCOPE_PARENT_WORKTREE")

if worktree_path:
    print(f"Running in worktree: {worktree_path}")
    print(f"Branch: {worktree_branch}")
    print(f"Spawned from: {parent_worktree}")
```

### Auto Mode Logic

```python
def should_use_worktree() -> bool:
    """Determine if worktree should be used based on SCOPE_USE_WORKTREE."""
    mode = os.environ.get("SCOPE_USE_WORKTREE", "false").lower()

    if mode == "true":
        return True
    elif mode == "false":
        return False
    elif mode == "auto":
        # Use worktree if spawning parallel tasks
        # or if explicitly requested via --worktree flag
        return is_parallel_spawn() or has_worktree_flag()
    return False
```

## 8. Error Handling Categories

### Custom Exception Classes

```python
# src/scope/exceptions.py

class WorktreeError(Exception):
    """Base class for worktree-related errors."""
    pass

class BranchExistsError(WorktreeError):
    """Branch already exists and cannot be created."""
    def __init__(self, branch_name: str, existing_path: str | None = None):
        self.branch_name = branch_name
        self.existing_path = existing_path
        msg = f"Branch '{branch_name}' already exists"
        if existing_path:
            msg += f" (checked out at {existing_path})"
        super().__init__(msg)

class PathExistsError(WorktreeError):
    """Worktree path already exists."""
    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Path already exists: {path}")

class DirtyWorktreeError(WorktreeError):
    """Worktree has uncommitted changes."""
    def __init__(self, path: str, changes: list[str] | None = None):
        self.path = path
        self.changes = changes or []
        msg = f"Worktree has uncommitted changes: {path}"
        if changes:
            msg += f"\n  Changes: {', '.join(changes[:5])}"
        super().__init__(msg)

class LockedWorktreeError(WorktreeError):
    """Worktree is locked and cannot be modified."""
    def __init__(self, path: str, reason: str | None = None):
        self.path = path
        self.reason = reason
        msg = f"Worktree is locked: {path}"
        if reason:
            msg += f"\n  Reason: {reason}"
        super().__init__(msg)

class DiskSpaceError(WorktreeError):
    """Insufficient disk space for worktree operation."""
    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient disk space: need {required}MB, have {available}MB"
        )

class SubmoduleError(WorktreeError):
    """Error related to submodules in worktree."""
    def __init__(self, message: str, submodule_path: str | None = None):
        self.submodule_path = submodule_path
        super().__init__(message)
```

### Error Detection and Handling

```python
def create_worktree_safe(
    path: str,
    branch: str,
    create_branch: bool = True,
) -> WorktreeInfo:
    """Create worktree with comprehensive error handling."""

    # Pre-flight checks
    if os.path.exists(path):
        raise PathExistsError(path)

    # Check disk space
    required_mb = estimate_worktree_size()
    available_mb = get_available_disk_space(path)
    if available_mb < required_mb:
        raise DiskSpaceError(required_mb, available_mb)

    # Check for submodules
    if has_submodules():
        logger.warning(
            "Repository has submodules. Worktree submodule support is experimental."
        )

    # Check if branch exists and is checked out
    if branch_exists(branch):
        if create_branch:
            checkout_path = get_branch_checkout_path(branch)
            raise BranchExistsError(branch, checkout_path)
        # Branch exists but we're not creating, just checking out

    try:
        result = subprocess.run(
            ["git", "worktree", "add"] +
            (["-b", branch] if create_branch else []) +
            [path, branch if not create_branch else "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        # Parse git error messages
        stderr = e.stderr.lower()
        if "already checked out" in stderr:
            raise BranchExistsError(branch)
        elif "already exists" in stderr:
            raise PathExistsError(path)
        elif "locked" in stderr:
            raise LockedWorktreeError(path)
        else:
            raise WorktreeError(f"Git worktree error: {e.stderr}")

    return WorktreeInfo(path=Path(path), branch=branch, session_id="")
```

## 9. Other Tools Analysis

### newt (cdzombak/newt)

**Directory Structure:** Stores worktrees in `repo_root/.newt/`

**Commands:**
- `newt -b branch-name` - Create new branch with worktree
- `newt branch-name` - Open existing branch in worktree
- `newt -l` - List worktrees
- `newt -d worktree-name` - Delete worktree and branch

**Key Features:**
- Automatically excludes `.newt/` from git
- Opens shell session in worktree after creation
- Designed for AI agent parallel workflows

**Reference:** [Chris Dzombak's blog](https://www.dzombak.com/blog/2025/10/a-tool-for-working-with-git-worktrees/)

### tree-me (haacked/dotfiles)

**Directory Structure:** `$WORKTREE_ROOT/<repo-name>/<branch-name>`

Example:
```
~/dev/worktrees/
├── dotfiles/
│   ├── haacked/vim-improvements/
│   └── haacked/git-tools/
└── posthog/
    └── haacked/feature-flags/
```

**Commands:**
- `create` - Create new branch worktree
- `checkout/co` - Access existing branch
- `pr` - Fetch and checkout GitHub PRs
- `list/ls` - Display all worktrees
- `remove/rm` - Delete worktree
- `prune` - Clean stale files
- `shellenv` - Output shell function for directory switching

**Key Features:**
- Auto-detects repository name from git remote
- Auto-detects default branch
- Tab completion support
- PR checkout support via `gh` CLI

**Reference:** [haacked.com](https://haacked.com/archive/2025/11/21/tree-me/)

### matklad's Fixed Worktree Set

**Directory Structure:** `~/projects/<project>/<worktree-name>`

Example:
```
~/projects/tigerbeetle/
├── main/     # Read-only snapshot of remote main
├── work/     # Primary development (switches branches)
├── review/   # Code review
├── fuzz/     # Long-running fuzzing (detached HEAD)
└── scratch/  # Miscellaneous tasks
```

**Philosophy:**
- 5 permanent worktrees for different activities
- Not using worktrees as branch replacement
- Managing concurrency in tasks, not branches
- `fuzz` uses detached HEAD (`-d` flag)
- `main` is read-only for comparison

**Key Features:**
- Branch naming: `username/feature-name` (e.g., `matklad/awesome-feature`)
- Custom `ggc` utility for "commit all with trivial message"
- Uses magit for commit surgery

**Reference:** [matklad.github.io](https://matklad.github.io/2024/07/25/git-worktrees.html)

### git-branchless

**Approach:** Does NOT implement virtual branches like GitButler.

**Philosophy:**
- "Entirely invisible to git" - uses standard git tooling
- Recommends stacked commits over virtual branches
- Emphasizes compatibility with other git tools

**Key Features:**
- `git amend` and `git restack` for stack management
- `git prev/next` for navigation
- Works with standard git worktrees

**Reference:** [GitHub Discussion #1257](https://github.com/arxanas/git-branchless/discussions/1257)

### GitButler Virtual Branches

**Approach:** Single working directory for all branches simultaneously.

**How it works:**
- Uses `git diff` to detect all changes
- Internal mapping tracks which changes belong to which branch
- Applies changes like `git apply`
- Drag-and-drop file organization between branches

**Key Difference from Worktrees:**
- Worktrees: Multiple directories, each with own branch
- Virtual branches: Single directory, multiple "virtual" branches

**Trade-offs:**
- Cannot have conflicting work (single file copy = no conflicts)
- No editor window proliferation
- Difficult to integrate with other git tooling

**Reference:** [GitButler Blog](https://blog.gitbutler.com/git-worktrees)

### @johnlindquist/worktree (wt)

**Commands:**
- `wt new feature-name` - Create new worktree
- `wt list` - List worktrees
- `wt pr 1234` - Checkout PR directly

**Focus:** Opening worktrees in Cursor editor

**Reference:** [npm package](https://www.npmjs.com/package/@johnlindquist/worktree)

### wtp

**Features:**
- Automated setup
- Branch tracking
- Project-specific hooks
- Smart navigation

**Reference:** [GitHub](https://github.com/satococoa/wtp)

## 10. Implementation Recommendations

### Phase 1: Basic Support with `--worktree` Flag

**Goal:** Enable worktree isolation for spawned sessions

**CLI Interface:**
```bash
# Spawn session in dedicated worktree
scope spawn "Fix authentication bug" --worktree

# Spawn with custom base path
scope spawn "Add feature" --worktree --worktree-base /tmp/scope-work

# Environment variable alternative
SCOPE_USE_WORKTREE=true scope spawn "Task"
```

**Implementation Tasks:**
1. Add `--worktree` flag to `scope spawn` command
2. Create `src/scope/worktree.py` module with core functions
3. Modify `spawn.py` to optionally create worktree
4. Add `worktree_path` and `worktree_branch` to session state
5. Set environment variables in spawned Claude session
6. Implement cleanup on session completion

**Default Directory Structure:**
```
repo/
├── .scope/
│   └── worktrees/
│       ├── abc123/      # Session worktree
│       └── def456/      # Another session
├── .git/
│   └── worktrees/
│       ├── abc123/      # Git metadata
│       └── def456/
└── src/
```

### Phase 2: Management Commands

**Goal:** Full worktree lifecycle management

**CLI Interface:**
```bash
# List all Scope-managed worktrees
scope worktree list

# Clean up orphaned worktrees
scope worktree prune

# Manually remove worktree
scope worktree remove <session-id>

# Lock/unlock worktree
scope worktree lock <session-id> --reason "In review"
scope worktree unlock <session-id>
```

**Implementation Tasks:**
1. Add `scope worktree` subcommand group
2. Implement `list` with status and session info
3. Implement `prune` for orphaned worktrees
4. Implement `remove` with force options
5. Implement `lock/unlock` for manual control
6. Add hooks for automatic cleanup on session end

### Phase 3: PR Checkout and Inheritance

**Goal:** Advanced workflows with PR integration and worktree inheritance

**CLI Interface:**
```bash
# Checkout PR in worktree
scope pr checkout 123 --worktree

# Spawn child session inheriting parent worktree
scope spawn "Sub-task" --inherit-worktree

# Spawn with fresh worktree based on PR
scope spawn "Review PR" --pr 123
```

**Implementation Tasks:**
1. Integrate with `gh` CLI for PR checkout
2. Implement worktree inheritance (child uses parent's worktree branch as base)
3. Add `--pr` flag to spawn for PR-based workflows
4. Track parent-child worktree relationships
5. Implement cascade cleanup for inherited worktrees

**Environment Variables for Inheritance:**
```python
# Parent session
SCOPE_WORKTREE_PATH=/repo/.scope/worktrees/parent123
SCOPE_WORKTREE_BRANCH=scope/parent123/main-task

# Child session
SCOPE_WORKTREE_PATH=/repo/.scope/worktrees/child456
SCOPE_WORKTREE_BRANCH=scope/child456/sub-task
SCOPE_PARENT_WORKTREE=/repo/.scope/worktrees/parent123
```

### Configuration Options

```toml
# .scope/config.toml or pyproject.toml [tool.scope]

[worktree]
# Enable worktree mode by default
enabled = false

# Base directory for worktrees (relative to repo root)
base = ".scope/worktrees"

# Branch naming pattern
branch_pattern = "scope/{session_id}/{task_slug}"

# Auto-cleanup on session completion
auto_cleanup = true

# Lock worktrees while session is active
auto_lock = true

# Maximum worktrees before warning
max_worktrees = 10
```

---

## References

- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- [Git Rev-Parse Documentation](https://git-scm.com/docs/git-rev-parse)
- [newt: Git Worktree Manager](https://www.dzombak.com/blog/2025/10/a-tool-for-working-with-git-worktrees/)
- [tree-me: Convention Over Configuration](https://haacked.com/archive/2025/11/21/tree-me/)
- [matklad: How I Use Git Worktrees](https://matklad.github.io/2024/07/25/git-worktrees.html)
- [GitButler: Git Worktrees vs Virtual Branches](https://blog.gitbutler.com/git-worktrees)
- [git-branchless: Virtual Branch Discussion](https://github.com/arxanas/git-branchless/discussions/1257)
- [Git Worktrees for AI Agents](https://nx.dev/blog/git-worktrees-ai-agents)
- [Worktrees with Submodules Guide](https://gist.github.com/ashwch/946ad983977c9107db7ee9abafeb95bd)
