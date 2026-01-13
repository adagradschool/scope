---
name: maker-checker
description: High-stakes work needing independent validation. Use for security-sensitive code, critical outputs needing review, or separation of creation and verification.
---

# Maker-Checker: Separation of Concerns

One makes, another validates. Never self-review.

## Roles
- **Maker**: Creates the artifact (code, plan, analysis)
- **Checker**: Reviews, critiques, validates independently

## Workflow
```
# Maker creates
scope spawn "Create: {artifact_description}"
scope wait

# Checker validates (fresh context, no maker bias)
scope spawn "Review: validate {artifact}, check for {criteria}"
scope wait

# If checker finds issues, iterate
scope spawn "Fix: address these issues: {checker_feedback}"
scope wait
```

## Rules
- Maker and checker MUST be separate agents (fresh context)
- Checker never sees maker's reasoning, only output
- Define validation criteria upfront
- Iterate until checker approves or max iterations hit
- For critical work: use different models (maker=fast, checker=thorough)
