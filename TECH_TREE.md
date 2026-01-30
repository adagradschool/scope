# Scope Tech Tree

## The Fundamental Primitive: Loops

Every `scope spawn` is a **loop** — a doer/checker pair where the checker both verifies and decides (accept/retry/terminate). The `--checker` flag is **required** — every task must declare its verification. Default max iterations is 3.

```
┌─────────────────────────┐          ┌─────────────────────────┐
│       Task 1            │          │       Task 2            │
│  ┌─────────────────┐    │          │  ┌─────────────────┐    │
│  │    Doer          │    │          │  │    Doer          │    │
│  │  (does the work) │    │          │  │  (does the work) │    │
│  ├──────────────────┤    │ ──────▶  │  ├──────────────────┤    │
│  │    Checker       │    │          │  │    Checker       │    │
│  │  (verify+decide) │    │          │  │  (verify+decide) │    │
│  └─────────────────┘    │          │  └─────────────────┘    │
└─────────────────────────┘          └─────────────────────────┘
```

This unifies all feedback patterns under one primitive:

| Pattern | Doer | Checker | Max Iter |
|---------|------|---------|----------|
| TDD red | "Write failing test" | `pytest tests/` (expect fail) | 3 |
| TDD green | "Make test pass" | `pytest tests/` (expect pass) | 5 |
| RALPH | "Improve: {task}" | `agent: Critique this. Verdict: ACCEPT/RETRY` | 5 |
| Maker-checker | "Implement: {task}" | `agent: Review. Verdict: ACCEPT/RETRY` | 3 |
| Simple task | "{task}" | `agent: Verify the task was completed correctly` | 3 |

**Key design decisions:**
- **Checker = mediator**: The checker verifies output AND recommends verdict. No third agent.
- **Emergent nesting**: Any doer can itself spawn sub-loops. Scope doesn't track depth.
- **Checker is mandatory**: Forces intentional verification design.
- **Max iterations default 3**: Hard cap prevents runaway loops.
- **Both doer and checker are tmux sessions**: Fully visible, introspectable, steerable.

---

## The Electricity

Skills aren't deterministic programs — they're intelligent orchestration where the orchestrator agent must *think* at every step. "What should the red phase test?" "What critique matters here?" "Did this session drift?"

The electricity of Scope is **the quality of the orchestration loop**:

```
Contract → Sub-agent execution → Checker verification → Orchestrator decision → Next contract
```

Every feature in this tree improves some part of this loop. They're organized around three primitives. The loop primitive (above) subsumes F1–F4:

- **F1 (Feedback Signals)** → command checkers ARE feedback signals
- **F2 (Hierarchical Decomposition)** → emergent nesting of loops
- **F3 (Loop Termination)** → `--max-iterations` + checker verdict (ACCEPT/RETRY/TERMINATE)
- **F4 (Pattern Commitment)** → patterns are loop templates with specific checker configurations

---

## The Three Primitives

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│  1. FEEDBACK LOOPS             How do you generate good feedback      │
│                                signals, decompose loops              │
│                                hierarchically, and know when         │
│                                to stop?                              │
│                                                                      │
│  2. DAG ORCHESTRATION          How do you express and execute        │
│                                dependency graphs — piping,           │
│                                phases, fan-out, conditions?          │
│                                                                      │
│  3. CONTEXT MANAGEMENT         How do you give each sub-agent        │
│                                the right context — not too much,     │
│                                not too little, at the right time?    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

These three primitives are independent but compound. Better feedback signals make orchestration decisions sharper. Better DAG structure makes feedback flow efficiently. Better context management keeps the whole system within its resource limits. The electricity runs through all three.

---

## Primitive 1: Feedback Loops

The core question: how does the orchestrator know if a sub-agent did a good job? Today, it reads the freeform result and makes a judgment call. This works for simple tasks but breaks down for complex ones — the orchestrator doesn't have strong signals about *what specifically* went right or wrong, which makes its next decision (retry? adjust? move on?) unreliable.

This primitive is about generating high-quality feedback signals, decomposing loops hierarchically, and knowing when to terminate.

### F1: Feedback Signal Quality

