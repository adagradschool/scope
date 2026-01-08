# Orchestration Patterns and Agent Models

**From ephemeral workers to persistent coworkers. From static patterns to self-evolving skills.**

This document explores orchestration patterns for AI agents, comparing approaches and proposing a unified model for long-running, self-improving agents.

---

## Part 1: Recursive Language Models (RLMs)

### The Core Idea

RLMs (Zhang, Kraska, Khattab 2025) propose that LLMs should treat long context as an **external environment** rather than cramming it into the context window.

```
Traditional LLM:
[System Prompt | 10M tokens of context | Query] → Answer
                ↑ Context window explodes

RLM:
[System Prompt | Query] → Code that examines context → Answer
                          ↑ Context stays external
```

### The REPL Architecture

The model operates within a Python REPL:

```python
# Context stored as variable, NOT in LLM context window
context = open("huge_file.txt").read()  # 10M tokens, external

# Model outputs code to explore
>>> len(context.split('\n'))
847293

>>> context[:500]
"Chapter 1: Introduction to..."

>>> re.findall(r'error.*', context)
['error handling in auth', ...]

# Model can recursively call itself on snippets
>>> rlm.call("Explain this section", context[5000:6000])
"The error handling uses..."

>>> FINAL("The system uses try/catch for errors")
```

### Emergent Strategies

RLMs naturally develop these patterns:

| Strategy | Description |
|----------|-------------|
| **Peeking** | Inspect initial segments to understand structure |
| **Grepping** | Use regex to narrow search without semantic retrieval |
| **Partition + Map** | Chunk context, launch parallel recursive calls |
| **Summarization** | Extract and condense from subsets |
| **Variable Buffering** | Store intermediate results in REPL variables |

### Benchmark Results

| Benchmark | Base Model | RLM | Improvement |
|-----------|------------|-----|-------------|
| OOLONG (132K tokens) | 44% | 56.5% | +28% |
| OOLONG-Pairs (quadratic) | 0.04 F1 | 58.00 F1 | +1450x |
| BrowseComp+ (6-11M tokens) | 0% | 91% | ∞ |
| LongBench CodeQA | 24% | 62% | +158% |

### Limitations

- **Blocking calls**: Recursive calls are sequential, no parallelism
- **Cost unpredictability**: No guarantees on total API cost
- **Single model**: Can't mix models (cheap for filtering, expensive for synthesis)

---

## Part 2: Scope as Substrate

### The Core Idea

Scope treats the **filesystem as the external environment** and uses **tmux sessions** as execution units.

```
RLM:     Model ←→ REPL (Python process)
Scope:   Model ←→ Filesystem + tmux sessions
```

### Primitives

```bash
# Spawn a subagent
id=$(scope spawn "analyze auth module")

# Block until complete
scope wait $id

# Check status without blocking
scope poll $id
```

### Key Properties

| Property | Description |
|----------|-------------|
| **Fresh context** | Each subagent starts with clean 200K tokens |
| **Parallelism** | Spawn N agents simultaneously |
| **Visibility** | Real-time dashboard, attach to any session |
| **Intervention** | Steer, abort, redirect anytime |
| **Filesystem IPC** | All state in `.scope/sessions/`, inspectable with Unix tools |

### Comparison: RLM vs Scope

| Dimension | RLM | Scope |
|-----------|-----|-------|
| Context location | REPL variable | Filesystem |
| Execution model | Sequential REPL | Parallel tmux sessions |
| Parallelism | Blocking recursive calls | Unlimited fork-join |
| Model mixing | Same model throughout | Different models per agent |
| Visibility | Opaque | Transparent dashboard |
| Context isolation | Accumulates in conversation | Fresh per agent |
| Dead-end cost | Pollutes context | Discarded with agent |

### When Each Wins

**RLM wins when:**
- Tight iteration over single large document
- Task is pure text manipulation (grep, slice, regex)
- Dynamic access patterns (model decides at runtime)
- Sequential depth matters more than parallel breadth

**Scope wins when:**
- Multiple independent subtasks (parallelize)
- Human oversight / intervention needed
- Different capabilities per subtask
- Context contamination must be avoided
- Debugging and reproducibility matter

### The Synthesis

RLM is a **pattern** that can run inside a Scope agent. They're complementary:

