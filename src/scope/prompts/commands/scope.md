<prompt>
  <instructions>
You are scope-managed. Task tool is disabled; use `scope spawn` for subagents.

## MANDATORY: Skill Selection

Before doing ANY work, you MUST evaluate if a skill applies. This is NOT optional.

| Skill | Trigger Patterns |
|-------|------------------|
| `/ralph` | "improve", "refine", "iterate", "polish", "critique", "enhance quality" |
| `/tdd` | "add tests", "test-driven", "fix bug with test", "implement feature" (code changes) |
| `/rlm` | "explore", "find", "understand codebase", "analyze large file", ">100 lines to examine" |
| `/map-reduce` | "process multiple files", "batch", "analyze each", "parallel tasks" |
| `/maker-checker` | "security", "critical", "validate", "review", "high-stakes" |
| `/dag` | "pipeline", "ordered steps", "A then B then C", "dependencies between tasks" |

## Enforcement Protocol

1. **STOP** - Do not begin work immediately
2. **CLASSIFY** - Match the task against skill triggers above
3. **INVOKE or PROCEED**:
   - If a skill matches: `Skill tool with skill="<name>"` - MANDATORY, no exceptions
   - If NO skill matches: Proceed with direct execution

## Examples

- "Improve this code quality" → MUST invoke `/ralph`
- "Add a new endpoint with tests" → MUST invoke `/tdd`
- "Find where errors are handled" → MUST invoke `/rlm`
- "Process all .py files" → MUST invoke `/map-reduce`
- "Review this security-critical change" → MUST invoke `/maker-checker`
- "Build, then test, then deploy" → MUST invoke `/dag`
- "Rename this variable" → No skill matches, proceed directly

## Context Limit (50k tokens)

When blocked by context gate:
- **HANDOFF**: `scope spawn "Continue: [progress] + [remaining work]"`
- **SPLIT**: `scope spawn "subtask 1"` + `scope spawn "subtask 2"` + `scope wait`

## Commands

| Command | Effect |
|---------|--------|
| `scope spawn "task"` | Start subagent |
| `scope spawn --id=X --after=Y "task"` | Start with dependency |
| `scope poll` | Check status (non-blocking) |
| `scope wait` | Block until complete |

## Recursion Guard

- Subtasks MUST be strictly smaller than parent
- NEVER spawn a task similar to what you received—do it yourself
- Include specific context: files, functions, progress

## CLI Quick Reference

```
scope                  # Launch TUI (shows all sessions)
scope spawn "task"     # Start subagent with task
scope spawn --plan     # Start in plan mode
scope spawn --model=X  # Use specific model (opus/sonnet/haiku)
scope poll [id]        # Check status (non-blocking)
scope wait [id]        # Block until done
scope abort <id>       # Kill a session
scope trajectory <id>  # Export conversation JSON
scope setup            # Reinstall hooks/skills
scope uninstall        # Remove scope integration
```

DAG options: `--id=NAME --after=A,B` for dependency ordering.
  </instructions>
</prompt>

$ARGUMENTS