**What:** Give the orchestrator concrete, actionable signals about what a sub-agent produced — not just "it finished" but specific quality indicators. These signals come from running real verification tools against the sub-agent's output:

- **Linting** — does the code pass static analysis? What warnings were introduced?
- **Unit testing** — do existing tests still pass? Do new tests cover the right cases?
- **Integration testing** — do the changed modules work together?
- **End-to-end testing** — does the user-facing behavior still work? (Cypress, Playwright, etc.)
- **Type checking** — does the code typecheck? Were new type errors introduced?

**Why this improves the loop:** The orchestrator's decision after each phase is the intelligence in the loop. The quality of that decision is bounded by the quality of the feedback it receives. "The session finished" is a weak signal. "The session finished, 3 tests fail, lint has 2 new warnings, types check clean" is a strong signal that lets the orchestrator make a precise next move — "fix the 3 failing tests" rather than "review what happened."

**What it looks like:**
- After a sub-agent completes, Scope automatically runs a configurable set of verification commands against the working tree
- Results are injected into the orchestrator's context: "Sub-agent w0.1 completed. Verification: tests 47/50 passing (3 new failures in auth_test.py), lint clean, types clean."
- The orchestrator decides what to do with the signal — retry, spawn a fix session, or accept and move on
- Rubric and verification criteria are defined upfront in the contract or skill — the orchestrator specifies what "done" means before spawning, not in a static config file

**Effort:** M

### F2: Hierarchical Loop Decomposition

**What:** Feedback loops can contain feedback loops. A TDD loop (red → green → refactor) is one level. But "implement auth" might decompose into: TDD loop for JWT module → TDD loop for middleware → TDD loop for routes → integration test loop across all three. The orchestrator needs to reason about *which level* of loop it's operating at and decompose large tasks into nested feedback loops.

**Why this improves the loop:** A single flat feedback loop can't handle complex tasks — "implement auth" as one red/green/refactor cycle will produce a mess. Hierarchical decomposition lets the orchestrator break the problem into sub-loops that each have tight, well-defined feedback signals, then compose the results at the outer level.

**What it looks like:**
- The orchestrator recognizes "this task is too large for a single loop" and decomposes into sub-loops
- Each sub-loop has its own feedback signals appropriate to its scope (unit tests for a module, integration tests for the composition)
- Outer loops use inner loop outcomes as their feedback signal: "3 of 4 sub-modules pass their TDD loops, 1 needs retry"
- Skills describe decomposition strategies: "for large features, decompose by module boundary and run TDD per module"

**Effort:** M — primarily skill design and contract enrichment for nested loops.

### F3: Loop Termination

**What:** When should a feedback loop stop? Today, the orchestrator just decides — and it tends to either stop too early (first green pass, regardless of quality) or too late (infinite refinement chasing diminishing returns). This node is about giving the orchestrator clear termination criteria.

**Why this improves the loop:** Termination is the hardest decision in iterative work. Without explicit criteria, the orchestrator uses its "gut feeling" which is really just whatever's most salient in its context window. With criteria, it can evaluate: "tests pass, lint clean, no type errors — this loop is done" or "tests pass but coverage dropped 10% — one more iteration."

**What it looks like:**
- Termination criteria are specified in the contract or skill: "this loop completes when all tests pass and lint is clean"
- After each iteration, Scope runs verification (F1) and checks against criteria
- The orchestrator sees: "Iteration 2: criteria met (tests pass, lint clean). Recommend: terminate." or "Iteration 3: 2/3 criteria met (tests pass, lint clean, but coverage dropped). Recommend: one more iteration."
- Max iteration bounds prevent infinite loops: "stop after 5 iterations regardless"

**Effort:** M — builds on F1 (feedback signals provide the criteria inputs).

### F4: Pattern Commitment

**What:** The orchestrator *chooses* a pattern (TDD, RALPH, map-reduce), then Scope *enforces* it through persistent reminding that prevents accidental drift while allowing deliberate deviation.

Today's skills are all freedom, no enforcement. The orchestrator reads "follow TDD: red, green, refactor" from CLAUDE.md and might skip refactor, do green before red, or forget it was doing TDD entirely — not because it's bad at its job, but because 50K tokens of tool results have pushed the skill prompt out of the attention window. This is a memory problem, not an intelligence problem.

