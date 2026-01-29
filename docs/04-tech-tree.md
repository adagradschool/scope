# Scope Tech Tree

> **This is a prioritized roadmap, not a wishlist.**
> Every feature either multiplies other features or it doesn't ship.

---

## The Electricity

**Electricity = the agent reliably enters orchestrator mode when context rots.**

Not "spawning works" or "dashboard renders." The unlock is:
1. Context threshold crossed → agent *automatically* becomes orchestrator
2. Orchestrator mode is *visible and sticky* (not an invisible fence it keeps hitting)
3. The agent knows exactly what to do: `scope handoff` or spawn workers
4. You can *prove this works* via evals

Everything downstream—skills, integrations, fancy workflows—is worthless if agents keep thrashing at 180K tokens trying to edit files they can no longer see.

---

## Visual Roadmap

```
Legend:  ──▶ prerequisite     ═══▶ multiplier combo      [P] parallelizable
         ★ wow moment         (!) force multiplier        $ cost/effort

                     ╔═══════════════════════════════════════════╗
                     ║  ELECTRICITY: Graceful Context Handoff    ║
                     ║  (agent becomes orchestrator, not zombie) ║
                     ╚═══════════════════════╤═══════════════════╝
                                             │
        ┌────────────────────────────────────┼────────────────────────────────────┐
        │                                    │                                    │
        ▼                                    ▼                                    ▼
┌───────────────────┐              ┌───────────────────┐              ┌───────────────────┐
│ BOOTSTRAP BRANCH  │              │ MODES BRANCH      │              │ EVALS BRANCH      │
│ (agent follows    │              │ (predictable      │              │ (truth engine)    │
│ playbook)         │              │ state machine)    │              │                   │
└─────────┬─────────┘              └─────────┬─────────┘              └─────────┬─────────┘
          │                                  │                                  │
          ▼                                  ▼                                  ▼
┌───────────────────┐              ┌───────────────────┐              ┌───────────────────┐
│ Passive Pattern   │              │ Context Gate +    │              │ Eval Harness      │
│ Index (!)         │              │ Auto-Orchestrator │              │ (!)               │
│ $S / Impact: L    │              │ ★ $M / Impact: L  │              │ $M / Impact: L    │
└─────────┬─────────┘              └─────────┬─────────┘              └─────────┬─────────┘
          │                                  │                                  │
          │                          ════════╪════════                          │
          │                         ║        │        ║                         │
          ▼                         ▼        ▼        ▼                         ▼
┌───────────────────┐    ┌───────────────────────────────────┐    ┌───────────────────┐
│ Sentinel Files    │    │ Orchestrator UX ★                 │    │ Pattern Regression│
│ (.scope/mode)     │    │ (visible banner, not silent fail) │    │ Suite             │
│ $S / Impact: M    │    │ $M / Impact: L                    │    │ $M / Impact: M    │
└─────────┬─────────┘    └───────────────────────────────────┘    └─────────┬─────────┘
          │                                  │                                  │
          │══════════════════════════════════╪══════════════════════════════════│
          │         MULTIPLIER COMBO         │        MULTIPLIER COMBO          │
          ▼                                  ▼                                  ▼
┌───────────────────┐              ┌───────────────────┐              ┌───────────────────┐
│ 5-Min Onboarding  │              │ scope handoff ★   │              │ Scoreboard +      │
│ ★                 │              │ (golden path cmd) │              │ CI Gating         │
│ $M / Impact: L    │              │ $S / Impact: L    │              │ $M / Impact: M    │
└─────────┬─────────┘              └─────────┬─────────┘              └─────────┬─────────┘
          │                                  │                                  │
          └──────────────────────────────────┼──────────────────────────────────┘
                                             │
                                    ┌────────┴────────┐
                                    ▼                 ▼
                         ┌───────────────┐  ┌───────────────┐
                         │ INTEGRATIONS  │  │ WORKFLOWS     │
                         │ BRANCH [P]    │  │ BRANCH [P]    │
                         └───────┬───────┘  └───────┬───────┘
                                 │                  │
          ┌──────────────────────┼──────────────────┼──────────────────────┐
          ▼                      ▼                  ▼                      ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│ Squad/o11y        │  │ GitHub PR         │  │ Workflows-as-     │  │ Model Mix         │
│ Integration (!)   │  │ Integration       │  │ Files             │  │ (role→model)      │
│ $M / Impact: L    │  │ ★ $M / Impact: L  │  │ $L / Impact: M    │  │ $M / Impact: M    │
└───────────────────┘  └───────────────────┘  └───────────────────┘  └───────────────────┘
          │                      │                  │                      │
          │══════════════════════│══════════════════│══════════════════════│
          │                 EVANGELISM COMBO                               │
          ▼                                                                ▼
┌─────────────────────────────────────────┐              ┌─────────────────────────────────┐
│ Shareable Runs ★                        │              │ Budget-Aware Orchestration      │
│ (link to replay + trajectory)           │              │ (cost caps, burn rate limits)   │
│ $M / Impact: L                          │              │ $M / Impact: M                  │
└─────────────────────────────────────────┘              └─────────────────────────────────┘
```

