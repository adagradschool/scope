# Scope Tech Tree (Roadmap)

> **Premise:** In the agent era, building Scope is more like unlocking a Civilization tech tree than shipping a linear backlog.
> Some features are **electricity** (foundational unlocks). Others are **multipliers** (they compound when combined). Others are vanity.
>
> This doc is opinionated on what matters and why.

---

## 0) Electricity (the foundational unlock)

**Electricity = a *reliable* control plane for agent execution under entropy.**

Not “more features”, but **structural reliability**:
- the agent *actually* loads the playbook and follows it,
- context rot is detected early and resolved cleanly,
- the system can switch modes (plan/orchestrate/execute) predictably,
- you can evaluate this end-to-end.

Everything else (DAGs, skills, fancy UI) only matters if the control plane is dependable.

---

## 1) Visual Diagram (dependencies + branches)

Legend:
- `=>` prerequisite unlock
- `[P]` parallelizable branch
- `(!)` multiplicative node
- `★` big “wow” unlock

```
                                   ┌──────────────────────────────┐
                                   │  ELECTRICITY: Reliable Control│
                                   │  Plane Under Entropy          │
                                   └──────────────┬───────────────┘
                                                  │
     ┌────────────────────────────────────────────┼─────────────────────────────────────────────┐
     │                                            │                                             │
     ▼                                            ▼                                             ▼
┌───────────────┐                         ┌───────────────────┐                          ┌──────────────────┐
│ Bootstrapping  │                         │ Mode System       │                          │ Evals + Metrics   │
│ + Playbook (! )│                         │ (Plan/Orch/Exec)  │                          │ (truth engine) (!)│
└───────┬───────┘                         └─────────┬─────────┘                          └─────────┬────────┘
        │                                           │                                            │
        │                                           │                                            │
        ▼                                           ▼                                            ▼
┌───────────────┐                         ┌───────────────────┐                          ┌──────────────────┐
│ Passive Index  │                         │ Context Rot Policy │                          │ Regression Suite  │
│ everywhere (!) │                         │ + Handoff ★        │                          │ for skills/pattern│
└───────┬───────┘                         └─────────┬─────────┘                          └─────────┬────────┘
        │                                           │                                            │
        │                                           │                                            │
        ▼                                           ▼                                            ▼
┌───────────────┐                         ┌───────────────────┐                          ┌──────────────────┐
│ Onboarding ★   │                         │ Orchestrator UX ★  │                          │ Scoreboard UI     │
│ 5‑min wow path │                         │ (no fence-hitting) │                          │ + CI gating       │
└───────┬───────┘                         └─────────┬─────────┘                          └─────────┬────────┘
        │                                           │                                            │
        │                                           │                                            │
        ▼                                           ▼                                            ▼
┌──────────────────────────┐               ┌──────────────────────┐                   ┌─────────────────────────┐
│ Integrations [P]          │               │ Workflow Library [P]  │                   │ Model Mix/Cost Controls │
│ (Squad, IDE, CI, GH) (!)  │               │ (DAG/TDD/etc as code) │                   │ (cheap worker, rich lead)│
└──────────┬───────────────┘               └──────────┬───────────┘                   └──────────┬──────────────┘
           │                                          │                                      │
           ▼                                          ▼                                      ▼
   ┌────────────────┐                         ┌──────────────────┐                   ┌─────────────────────────┐
   │ Shareable Runs ★│                         │ Deterministic     │                   │ Long-lived coworkers     │
   │ (evangelists)   │                         │ sched/queue (L)   │                   │ (stateful agents) (L)    │
   └────────────────┘                         └──────────────────┘                   └─────────────────────────┘
```

---

## 2) Detailed Node Descriptions

### Branch: Bootstrapping / “agent will actually do it”

#### Node: Reliable `/scope` bootstrap (!)
- **Description:** Ensure Scope’s command/playbook is executed as a command, not embedded as inert text.
- **Prereqs:** none
- **Unlocks:** Everything downstream (skills, modes, handoff) becomes possible.
- **Effort:** S
- **Impact:** L
- **Branch:** Bootstrapping

