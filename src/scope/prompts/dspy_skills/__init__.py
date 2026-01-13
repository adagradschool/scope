"""DSPy-based skill signatures for optimizable prompt routing.

This module provides DSPy signatures for skill selection and routing.
DSPy enables automatic prompt optimization through techniques like:

1. **Bootstrap Few-Shot**: Automatically generates and selects the best
   few-shot examples from a training set based on a metric.

2. **MIPRO (Mixed-Initiative Prompt Optimization)**: Optimizes both the
   instruction text and few-shot examples jointly.

3. **Signature Optimization**: Tunes the natural language descriptions
   in signatures to improve task performance.

Optimization Strategy:
----------------------
The SkillRouter signature is designed to be optimized with labeled examples
of (task_description, skill_name) pairs. The optimization process:

1. Collect a dataset of task descriptions and their correct skill assignments
2. Define a metric (e.g., exact match accuracy on skill_name)
3. Use `dspy.BootstrapFewShot` or `dspy.MIPROv2` to find optimal prompts
4. The optimized router can then be saved and loaded for production use

Example optimization workflow:
    ```python
    import dspy
    from scope.prompts.dspy_skills import SkillRouter

    # Configure LM
    lm = dspy.LM("anthropic/claude-sonnet-4-20250514")
    dspy.configure(lm=lm)

    # Create training data
    trainset = [
        dspy.Example(
            task_description="Iteratively improve this essay",
            skill_name="ralph"
        ).with_inputs("task_description"),
        # ... more examples
    ]

    # Define metric
    def skill_match(example, pred, trace=None):
        return example.skill_name == pred.skill_name

    # Optimize
    optimizer = dspy.BootstrapFewShot(metric=skill_match, max_bootstrapped_demos=4)
    optimized_router = optimizer.compile(SkillRouter(), trainset=trainset)

    # Save for production
    optimized_router.save("optimized_skill_router.json")
    ```
"""

from typing import Literal

import dspy


# Skill type for routing decisions
SkillName = Literal["ralph", "tdd", "rlm", "map-reduce", "maker-checker", "dag", "none"]

SKILL_DESCRIPTIONS = {
    "ralph": "Iterative refinement loops for improving outputs through critique cycles",
    "tdd": "Test-driven development for code changes requiring test coverage",
    "rlm": "Large context exploration for codebases >100K tokens",
    "map-reduce": "Parallel independent tasks with aggregation",
    "maker-checker": "High-stakes work needing independent validation",
    "dag": "Multi-step workflows with task dependencies",
    "none": "Simple tasks not requiring orchestration patterns",
}


class SkillSignature(dspy.Signature):
    """Base signature for skill-related DSPy modules.

    This provides a common foundation for skill signatures with:
    - Consistent field naming conventions
    - Shared docstring patterns for optimization
    - Type hints compatible with DSPy's optimization

    Subclasses should define their own input/output fields while
    maintaining compatibility with the skill routing infrastructure.

    Optimization Notes:
    ------------------
    When creating custom skill signatures, include detailed docstrings
    on fields as these are used by DSPy during prompt optimization.
    The optimizer may rewrite these descriptions to improve performance.
    """

    pass


class SkillRouter(dspy.Signature):
    """Route a task description to the most appropriate orchestration skill.

    Given a description of a task, determine which orchestration pattern
    (if any) would be most effective for completing it. Consider:

    - ralph: Iterative refinement through critique cycles (polish, editing)
    - tdd: Test-driven development (new features, bug fixes with tests)
    - rlm: Large context exploration (>100K tokens, unfamiliar codebases)
    - map-reduce: Parallel independent work (file-by-file analysis)
    - maker-checker: Independent validation (security-sensitive, critical code)
    - dag: Ordered task dependencies (build pipelines, complex orchestration)
    - none: Simple tasks not needing orchestration patterns

    Optimization Strategy:
    ---------------------
    This signature is optimized using labeled (task, skill) pairs.
    The reasoning field enables chain-of-thought which improves accuracy
    on ambiguous cases. During optimization, DSPy will:

    1. Generate candidate few-shot examples from training data
    2. Score them based on downstream skill selection accuracy
    3. Select the best demonstrations for the final prompt

    The `reasoning` output field is crucial for optimization as it
    provides interpretable intermediate steps that can be evaluated.
    """

    task_description: str = dspy.InputField(
        desc="A natural language description of the task to be performed"
    )

    reasoning: str = dspy.OutputField(
        desc="Step-by-step analysis of which orchestration pattern fits this task"
    )

    skill_name: SkillName = dspy.OutputField(
        desc="The selected skill: ralph, tdd, rlm, map-reduce, maker-checker, dag, or none"
    )


def create_router() -> dspy.Module:
    """Create a SkillRouter module ready for use or optimization.

    Returns:
        A dspy.Predict module wrapping the SkillRouter signature.

    Example:
        ```python
        import dspy

        dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-4-20250514"))
        router = create_router()

        result = router(task_description="Refactor this code to be more readable")
        print(f"Skill: {result.skill_name}")
        print(f"Reasoning: {result.reasoning}")
        ```
    """
    return dspy.Predict(SkillRouter)


def load_optimized_router(path: str) -> dspy.Module:
    """Load a previously optimized SkillRouter from disk.

    Args:
        path: Path to the saved optimized router JSON file.

    Returns:
        The loaded dspy.Predict module with optimized prompts.

    Example:
        ```python
        router = load_optimized_router("optimized_skill_router.json")
        result = router(task_description="Add unit tests for the auth module")
        ```
    """
    router = dspy.Predict(SkillRouter)
    router.load(path)
    return router
