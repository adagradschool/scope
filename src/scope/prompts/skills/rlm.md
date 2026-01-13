---
name: rlm
description: Large context exploration. Use when exploring large codebases (>100K tokens), unknown codebase structure, finding needles in haystacks, or iterative examination of unfamiliar content.
---

# RLM: Recursive Language Model Exploration

Peek → Grep → Dive. Explore large contexts without flooding your window.

## Pattern
1. **Peek**: Inspect structure first (head, tail, outline)
2. **Grep**: Narrow search with patterns before diving deep
3. **Dive**: Spawn subagents for focused analysis of specific sections

## Workflow
```
# 1. Peek at structure
Read first 100 lines, check file structure, identify sections

# 2. Grep to locate
Search for relevant patterns before spawning

# 3. Dive on specific targets
scope spawn "Analyze {specific_section} in {file}"
scope wait
```

## Rules
- ALWAYS peek before spawning - understand structure first
- Use grep to narrow, don't spawn "analyze everything"
- Max dive depth: 3 levels
- Each dive must be smaller scope than parent
- If >50% of dives return empty, try different patterns