#### Node: Passive Index Everywhere (!)
- **Description:** Adopt the Vercel insight: put a compressed “where to look + what to do” index in always-present context. Don’t rely on “agent chooses to retrieve.”
- **Prereqs:** Reliable `/scope` bootstrap
- **Unlocks:** Higher skill/pattern adherence; fewer “ignored docs” failures.
- **Effort:** S
- **Impact:** L
- **Branch:** Bootstrapping

#### Node: Onboarding ★ (5-minute wow path)
- **Description:** Make first-run feel like magic: install → open Scope → run a multi-step task → watch agents spawn → get clean synthesis.
- **Prereqs:** Passive index everywhere
- **Unlocks:** Conversion + retention; users immediately understand “why Scope”.
- **Effort:** M
- **Impact:** L
- **Branch:** Bootstrapping

Concrete onboarding artifacts:
- `scope demo` that spins up 2–3 agents on a toy repo and shows the dashboard filling in.
- A one-page “what Scope does / what it doesn’t do” cheat sheet.

---

### Branch: Mode System (Plan ↔ Orchestrate ↔ Execute)

#### Node: Session Modes (Plan/Orchestrator/Execute)
- **Description:** A first-class per-session mode that changes behavior + tool allowances.
- **Prereqs:** Reliable bootstrap
- **Unlocks:** “Plan mode” feel, orchestrator-only control, less thrash.
- **Effort:** M
- **Impact:** L
- **Branch:** Modes

Mode definitions (suggested):
- **plan:** produce plan + checkpoints; no edits
- **orchestrator:** can only spawn/wait/poll/tk (no repo touching)
- **execute:** normal work session

#### Node: Context Rot Policy + Handoff ★
- **Description:** When context approaches danger zone, trigger a *mode switch* early and provide a single golden path: `scope handoff`.
- **Prereqs:** Session modes
- **Unlocks:** Prevents “hit wall → panic spawn → forget” loops.
- **Effort:** M
- **Impact:** L
- **Branch:** Modes

#### Node: Orchestrator UX ★ (no fence-hitting)
- **Description:** Make “you are now orchestrator” *visible before the agent tries tools*.
- **Prereqs:** Context Rot Policy + Handoff
- **Unlocks:** Great agent experience; fewer repeated tool failures.
- **Effort:** M
- **Impact:** L
- **Branch:** Modes

Implementation idea:
- a sticky banner + single recommended next command
- escalate to hard blocking only after repeated violations

---

### Branch: Evals + Metrics (truth engine)

#### Node: Evals Harness (!)
- **Description:** A repeatable way to test “does Scope improve reliability?” (skills triggered, spawning timing, context rot handled).
- **Prereqs:** none (can start immediately)
- **Unlocks:** Prevents vibe-driven development. Enables CI gating.
- **Effort:** M
- **Impact:** L
- **Branch:** Evals

#### Node: Regression Suite for Patterns
- **Description:** Add eval cases for each pattern (RLM/TDD/DAG/etc) including adversarial prompts.
- **Prereqs:** Evals Harness
- **Unlocks:** Safe iteration on `/scope` prompt + hooks.
- **Effort:** M
- **Impact:** M
- **Branch:** Evals

#### Node: Scoreboard UI + CI gating
- **Description:** Show trendlines: skill trigger rate, spawn latency, context rot incidence, % tasks completed without compaction failures.
- **Prereqs:** Regression suite
- **Unlocks:** Makes improvements legible; helps users tune their workflows.
- **Effort:** M
- **Impact:** M
- **Branch:** Evals

---

### Branch: Integrations (make Scope essential) [P]

#### Node: Squad Integration (!)
- **Description:** Pipe Scope session tree + trajectories into Squad (or Squad-like city) as the canonical agent o11y layer.
- **Prereqs:** Trajectory capture exists (already in scope)
- **Unlocks:** “Nice-to-have” → “always on” for teams running multiple agents.
- **Effort:** M–L
- **Impact:** L
- **Branch:** Integrations

Concrete integration surface:
- export `.scope/sessions/**/trajectory_index.json` as a stable schema
- optional websocket/stream for live updates