**Enforcement mechanic — contract re-injection:** When the orchestrator commits to a pattern, Scope registers it. Every time a sub-agent completes and the orchestrator gets a result back, Scope re-injects the pattern state into the orchestrator's context: "Pattern: TDD. Completed: red. Next: green. Prior result: [red output]." The orchestrator can't drift because it's constantly reminded where it is and what comes next. Deviation is still possible but must be explicit — the context says "next: green" and the orchestrator has to actively choose otherwise.

**Why this improves the loop:** The orchestrator's intelligence is in *choosing* the right pattern for the situation and *deciding* what each phase should accomplish. It shouldn't also have to remember where it is in the pattern or resist the temptation to wander. Pattern commitment separates the creative decisions (what to test, when to deviate) from the mechanical ones (what phase comes next).

**What it looks like:**
- Each agent loads the skill it wants — the parent can bias ("this task would benefit from TDD") but doesn't choose for the child
- When an agent commits to a skill, Scope registers the pattern and its phases (red → green → refactor)
- After red completes, the agent receives: "Pattern: TDD. Completed: red [test output summary]. Next expected: green. To deviate, explicitly state why."
- The agent retains full authority — Scope holds it accountable, not hostage

**Effort:** M — extends contract injection, builds on F1.

### F5: Skill Evolution

**What:** An offline improvement loop that uses completed session trajectories to iteratively improve skill definitions. After sessions complete, an LLM reads the trajectory and critiques it against the skill's intent along three axes: (1) did the orchestrator follow the pattern? (2) did it instantiate sub-agents correctly? (3) did it enforce the pattern correctly? The critique drives mutations to the skill prompt text — tightening ambiguous language, adding guardrails where drift occurred, removing instructions that caused confusion.