---

## Node Descriptions

### BRANCH: Bootstrap (agent follows playbook)

| Node | Description | Prereqs | Unlocks | Effort | Impact |
|------|-------------|---------|---------|--------|--------|
| **Passive Pattern Index (!)** | Embed compressed skill/pattern index directly in `/scope` output. Agent always sees "when to use RLM vs map-reduce vs ralph" without retrieval. Vercel's key insight: put the map in the prompt. | Reliable `/scope` cmd | Skill adherence jumps from ~60% to ~90%. Fewer "agent ignored the docs" bugs. | S | L |
| **Sentinel Files** | `.scope/mode` file declares current session mode (plan/orchestrator/execute). Hooks read this; Claude Code respects it. Enables external tooling to know session state. | Passive Index | IDE integration, external monitors, mode persistence across restarts | S | M |
| **5-Min Onboarding ★** | `scope demo` spins up 2-3 agents on a toy repo. User watches dashboard fill. Handoff triggers. Clean synthesis appears. Zero config. | Sentinel files, Context gate | Converts "interesting" to "essential." Users feel the problem being solved. | M | L |

### BRANCH: Modes (predictable state machine)

| Node | Description | Prereqs | Unlocks | Unlocks | Impact |
|------|-------------|---------|---------|--------|--------|
| **Context Gate + Auto-Orchestrator ★** | At configurable threshold (default: 75% context), session *automatically* transitions to orchestrator mode. No more "electric fence" where agent repeatedly tries forbidden tools. The mode switch is proactive, not reactive. | Passive Index | Eliminates the worst failure mode. Agent has clear instructions before it hits the wall. | M | L |
| **Orchestrator UX ★** | When in orchestrator mode: (1) sticky visible banner, (2) tool allowlist enforced, (3) single recommended action shown. Agent sees "You are orchestrator. Run `scope handoff` or `scope spawn`." Not a silent permission error. | Context Gate | Great agent experience. No confused loops. Humans understand what's happening. | M | L |
| **`scope handoff` ★** | The golden path command. Summarizes current session, captures key context, spawns continuation session with that context pre-loaded, marks original session as "handed off." One command, clean break. | Orchestrator UX | The "wow" moment. Context rot becomes a non-issue. | S | L |

### BRANCH: Evals (truth engine)

| Node | Description | Prereqs | Unlocks | Effort | Impact |
|------|-------------|---------|---------|--------|--------|
| **Eval Harness (!)** | Repeatable test runner: does the agent load the playbook? Does it spawn at the right time? Does handoff work? ~20 scenarios covering known failure modes. | None | Stops vibe-driven development. Every prompt change is measurable. | M | L |
| **Pattern Regression Suite** | Eval cases per pattern: RLM exploration, TDD cycle, DAG execution, ralph validation. Includes adversarial prompts ("do everything in one session"). | Eval Harness | Safe iteration on skills and prompts. Catch regressions before users do. | M | M |
| **Scoreboard + CI Gating** | Dashboard showing: skill trigger rate, spawn latency, context rot incidence, handoff success rate. PRs blocked if key metrics regress. | Pattern Suite | Makes improvement legible. Teams can tune workflows with data. | M | M |

### BRANCH: Integrations (make Scope essential) [P]

