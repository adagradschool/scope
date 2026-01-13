---
name: dag
description: Multi-step workflows with task dependencies. Use for build pipelines requiring ordered execution, or complex orchestration with partial parallelism.
---

# DAG: Dependency Graph Execution

Tasks with dependencies. Use --id and --after for ordering.

## Syntax
```
scope spawn --id=A "Task A (no deps)"
scope spawn --id=B "Task B (no deps)"
scope spawn --id=C --after=A,B "Task C (needs A and B)"
scope spawn --id=D --after=C "Task D (needs C)"
```

## Workflow
```
# 1. Identify tasks and dependencies
# 2. Assign IDs to each task
# 3. Spawn with --after for dependencies
# 4. scope wait blocks until all complete

scope spawn --id=parse "Parse input files"
scope spawn --id=validate "Validate schema"
scope spawn --id=transform --after=parse,validate "Transform data"
scope spawn --id=output --after=transform "Generate output"
scope wait
```

## Rules
- Tasks without --after start immediately
- --after=X,Y waits for BOTH X and Y
- Cycles are forbidden (A->B->A)
- Failed dependency = dependent task skipped
- Use descriptive IDs (not just a,b,c)