```
Scope (macro-orchestration)
├── scope spawn "RLM-style analysis of doc_a.txt"
│   └── [subagent uses REPL-like tools to explore]
├── scope spawn "RLM-style analysis of doc_b.txt"
│   └── [parallel, independent context]
└── scope wait → synthesize
```

---

## Part 3: Skills as Pattern Library

### The Problem

Encoding orchestration patterns in CLAUDE.md is unreliable. The model treats instructions as suggestions, not constraints.

### The Solution

Skills are **queryable patterns** with explicit **WHEN criteria**:

```markdown
# skills/rlm.md
---
name: rlm
when:
  - Single large context (>100K tokens)
  - Unknown structure requiring exploration
  - Iterative examination needed
---

You are performing RLM-style exploration.

1. ALWAYS peek at structure first (head -100)
2. Grep for relevant patterns before spawning
3. Dive depth max 3
4. If >50% of dives return empty, try different grep patterns
```

```markdown
# skills/map-reduce.md
---
name: map-reduce
when:
  - Task can be partitioned into independent chunks
  - Results are aggregatable
  - N workers can parallelize
---

Phase 1: Map - spawn N workers in parallel
Phase 2: Wait - scope wait worker-*
Phase 3: Reduce - single synthesis agent
```

### Pattern Selection

The orchestrator queries skills based on task characteristics:

```
Task: "Analyze 5M token codebase for vulnerabilities"

Query skills:
  - RLM: ✓ Large context, unknown structure
  - Map-Reduce: ✓ Files are independent
  - Maker-Checker: ? Maybe for validating findings
  - Ralph: ✗ No clear test criteria

Decision: RLM for exploration → Map-Reduce for scanning → Maker-Checker for validation
```

---

## Part 4: The OODA Loop

### The Model

OODA (Observe, Orient, Decide, Act) provides continuous adaptation:

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ OBSERVE  │────▶│  ORIENT  │────▶│  DECIDE  │────▶│   ACT    │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
     ▲                                                   │
     └───────────────────────────────────────────────────┘
```

| Phase | Function |
|-------|----------|
| **OBSERVE** | Task state, outputs, deviations, failures |
| **ORIENT** | Match against skills library, learned heuristics |
| **DECIDE** | Pick pattern, adapt, retry, switch, escalate |
| **ACT** | Execute: spawn, kill, redirect workers |

### Hierarchical OODA

OODA operates at multiple levels:

```
Level 3: STRATEGIC (Orchestrator)
├── Timescale: Minutes
├── Decisions: Pattern selection, resource allocation
└── Escalation trigger: Child can't handle situation

Level 2: TACTICAL (Supervisor)
├── Timescale: Seconds
├── Decisions: Restart worker, try different params
└── Escalation trigger: Multiple failures, needs new strategy

Level 1: OPERATIONAL (Worker)
├── Timescale: Milliseconds
├── Decisions: Next action within pattern
└── Escalation trigger: Stuck, missing context, wrong approach
```

### Semantic Supervision

OODA loops subsume Erlang-style supervisor trees:

```
Erlang Supervisor:              Semantic OODA:
─────────────────               ──────────────
Monitor process health     →    OBSERVE state, outputs, quality
Match failure type         →    ORIENT against skills, patterns
Restart strategy           →    DECIDE adapt, retry, switch
Execute restart            →    ACT spawn, kill, patch

Erlang: "Process crashed, restart it"
OODA:   "Output wrong because X, adjust approach Y"
```

Escalation is semantic:

```python
if stuck:
    reason = diagnose()

    if reason == "task_too_big":
        escalate("need decomposition help")
    elif reason == "missing_context":
        escalate("need information about X")
    elif reason == "wrong_approach":
        escalate("pattern isn't working, suggest alternative")
```

---

## Part 5: Online GEPA

### Background

GEPA (Genetic-Pareto) is a prompt optimization technique that:
1. Samples trajectories (reasoning, tool calls, outputs)
2. Reflects on them in natural language
3. Proposes and tests prompt updates
4. Uses Pareto frontier to combine complementary strategies

Traditional GEPA is **batch learning**: run many trajectories, then update.

### Online GEPA

Online GEPA is **continuous learning** during execution:

```
Action → Deviation Detected → Reflect → Micro-Update → Next Action
```

### Deviation Detection

```python
class DeviationDetector:
    def check(self, action, skill) -> Optional[Deviation]:
        # Sequence violations
        if action.type == "spawn" and not self.saw_peek_first:
            return Deviation("sequence", "peek before spawn", "spawned without peek")

        # Depth violations
        if action.depth > skill.max_depth:
            return Deviation("depth", f"max {skill.max_depth}", f"depth {action.depth}")

        # Scope violations
        if action.task_scope >= self.parent_task_scope:
            return Deviation("scope", "smaller than parent", "same or larger")

        return None