#### Node: GitHub PR Integration
- **Description:** Auto-open PRs from completed sessions, attach trajectory summary, test results, and “what changed / why”.
- **Prereqs:** Mode system (so you can have a PR-prep workflow)
- **Unlocks:** Evangelism + real team adoption.
- **Effort:** M
- **Impact:** L
- **Branch:** Integrations

#### Node: IDE Integration (VS Code/Cursor)
- **Description:** Jump from scope session tree to file/line in editor; show “this agent touched these files”.
- **Prereqs:** stable trajectory schema
- **Unlocks:** daily workflow glue.
- **Effort:** M
- **Impact:** M
- **Branch:** Integrations

---

### Branch: Workflow Library (patterns as code) [P]

#### Node: Workflows-as-Files
- **Description:** Let users define repeatable workflows (DAG/TDD/ralph) as versioned files (YAML/JSON) executed by Scope.
- **Prereqs:** Session modes + evals
- **Unlocks:** Reproducibility; teams can share “how we do work”.
- **Effort:** L
- **Impact:** M
- **Branch:** Workflows

#### Node: Deterministic Scheduler / Queue (strategically optional)
- **Description:** A real scheduler that enforces concurrency/WIP, dependencies, retries.
- **Prereqs:** workflows-as-files
- **Unlocks:** enterprise-y robustness.
- **Effort:** L
- **Impact:** M
- **Branch:** Workflows

Opinion: this is **technically expensive but strategically cheap** until you have real usage.

---

### Branch: Model Mix + Cost Controls

#### Node: Role-based model defaults
- **Description:** Default model choices by role: planner=opus, workers=sonnet/haiku, checker=opus.
- **Prereqs:** Session modes
- **Unlocks:** Better cost/perf; better parallelism.
- **Effort:** M
- **Impact:** M
- **Branch:** Models

#### Node: Budget-aware orchestration
- **Description:** Per-session budget caps + “stop spawning if burn rate too high”.
- **Prereqs:** role-based model defaults
- **Unlocks:** Safe scaling for teams.
- **Effort:** M
- **Impact:** M
- **Branch:** Models

---

## 3) Recommended Starting Branches (3 parallel agents)

If I had 3 agents for one week, I’d run:

1) **Modes + Handoff (★)**
   - Build `mode=handoff_required` + `scope handoff` happy path.
   - Expected compounding: reduces the worst failure mode (context rot) and makes everything feel intentional.

2) **Evals harness (!)**
   - Write ~20 eval cases around the known failures.
   - Expected compounding: every future prompt/hook change becomes safe + measurable.

3) **Onboarding ★ (demo + docs)**
   - A new user should hit “wow” in <5 minutes.
   - Expected compounding: converts curiosity into habit, which is what creates evangelists.

Why not integrations first? Because without reliable modes + evals, integrations just scale chaos.

---

## 4) Critical Path Analysis

### Shortest path to the next major unlock (★ = “Scope feels inevitable”)

1. **Reliable bootstrap** (already largely in place)
2. **Mode sentinel + handoff command**
3. **Onboarding demo** that showcases handoff + fresh sessions

That’s the shortest path to “wow”: users *feel* Scope preventing a failure they already hate.

### What blocks the highest-impact features?

- **No first-class mode system** blocks “plan/orchestrator/execute” semantics.
- **No eval harness** blocks safe iteration; you can’t tell if a new prompt made things better.
- **No stable exported schema** blocks Squad/IDE/GitHub integrations.

---

## 5) Wildcards (weird but potentially game-changing)

1) **“Auto-merge run” as a product ritual**
   - A nightly job that: summarizes all sessions, produces a single PR, and attaches a provenance report.
   - If it works once, users will tell everyone.

2) **“Scope Linter”**
   - A static analyzer for agent trajectories: flags thrash loops, missing tests, suspicious edits, unclear intent.
   - Turns o11y into *actionable* o11y.

3) **Public pattern marketplace (but with eval scores)**
   - People can publish orchestration patterns, but they must ship an eval pack.
   - The ranking is performance, not vibes.

---

## Notes on effort/impact

- **Strategically cheap, technically expensive:** full scheduler, long-lived coworkers.
- **Strategically expensive, technically cheap:** evals + onboarding + passive index.

These are the leverage points.