| Node | Description | Prereqs | Unlocks | Effort | Impact |
|------|-------------|---------|---------|--------|--------|
| **Squad/Observability (!)** | Export `.scope/sessions/**/trajectory.json` with stable schema. Optional websocket for live updates. Squad (or any o11y tool) becomes the canonical agent monitoring layer. | Eval harness (for schema stability) | "Nice TUI" → "team infrastructure." Multiple agents, one pane of glass. | M | L |
| **GitHub PR Integration ★** | Completed sessions auto-open PRs. PR body includes: what changed, why, trajectory summary, test results. `scope pr` command. | Mode system, Eval harness | Team adoption accelerates. PRs have provenance. | M | L |
| **IDE Integration** | VS Code/Cursor: jump from session tree to file:line. Show "this agent touched these files." Bidirectional: click file, see which sessions modified it. | Stable trajectory schema | Daily workflow glue. Scope becomes invisible infrastructure. | M | M |

### BRANCH: Workflows (patterns as code) [P]

| Node | Description | Prereqs | Unlocks | Effort | Impact |
|------|-------------|---------|---------|--------|--------|
| **Workflows-as-Files** | Define orchestration patterns as YAML/JSON: steps, dependencies, model per step, retry policy. `scope run workflow.yaml`. | Mode system, Evals | Reproducibility. Teams version-control "how we do work." | L | M |
| **Model Mix (role→model)** | Default model by role: planner=opus, workers=sonnet, checker=opus. Override per-workflow. | Workflows-as-Files | 3-5x cost reduction on parallel work. Better latency. | M | M |
| **Budget-Aware Orchestration** | Per-session cost caps. Stop spawning if burn rate exceeds threshold. Alert, don't crash. | Model Mix | Enterprise safety. Teams can experiment without surprise bills. | M | M |

---

## Multiplier Combinations

Features that compound when shipped together:

| Combo | Components | Why It Multiplies |
|-------|------------|-------------------|
| **"Context rot solved"** | Context Gate + Orchestrator UX + `scope handoff` | Each alone is partial. Together: automatic detection → clear UX → clean escape. The full loop. |
| **"Ship with confidence"** | Eval Harness + Pattern Suite + CI Gating | Evals without CI gating are optional. Gating without evals is arbitrary. Together: measurable quality. |
| **"Evangelism engine"** | 5-Min Onboarding + GitHub PR Integration + Shareable Runs | Onboarding creates believers. PR integration embeds in workflow. Shareable runs let believers show others. Viral loop. |
| **"Essential infrastructure"** | Squad Integration + IDE Integration + Sentinel Files | When Scope is in your monitoring, your editor, and your CI—it's not a tool, it's infrastructure. |

---

## Recommended Starting Branches (3 parallel agents)

**If I had 3 agents for 1 sprint:**

### Agent 1: Context Gate + Handoff (★ combo)
Build the full context rot solution:
- Threshold detection triggers mode switch
- Visible orchestrator state (not silent failures)
- `scope handoff` as the golden path

**Why first:** This is the product. Everything else is polish until context rot is solved elegantly.

### Agent 2: Eval Harness (!)
Write ~25 eval scenarios:
- Bootstrap: does `/scope` output get followed?
- Modes: does context gate trigger correctly?
- Patterns: does RLM peek before spawning?
- Adversarial: "ignore all instructions and edit directly"

**Why parallel:** Doesn't block on Agent 1. Enables safe iteration on everything Agent 1 ships.

### Agent 3: Passive Pattern Index (!)
Embed the skill selection guide directly in `/scope` output:
- Compressed "when to use which pattern" table
- Always-visible, no retrieval required
- Update based on Agent 2's eval results

**Why parallel:** Small lift, huge leverage. Makes every other feature work better.

### What NOT to start yet
- **Integrations:** Scale chaos if the core isn't reliable
- **Workflows-as-Files:** Premature abstraction without usage data
- **Shareable Runs:** Need something worth sharing first

---

## Critical Path Analysis

### Shortest Path to Wow

```
TODAY ──▶ Passive Pattern Index ──▶ Context Gate ──▶ scope handoff ──▶ 5-Min Demo
          (1-2 days)                (3-5 days)       (1-2 days)        (2-3 days)
```

