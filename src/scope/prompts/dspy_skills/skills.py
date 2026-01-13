"""DSPy skill signatures for orchestration patterns.

This module provides DSPy signatures for each of the 6 orchestration skills:
- ralph: Iterative refinement loops
- tdd: Test-driven development
- rlm: Large context exploration
- map-reduce: Parallel tasks with aggregation
- maker-checker: Independent validation
- dag: Dependency graph execution

Each signature defines typed InputFields and OutputFields that can be
optimized using DSPy's optimization techniques (BootstrapFewShot, MIPRO).
"""

from typing import Literal

import dspy


class RalphSignature(dspy.Signature):
    """Iterative refinement loop: Critique -> Evaluate -> Act -> Repeat.

    RALPH implements convergent optimization toward a goal through
    iterative critique cycles. Each iteration evaluates the current
    state against the goal, generates targeted critique, and applies
    improvements until the goal is met or delta becomes negligible.

    Use for: Quality improvement, polish/editing tasks, convergent
    optimization, or any task requiring iterative refinement.
    """

    current_state: str = dspy.InputField(
        desc="The current artifact or output being refined (code, text, plan, etc.)"
    )
    goal: str = dspy.InputField(
        desc="What 'done' looks like - the target state or quality criteria to achieve"
    )
    max_iterations: int = dspy.InputField(
        desc="Maximum number of critique-improve cycles before stopping (default: 5)"
    )
    delta_threshold: float = dspy.InputField(
        desc="Minimum improvement required to continue; stop if delta falls below this"
    )

    refined_output: str = dspy.OutputField(
        desc="The improved artifact after applying critique and refinements"
    )
    critique: str = dspy.OutputField(
        desc="Evaluation of current state against goal, identifying gaps and improvements"
    )
    should_continue: bool = dspy.OutputField(
        desc="Whether to continue iterating (False if goal met or delta < threshold)"
    )
    iterations_used: int = dspy.OutputField(
        desc="Number of iterations actually performed before stopping"
    )
    stop_reason: str = dspy.OutputField(
        desc="Why refinement stopped: goal_met, delta_negligible, or max_iterations_reached"
    )


class TDDSignature(dspy.Signature):
    """Test-driven development: Red -> Green -> Refactor.

    TDD ensures code correctness by writing tests before implementation.
    The cycle is: write a failing test (Red), write minimal code to
    pass it (Green), then clean up while keeping tests green (Refactor).

    Use for: New feature implementation, bug fixes requiring regression
    tests, or any code change needing test coverage.
    """

    feature_description: str = dspy.InputField(
        desc="Natural language description of the feature or behavior to implement"
    )
    existing_code: str = dspy.InputField(
        desc="Current codebase context relevant to the feature (may be empty for new features)"
    )
    test_framework: str = dspy.InputField(
        desc="Testing framework to use (e.g., pytest, jest, go test)"
    )

    test_code: str = dspy.OutputField(
        desc="Failing test(s) that define the expected behavior - written BEFORE implementation"
    )
    implementation_code: str = dspy.OutputField(
        desc="Minimal code to make the test(s) pass - no more, no less"
    )
    refactored_code: str = dspy.OutputField(
        desc="Cleaned up implementation with improved structure while keeping tests green"
    )
    test_results: str = dspy.OutputField(
        desc="Output from running tests at each stage (Red -> Green -> Green)"
    )


class RLMSignature(dspy.Signature):
    """Recursive language model exploration: Peek -> Grep -> Dive.

    RLM handles large context exploration without flooding the context
    window. It uses a hierarchical approach: peek at structure first,
    narrow with pattern matching, then spawn focused subagents for
    specific sections.

    Use for: Large codebases (>100K tokens), unknown codebase structure,
    finding needles in haystacks, or iterative examination of unfamiliar content.
    """

    target_content: str = dspy.InputField(
        desc="The large content to explore (file path, codebase description, or content identifier)"
    )
    search_goal: str = dspy.InputField(
        desc="What information is being sought (e.g., 'find authentication logic')"
    )
    max_dive_depth: int = dspy.InputField(
        desc="Maximum recursion depth for subagent spawns (default: 3)"
    )

    structure_overview: str = dspy.OutputField(
        desc="High-level structure discovered during peek phase (sections, files, patterns)"
    )
    search_patterns: list[str] = dspy.OutputField(
        desc="Grep patterns used to narrow down locations of interest"
    )
    dive_targets: list[str] = dspy.OutputField(
        desc="Specific sections or files identified for deep analysis"
    )
    findings: str = dspy.OutputField(
        desc="Synthesized results from exploration - the answer to the search goal"
    )
    exploration_path: str = dspy.OutputField(
        desc="Trace of peek -> grep -> dive steps taken during exploration"
    )


