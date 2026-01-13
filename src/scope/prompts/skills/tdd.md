---
name: tdd
description: Test-driven development. Use for new feature implementation, bug fixes requiring regression tests, or any code change needing test coverage.
---

# TDD: Test-Driven Development

Red → Green → Refactor. Tests first, always.

## Cycle
1. **Red**: Write a failing test for the next piece of functionality
2. **Green**: Write minimal code to make it pass
3. **Refactor**: Clean up while keeping tests green

## Workflow
```
scope spawn "Write failing test for: {feature}"
scope wait

scope spawn "Implement minimal code to pass the test"
scope wait

scope spawn "Refactor: clean up implementation, ensure tests pass"
scope wait
```

## Rules
- Never write implementation before the test exists
- Each test should fail for the right reason before you fix it
- Keep cycles small: one behavior per test
- Run tests after every change
- Refactor only when green