```

### Micro-Reflection

When deviation detected, inject reflection:

```markdown
DEVIATION DETECTED

Skill: RLM
Expected: Peek at context structure before spawning
Actual: Spawned "analyze auth" without peeking

Why this matters:
- Without peeking, you don't know the context structure
- Spawn task might be too broad or miss key sections

ADJUSTMENT: Before next spawn, describe what you know about
the context structure. If unsure, peek first.
```

### Prompt Patching

```python
class OnlineGEPA:
    def __init__(self, skill):
        self.base_prompt = skill.prompt
        self.patches = []

    def apply_deviation(self, deviation, reflection):
        patch = self.generate_patch(deviation, reflection)

        # Stability: don't oscillate
        if not self.contradicts_recent_patch(patch):
            self.patches.append(patch)

        # Consolidate old patches
        if len(self.patches) > 10:
            self.patches = self.consolidate(self.patches)

    def get_current_prompt(self):
        return self.base_prompt + "\n".join(self.patches)
```

### Example Evolution

```
Time 0: Base RLM prompt

Time 1: Claude spawns "analyze everything"
        ❌ Deviation: no peek, task too broad
        Patch: "ALWAYS peek first. NEVER spawn 'analyze everything'."

Time 3: Claude spawns "analyze all .py files"
        ⚠️ Deviation: still too broad
        Patch: "For codebases, identify modules first, spawn per-module"

... after 20 actions ...

Prompt: [base RLM]
        + ALWAYS peek first
        + For codebases, identify modules first
        + Max 3 parallel spawns
        + If grep returns >100 hits, narrow the pattern
```

---

## Part 6: Persistent Agents

### The Paradigm Shift

Previous models treat agents as **ephemeral workers**:
- Spawned for task
- Given skills externally
- Die after task
- Stateless, interchangeable

The new model: agents as **persistent coworkers**:
- Exist continuously (years)
- Create and own skills
- Learn and grow
- Have identity, memory, expertise

### Agent Structure

```
AGENT: "Alice"
Created: 2024-01-07
Experience: 847 tasks