class MapReduceSignature(dspy.Signature):
    """Parallel workers with aggregation: Fork N -> Wait All -> Reduce.

    Map-Reduce parallelizes independent work across N workers, then
    synthesizes results. Workers must be independent (no shared state)
    and each receives a specific, bounded chunk of work.

    Use for: File-by-file analysis, aggregatable results across chunks,
    or when N workers can process simultaneously without dependencies.
    """

    task_description: str = dspy.InputField(
        desc="Overall task to be distributed across workers"
    )
    input_chunks: list[str] = dspy.InputField(
        desc="List of independent work items to distribute (files, data chunks, etc.)"
    )
    worker_instructions: str = dspy.InputField(
        desc="Instructions for each worker on how to process their chunk"
    )
    aggregation_strategy: str = dspy.InputField(
        desc="How to combine worker outputs (e.g., concatenate, merge, vote, summarize)"
    )

    worker_outputs: list[str] = dspy.OutputField(
        desc="Results from each worker, indexed to match input_chunks"
    )
    worker_statuses: list[str] = dspy.OutputField(
        desc="Status of each worker: success, failed, or skipped"
    )
    reduced_output: str = dspy.OutputField(
        desc="Final synthesized result after applying aggregation strategy"
    )
    failed_chunks: list[str] = dspy.OutputField(
        desc="List of chunks that failed processing (for retry or investigation)"
    )


class MakerCheckerSignature(dspy.Signature):
    """Separation of creation and validation: One makes, another validates.

    Maker-Checker ensures quality through independent validation.
    The maker creates an artifact, then a separate checker (with fresh
    context and no maker bias) validates against defined criteria.

    Use for: Security-sensitive code, critical outputs needing review,
    or any work requiring separation of creation and verification.
    """

    artifact_request: str = dspy.InputField(
        desc="Description of the artifact to create (code, plan, analysis, etc.)"
    )
    validation_criteria: list[str] = dspy.InputField(
        desc="Specific criteria the checker will use to validate the artifact"
    )
    max_iterations: int = dspy.InputField(
        desc="Maximum maker-checker cycles before accepting or failing (default: 3)"
    )

    artifact: str = dspy.OutputField(
        desc="The created artifact from the maker agent"
    )
    validation_result: Literal["approved", "rejected", "needs_revision"] = dspy.OutputField(
        desc="Checker's verdict on the artifact quality"
    )
    checker_feedback: str = dspy.OutputField(
        desc="Detailed feedback from checker, including issues found and suggestions"
    )
    revision_history: list[str] = dspy.OutputField(
        desc="Log of revisions made across iterations based on checker feedback"
    )
    final_status: Literal["approved", "rejected_max_iterations", "rejected_unfixable"] = dspy.OutputField(
        desc="Final outcome after all iterations complete"
    )


class DAGSignature(dspy.Signature):
    """Dependency graph execution: Tasks with ordered dependencies.

    DAG orchestrates complex workflows where tasks have dependencies.
    Tasks without dependencies start immediately; tasks with --after
    wait for their dependencies to complete. Enables partial parallelism
    where independent branches execute simultaneously.

    Use for: Build pipelines requiring ordered execution, complex
    orchestration with partial parallelism, or any workflow with
    task interdependencies.
    """

    workflow_description: str = dspy.InputField(
        desc="Natural language description of the workflow to execute"
    )
    tasks: list[str] = dspy.InputField(
        desc="List of task descriptions to execute in the workflow"
    )
    dependencies: dict[str, list[str]] = dspy.InputField(
        desc="Mapping of task_id -> [dependency_ids] defining execution order"
    )

    task_ids: list[str] = dspy.OutputField(
        desc="Generated descriptive IDs assigned to each task"
    )
    execution_order: list[list[str]] = dspy.OutputField(
        desc="Tasks grouped by execution wave (parallel within wave, sequential across)"
    )
    task_outputs: dict[str, str] = dspy.OutputField(
        desc="Mapping of task_id -> output for each completed task"
    )
    task_statuses: dict[str, str] = dspy.OutputField(
        desc="Mapping of task_id -> status (completed, failed, skipped_dep_failed)"
    )
    workflow_result: str = dspy.OutputField(
        desc="Final synthesized result of the entire workflow"
    )


# Factory functions for creating skill modules


def create_ralph() -> dspy.Module:
    """Create a RALPH iterative refinement module."""
    return dspy.Predict(RalphSignature)


def create_tdd() -> dspy.Module:
    """Create a TDD test-driven development module."""
    return dspy.Predict(TDDSignature)


def create_rlm() -> dspy.Module:
    """Create an RLM large context exploration module."""
    return dspy.Predict(RLMSignature)


def create_map_reduce() -> dspy.Module:
    """Create a Map-Reduce parallel worker module."""
    return dspy.Predict(MapReduceSignature)


def create_maker_checker() -> dspy.Module:
    """Create a Maker-Checker validation module."""
    return dspy.Predict(MakerCheckerSignature)


def create_dag() -> dspy.Module:
    """Create a DAG dependency graph execution module."""
    return dspy.Predict(DAGSignature)


# Mapping of skill names to their signature classes
SKILL_SIGNATURES = {
    "ralph": RalphSignature,
    "tdd": TDDSignature,
    "rlm": RLMSignature,
    "map-reduce": MapReduceSignature,
    "maker-checker": MakerCheckerSignature,
    "dag": DAGSignature,
}

# Mapping of skill names to their factory functions
SKILL_FACTORIES = {
    "ralph": create_ralph,
    "tdd": create_tdd,
    "rlm": create_rlm,
    "map-reduce": create_map_reduce,
    "maker-checker": create_maker_checker,
    "dag": create_dag,
}
