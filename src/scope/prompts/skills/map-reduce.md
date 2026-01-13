---
name: map-reduce
description: Parallel independent tasks with aggregation. Use for file-by-file analysis, aggregatable results across chunks, or when N workers can process simultaneously.
---

# Map-Reduce: Parallel Workers + Aggregation

Fork N workers → Wait all → Reduce results.

## Phases
1. **Map**: Spawn N independent workers in parallel
2. **Wait**: Block until all complete
3. **Reduce**: Synthesize results into final output

## Workflow
```
# Map phase - spawn workers in parallel
scope spawn "Process chunk 1: {specific_task}"
scope spawn "Process chunk 2: {specific_task}"
scope spawn "Process chunk 3: {specific_task}"

# Wait phase - block for all
scope wait

# Reduce phase - synthesize (you do this, or spawn reducer)
Combine results from all workers into final output
```

## Rules
- Workers MUST be independent (no shared state)
- Each worker gets a specific, bounded chunk
- Wait for ALL workers before reducing
- Reducer sees only outputs, not worker context
- If a worker fails, decide: retry, skip, or abort