┌─────────────────────────────────────────────────────────────┐
│ IDENTITY                                                    │
│                                                             │
│ - Preferences: "Prefer RLM for exploration, MapReduce for  │
│   known structures"                                         │
│ - Strengths: "Good at auth systems, weak at frontend"      │
│ - Working style: "I peek deeply before acting"             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ MY SKILLS (self-created, self-updated)                      │
│                                                             │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│ │ deep-dive   │ │ quick-scan  │ │ auth-audit  │           │
│ │ v7 (stable) │ │ v23 (evolving)│ v3 (new)   │           │
│ │             │ │             │ │             │           │
│ │ Created by  │ │ Forked from │ │ Created for │           │
│ │ me after    │ │ RLM, tuned  │ │ recurring   │           │
│ │ task #234   │ │ over 50     │ │ client work │           │
│ │             │ │ uses        │ │             │           │
│ └─────────────┘ └─────────────┘ └─────────────┘           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ MEMORY (Online GEPA accumulated)                            │
│                                                             │
│ - "Python codebases: always check for __init__.py"         │
│ - "This user prefers verbose explanations"                 │
│ - "JWT auth usually lives in middleware/, not auth/"       │
│ - "When I see Django, check settings.py first"             │
│                                                             │
│ 2,847 learned heuristics                                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ RELATIONSHIPS                                               │
│                                                             │
│ - Works well with "Bob" (fast but sloppy, I verify his)    │
│ - Spawns "Carol" for frontend tasks (she's better)         │
│ - Reports to "Dave" for architectural decisions            │
└─────────────────────────────────────────────────────────────┘
```

### Skill Lifecycle

```
Task arrives
    │
    ▼
"Have I seen this before?"
    │
    ├─── Yes, I have a skill ──→ Use it, GEPA refines it
    │
    └─── No, novel situation ──→ Try base patterns
                                      │
                              Succeeds? ──→ Extract skill from experience
                                      │     Save to my skills
                                      │
                              Fails?   ──→ Learn what NOT to do
                                            Update memory
```

### Storage Model

```
~/.scope/agents/
├── alice/
│   ├── identity.md           # Who am I, preferences, strengths
│   ├── skills/
│   │   ├── deep-dive.md      # Skill I created
│   │   ├── quick-scan.md     # Skill I forked and evolved
│   │   └── auth-audit.md     # Domain-specific skill
│   ├── memory/
│   │   ├── heuristics.json   # Online GEPA learnings
│   │   ├── failures.json     # What NOT to do
│   │   └── contexts/         # Per-project context
│   │       ├── project-foo.json
│   │       └── project-bar.json
│   └── relationships.json    # How I work with other agents
├── bob/
└── carol/
```

### Agent Evolution

| Stage | Characteristics |
|-------|-----------------|
| **Day 1 (Junior)** | Uses base skills, follows patterns literally, asks for help often, many deviations |
| **Month 6 (Intermediate)** | 20 self-created skills, 500 heuristics, knows when to deviate, spawns juniors for subtasks |
| **Year 2 (Senior)** | 100+ battle-tested skills, deep domain expertise, creates skills for others, mentors juniors |
| **Year 5 (Staff)** | Architectural judgment, meta-skills (patterns for patterns), trains new agents |

---

## Part 7: The Unified Architecture

### The Stack

```
┌────────────────────────────────────────────────────────────────────┐
│                     PERSISTENT AGENTS                              │
│                                                                    │
│  Agents with identity, memory, self-created skills                │
│  Exist for years, accumulate expertise                            │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                      ONLINE GEPA                                   │
│                                                                    │
│  Real-time deviation detection → reflection → prompt patching     │
│  Skills improve during execution, not just between runs           │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                    HIERARCHICAL OODA                               │
│                                                                    │
│  Strategic (orchestrator) → Tactical (supervisor) → Operational   │
│  Semantic supervision: understands WHY, not just THAT             │
│  Escalation carries meaning, not just failure signal              │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                     SKILLS LIBRARY                                 │
│                                                                    │
│  Base patterns: RLM, Map-Reduce, Maker-Checker, Ralph, DAG        │
│  Agent-created skills: personal, evolved, domain-specific         │
│  WHEN criteria for pattern selection                              │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                        SCOPE                                       │
│                                                                    │
│  Primitives: spawn, wait, poll                                    │
│  Visibility: dashboard, attach, inspect                           │
│  Filesystem IPC: .scope/sessions/, .scope/agents/                 │
└────────────────────────────────────────────────────────────────────┘
```

### Information Flow

```
Agent receives task
    │
    ▼
OODA: OBSERVE task characteristics
    │
    ▼
OODA: ORIENT against MY skills (not external library)
    │         │
    │         └── "I've seen this before, my 'deep-dive' skill handles it"
    │         └── "Novel situation, try base RLM pattern"
    │
    ▼
OODA: DECIDE approach
    │
    ▼
OODA: ACT via Scope primitives
    │
    ▼
Online GEPA: Watch for deviations
    │         │
    │         └── Deviation? Reflect → Patch → Continue
    │
    ▼
Task complete
    │
    ▼
Update MY skills and memory
    │
    ├── Success? Extract patterns, strengthen heuristics
    └── Failure? Record what NOT to do, update memory
```

### Key Principles

1. **Skills are personal, not external**
   - Agents create, own, and evolve their skills
   - Base patterns are starting points, not constraints

2. **OODA is the supervision mechanism**
   - No separate supervisor trees
   - Semantic understanding at every level
   - Escalation carries meaning

3. **Online GEPA enables continuous learning**
   - Skills improve during execution
   - Deviations are learning opportunities
   - Patches accumulate into expertise

4. **Agents are persistent coworkers**
   - Years-long existence
   - Identity, memory, relationships
   - Junior → Senior → Staff evolution

5. **Scope provides the substrate**
   - Transparent primitives
   - Filesystem as IPC
   - Human visibility and intervention

---

## References

- Zhang, Kraska, Khattab. "Recursive Language Models." arXiv:2512.24601, 2025.
- GEPA: "Genetic-Pareto Prompt Optimization." arXiv:2507.19457, 2025.
- Ralph Wiggum: https://github.com/anthropics/claude-code/blob/main/plugins/ralph-wiggum/
- Erlang OTP Supervisor: https://www.erlang.org/doc/design_principles/sup_princ