This follows the [GEPA](https://github.com/gepa-ai/gepa) (Genetic-Pareto Algorithm) approach to prompt evolution: the skill definition is the seed prompt, the trajectory is the execution trace, the critique is the reflection, and the rewritten skill is the mutation. Over iterations, skill definitions converge toward language that LLMs reliably follow.

**Why this improves the loop:** Pattern Commitment (F4) enforces skills at runtime — re-injection keeps the orchestrator on track. Skill Evolution improves the skills themselves offline, so each generation of the skill prompt is *easier* to follow. Runtime enforcement catches drift; offline evolution reduces the drift that needs catching.

**What it looks like:**
- After each task completes, Scope automatically fires the evolution loop against the session's trajectory
- An LLM critiques: "In session w0, the orchestrator skipped the refactor phase. The skill prompt says 'refactor for clarity' but doesn't explain when refactoring is mandatory vs optional."
- The critique produces a candidate skill rewrite: add "Always run refactor. To skip, explicitly state why in the contract."
- Candidate updates are staged — accumulated across sessions, versioned so you can roll back
- Over multiple sessions, Pareto selection across adherence, outcome quality, and sub-agent efficiency converges the skill toward language that LLMs reliably follow

**The three critique axes:**
1. **Pattern adherence:** Did the orchestrator execute phases in the right order? Did it skip steps? Did it deviate without justification?
2. **Sub-agent instantiation:** Were contracts well-formed? Did sub-agents get the right context? Were dependencies set up correctly?
3. **Enforcement quality:** When the orchestrator drifted, did it self-correct? Did it acknowledge the pattern state re-injection?

**Effort:** L — requires trajectory analysis, LLM-based critique, and a mutation/selection loop. Independent of runtime features.

---

## Primitive 2: DAG Orchestration

Today, DAGs are built by the orchestrator agent using `scope spawn --after`. This works for simple chains but gets unwieldy for complex dependency graphs. The orchestrator manually manages piping, fan-out, fan-in, phase sequencing, and failure propagation.

This primitive is about making DAG construction and execution more expressive, so the orchestrator can think in terms of workflow shape rather than individual spawn commands.

### D1: Result Piping

**What:** `scope spawn "review" --pipe <session_id>` — the result of a completed session is automatically injected into the next session's contract. The child doesn't start until the parent is done, and it gets the parent's output as context.

**Why this improves the loop:** Piping is the wire between DAG nodes. Today, `--after` tells the child to `scope wait`, which blocks the tmux session and wastes context on parsing wait output. Piping is cleaner: the child starts with the parent's result already in its contract, so 100% of its context is useful work.

**What it looks like:**
- `scope spawn --id red "write failing test" && scope spawn --id green --pipe red "make it pass"`
- The green session's contract includes: "The red phase produced: [result of red session]"
- Multiple pipes: `--pipe red,green` combines both results into the contract

**Effort:** S

### D2: Phase Sequencing

**What:** First-class multi-phase execution: `scope spawn --phases red,green,refactor "implement auth"`. Each phase runs sequentially as a DAG chain, with the output of one piping into the next automatically.

**Why this improves the loop:** Phases are the most common DAG pattern — a linear chain where each step depends on the previous. Today the orchestrator manually spawns each phase with `--after`. Phase sequencing makes this declarative so the orchestrator focuses on what each phase should accomplish, not the plumbing.

**What it looks like:**
- `scope spawn --phases red,green,refactor --target src/auth "add login"`
- Scope expands this into a 3-node DAG with piping between each phase
- Each phase gets a contract with phase-specific instructions and the prior phase's result
- The orchestrator can customize per-phase contracts or accept defaults

**Effort:** M — extends spawn.py, builds on D1.

### D3: Richer Dependency Expressions

**What:** Beyond `--after` (wait for all), support: `--after-any` (wait for first), `--gate N` (wait for N of M), fan-out helpers (`scope fan-out --task "review" --items a,b,c`), and fan-in (`scope fan-in --reduce "summarize" --sources a,b,c`).

**Why this improves the loop:** The orchestrator currently thinks in terms of individual spawns and waits. Richer expressions let it think in terms of workflow *patterns* — fan-out/fan-in, racing, quorum — and spend its intelligence on what each node should do.

**What it looks like:**
- `scope fan-out --task "test module" --items auth,billing,search` → 3 parallel sessions
- `scope fan-in --reduce "merge results" --wait-for auth,billing,search` → after all complete
- `scope spawn "fast-path" --after-any review-1,review-2` → starts when first finishes

**Effort:** M

### D4: Conditional Branching

**What:** `scope spawn "fix" --on-fail <id>` and `scope spawn "ship" --on-pass <id>` — spawn sessions conditionally based on what happened in a prior session. The orchestrator agent reads the prior result and decides success/failure — intelligence in the loop.

**Why this improves the loop:** Conditional branching lets the orchestrator build DAGs with error recovery and fast paths. A test phase that fails triggers a fix phase. A review that passes skips straight to merge.

**What it looks like:**
- `scope spawn --on-fail red "analyze why test design was wrong"` — only runs if red failed
- `scope spawn --on-pass review "merge to main"` — only runs if review passed

**Effort:** M

### D5: Programmatic Workflows

**What:** Python builder pattern for defining reusable DAGs programmatically. Not YAML — real code that can express conditionals, loops, and parameterization. `scope run workflows/tdd.py --target src/auth`.

**Why this improves the loop:** Declarative formats (YAML, TOML) can't express the dynamic logic that real workflows need — "if the module has existing tests, skip red phase" or "fan-out over all changed files." A Python builder gives full expressiveness while keeping the DAG structure explicit.

**What it looks like:**
```python
from scope import Workflow, Phase

wf = Workflow("tdd")
red = wf.phase("red", task="Write failing tests for {target}")
green = wf.phase("green", pipe=red, task="Make the tests pass")
green.on_fail(retry=3)
refactor = wf.phase("refactor", pipe=green, task="Refactor for clarity")
review = wf.phase("review", pipe=refactor, task="Review the implementation")
review.on_fail(goto=red)

wf.run(target="src/auth")
```

**Effort:** L — builds on D1, D2, D4.

---

## Primitive 3: Context Management

Context is the scarcest resource in the orchestration loop. Every sub-agent has a finite context window. The orchestrator's own context fills up as it coordinates more sessions. Today, Scope has one context management mechanism: the `context-gate` hook that warns when a session hits 80% context usage and suggests spawning a sub-task. This is reactive — it kicks in when you're already in trouble.

This primitive is about making context flow efficiently: giving each sub-agent exactly the right context, and keeping the orchestrator lean enough to coordinate large workflows. Scope exposes the essential context primitives; specific patterns like handoffs are skills built on top of those primitives.

### C1: Contract Enrichment

**What:** Extend `contract.py` to build richer contracts that carry the right context for each sub-agent. Today, contracts are minimal: dependency wait instructions + the task prompt. They should include phase metadata ("you're in the RED phase"), parent intent ("the orchestrator's goal is X, your sub-goal is Y"), relevant prior results, and scoped file context.

**Why this improves the loop:** The contract is the context *input* to each sub-agent. A well-constructed contract means the sub-agent doesn't waste its context window figuring out what it's supposed to do or searching for information the orchestrator already has.

**What it looks like:**
- Contract includes phase context: "You are in the GREEN phase. The RED phase produced these failing tests: [test output]"
- Contract includes scope: "Only modify files in src/auth/. Do not touch src/billing/."
- Contract includes relevant learnings: "In this project, the auth module uses JWT tokens."

**Effort:** S — `contract.py` is 39 lines today, this extends it.

### C2: Poll as Check-in, Wait as Result

**What:** Clarify the semantics of `poll` and `wait`. `poll` becomes a lightweight, non-blocking check-in: "what's the status of this session? still running, how far along, any signals yet?" `wait` becomes the blocking call that returns the full result when the session completes.

**Why this improves the loop:** The orchestrator needs two different context interactions with child sessions. During execution, it wants a cheap status check that doesn't bloat its context — "still running, 3 tool calls so far, no errors." When the session is done, it wants the full result to make its next decision. Today, `poll` and `wait` aren't clearly differentiated, so the orchestrator either wastes context on full results when it just wants status, or gets too little information when it needs the full picture.

**What it looks like:**
- `scope poll w0.1` → "running, 45s elapsed, 12 tool calls, last activity: Edit src/auth/jwt.py" (lightweight, non-blocking)
- `scope wait w0.1` → blocks until complete, returns full result text (blocking, full context)
- `scope poll --all` → status summary of all active sessions in one compact view
- The orchestrator uses `poll` to monitor progress without burning context, and `wait` when it's ready to consume the result and make its next decision

**Effort:** M — clarifies existing commands, extends poll output.

### C3: Orchestrator Context Protection

**What:** Keep the orchestrator's own context lean. Today, the orchestrator reads full results from every sub-agent, accumulating context as it coordinates. This primitive gives the orchestrator summarized views by default — "session X succeeded, changed 3 files, tests pass" — so it can coordinate more sessions before hitting its own context limit.

**Why this improves the loop:** The orchestrator is the bottleneck. If it runs out of context, the whole workflow stalls. Protecting its context means it can coordinate larger, more complex DAGs without degradation.

**What it looks like:**
- `poll` returns compact status (see C2)
- `wait` returns the result, but the orchestrator can request summaries: `scope wait --summary w0.1`
- The orchestrator sees: "w0.1: passed, 3 files changed, all tests green" instead of the full diff
- Drill-down on demand: the orchestrator can request full details for specific sessions when its judgment says it needs them

**Effort:** M — extends poll/wait to return summaries, adds summarization to result capture.

---

## Dependency Graph

```
FEEDBACK LOOPS                  DAG ORCHESTRATION           CONTEXT MANAGEMENT

F1 Feedback Signals              D1 Result Piping           C1 Contract Enrichment
       │                                │                          │
       ▼                                ▼                          ▼
F2 Hierarchical Decomp           D2 Phase Sequencing        C2 Poll/Wait Semantics
       │                                │                          │
       ▼                                ▼                          ▼
F3 Loop Termination              D3 Dependency Exprs        C3 Orchestrator Protection
       │                                │
       ▼                                ▼
F4 Pattern Commitment            D4 Conditional Branching
       │                                │
       ▼                                ▼
F5 Skill Evolution               D5 Programmatic Workflows
```

**Cross-primitive dependencies:**
- D1 (Result Piping) benefits from C1 (Contract Enrichment) — piped results flow through enriched contracts
- D2 (Phase Sequencing) benefits from F1 (Feedback Signals) — each phase needs verification between steps
- F3 (Loop Termination) uses F1 (Feedback Signals) as its criteria inputs
- F4 (Pattern Commitment) benefits from C1 (Contract Enrichment) — re-injected pattern state flows through enriched contracts
- F5 (Skill Evolution) draws from completed trajectories and connects to F4 (Pattern Commitment) — evolution improves the skills that commitment enforces
- D5 (Programmatic Workflows) builds on D1, D2, D4

---

## Critical Path

```
C1 (Contract Enrichment)    [S]    ← Start here: the input to every sub-agent
D1 (Result Piping)           [S]    ← Start here: the wire between DAG nodes
         │                                │
         ▼                                ▼
F1 (Feedback Signals)        [M]   D2 (Phase Sequencing)    [M]
         │                                │
         ▼                                ▼
F3 (Loop Termination)        [M]   D4 (Conditional Branching) [M]
         │                                │
         ▼                                ▼
F4 (Pattern Commitment)      [M]   D5 (Programmatic Workflows) [L]
```

**Two independent starting points:** C1 and D1 are both S effort with no prerequisites. C1 improves every sub-agent immediately. D1 enables DAG composition. They can be built in parallel and they compound — piped results flow through enriched contracts.

---

## Parallel Work Streams

### Stream 1: Feedback Quality (F1 → F3 → F4)
Build feedback signal infrastructure, then loop termination criteria, then pattern commitment via contract re-injection.

**Files:** `src/scope/hooks/handler.py`, `src/scope/core/contract.py`

### Stream 2: DAG Primitives (D1 → D2 → D3 → D4)
Result piping, then phase sequencing, then richer dependency expressions, then conditional branching.

**Files:** `src/scope/commands/spawn.py`, `src/scope/core/contract.py`

### Stream 3: Context Flow (C1 → C2 → C3)
Enrich contracts, then clarify poll/wait semantics, then orchestrator context protection.

**Files:** `src/scope/core/contract.py`, `src/scope/commands/poll.py`, `src/scope/commands/wait.py`

### Stream 4: Agent Backends
`scope spawn --agent codex "task"` — support non-Claude agents. Independent of the other streams. Strategic insurance: if Scope works with any agent CLI, it becomes the universal substrate.

**Files:** `src/scope/commands/spawn.py`, `src/scope/core/tmux.py`

---

## Wildcards

### "Ghost Sessions" — Dry-Run Orchestration

`scope spawn --ghost "task"` — creates a session that doesn't actually run. Instantly completes with a synthetic result based on historical data. Like `terraform plan` for AI orchestration — preview the shape and likely outcome of a DAG before running it.

### "Session Replay as Test Fixture"

`scope fixture <id>` — export a session's trajectory as a deterministic test fixture. Replay it to verify orchestration patterns without calling Claude. Solves Scope's biggest testing challenge: integration tests that require expensive, slow, flaky LLM calls.

### "Scope as Debugger"

Set breakpoints on tool calls: `scope break <id> --on Edit`. Pauses the session before any Edit, letting the user inspect and approve. The `PreToolUse` hook already supports blocking — this extends it into a full debugging experience.

---

## Summary

Scope becomes essential when its three primitives compound:

1. **Feedback loops** give the orchestrator strong signals — linting, testing, type checking — so its decisions after each phase are precise, not vague. Hierarchical decomposition lets it break complex tasks into nested loops with appropriate signals at each level. Pattern commitment keeps it on track. Skill evolution makes the patterns themselves improve over time.
2. **DAG orchestration** gives the orchestrator expressive tools for structuring work — piping, phases, fan-out, conditions, programmatic workflows — so it thinks about *what* each node should accomplish, not the plumbing between them.
3. **Context management** ensures every sub-agent gets exactly the right context and the orchestrator stays lean enough to coordinate large workflows — enriched contracts, lightweight check-ins via `poll`, full results via `wait`.

The electricity — the intelligence in the orchestration loop — gets smarter at every level: better feedback signals make decisions sharper, better DAG tools make structure effortless, better context management lets the whole system scale without drowning in its own output.
