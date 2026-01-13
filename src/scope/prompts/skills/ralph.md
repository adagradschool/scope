---
name: ralph
description: Iterative refinement loops. Use when improving outputs through critique cycles, quality improvement, polish/editing tasks, or convergent optimization toward a goal.
---

# RALPH: Iterative Refinement Loop

Critique → Evaluate → Act → Repeat until done.

## 1. Lock Variables (ask one at a time)
- **Goal**: What does done look like?
- **Max iterations**: Default 5
- **Delta threshold**: When is improvement too small to continue?

Do not proceed until confirmed.

## 2. Loop
```
while iterations < max:
    critique = scope spawn "Critique: evaluate current state against goal"
    scope wait

    if goal_met(critique) or delta < threshold:
        break

    scope spawn "Improve: apply this critique: {critique}"
    scope wait
```

## 3. Exit
Report: why stopped, what changed, current state.

## Rules
- Each step is a fresh subagent via scope spawn
- Never improve without evaluating the critique first
- Stop early if delta is negligible