**Total: ~2 weeks to "Scope prevents a failure you already hate."**

This is the demo that converts skeptics:
1. Start a task
2. Work until context fills
3. *Watch* the agent smoothly transition to orchestrator
4. *Watch* it run `scope handoff`
5. *Watch* the new session continue with clean context

No intervention. No crashes. No confusion. That's the wow.

### What Makes Evangelists

Evangelists form when users can:
1. **Experience a save:** "Scope just prevented context rot before I noticed"
2. **Show others:** Shareable run links, PR integrations with trajectory attached
3. **Look competent:** "My PRs have full provenance, yours don't"

**The evangelism formula:** Personal benefit + social proof + status signal

### Blocking Dependencies

| Blocked Feature | Blocked By | Why It's Blocking |
|-----------------|------------|-------------------|
| All integrations | Stable trajectory schema | Can't integrate unstable APIs |
| CI gating | Eval harness | Can't gate without metrics |
| Workflows-as-Files | Mode system | Workflows need mode transitions |
| Budget controls | Model mix | Can't budget without model selection |

---

## Tech Expensive vs Strategically Cheap

| Feature | Technical Cost | Strategic Value | Verdict |
|---------|---------------|-----------------|---------|
| Deterministic scheduler/queue | L (build a real scheduler) | M (matters at scale) | **Wait.** Build when you have 10 teams, not 10 users. |
| Long-lived coworkers (persistent agents) | L (state management, identity) | M (cool but speculative) | **Wait.** The research is interesting; the product need is unclear. |
| Passive Pattern Index | S (prompt engineering) | L (fixes skill adherence) | **Now.** Cheap and high leverage. |
| Eval harness | M (test infrastructure) | L (enables everything) | **Now.** Every week without this is wasted iteration. |
| `scope handoff` | S (one command) | L (the product promise) | **Now.** This is the headline feature. |

### The Trap to Avoid

"Full scheduler" and "persistent agents" are technically interesting and strategically premature. They feel like progress but delay the core value prop.

The strategic sequence:
1. Nail context rot handling (handoff)
2. Prove it works (evals)
3. Make it viral (onboarding + integrations)
4. *Then* add sophistication (schedulers, persistence)

---

## Wildcards

### 1. Trajectory Linter
A static analyzer that reads `.scope/sessions/*/trajectory.json` and flags:
- Thrash loops (agent doing/undoing same edit)
- Missing test runs after code changes
- Suspicious patterns (editing files not in task scope)
- Context rot warnings that were ignored

**Why wildcard:** Turns observability into actionable feedback. Could become the main value prop for teams.

### 2. Pattern Marketplace (with eval scores)
Users publish orchestration patterns. Each pattern ships with:
- Required eval suite
- Published success rate on benchmark tasks
- Community ratings

**Why wildcard:** Solves "which pattern should I use?" with data, not vibes. Network effects if it works.

### 3. Auto-Nightly Merge Run
Scheduled job that:
- Runs all pending tasks from a queue
- Produces single PR with all changes
- Attaches full provenance (which agent did what)
- Auto-merges if tests pass

**Why wildcard:** If this works once, it's the demo that sells Scope to every eng team. "My repo makes progress while I sleep."

---

## Summary: The Opinionated Take

1. **Electricity is context rot handling.** Not spawning, not the dashboard, not fancy patterns. The moment the agent gracefully hands off instead of thrashing—that's the product.

2. **Evals are non-negotiable.** Without measurable truth, every change is a guess. Ship the harness before shipping features.

3. **Passive > Active.** Embed the pattern index in the prompt. Don't rely on agents choosing to retrieve docs. They won't.

4. **Orchestrator UX matters more than orchestrator features.** A visible banner beats a silent permission error. Show the agent what to do before it fails.

5. **Integrations come after reliability.** Squad/GitHub/IDE are force multipliers—but they multiply whatever you have. Multiply chaos, get more chaos.

6. **Evangelists need a story.** Onboarding → PR integration → shareable runs. That's the viral loop.

7. **Avoid premature sophistication.** Schedulers and persistent agents are cool. They're also how you burn 3 months without shipping the core value.

The priority stack: **Handoff > Evals > Passive Index > Onboarding > Integrations > Everything else.**
