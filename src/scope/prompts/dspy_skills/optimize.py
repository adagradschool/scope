"""Training data collection and DSPy optimization for skill routing.

This module provides:
1. TrainingDataCollector - Extracts skill invocations and outcomes from trajectory files
2. SkillOptimizer - Runs BootstrapFewShot, MIPROv2, or GEPA optimization on the SkillRouter

Training data is collected from ~/.scope/sessions/*/trajectory.jsonl files,
where session.state=='done' indicates successful completion (positive examples).

Optimization Strategies:
- bootstrap: Fast, simple few-shot example selection
- mipro: Multi-step instruction proposal and optimization
- gepa: Reflective prompt evolution with textual feedback (best quality, fewer rollouts)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import dspy
import orjson

from scope.core.project import get_global_scope_base
from scope.core.state import load_all, load_trajectory
from scope.prompts.dspy_skills import SkillRouter, create_router


@dataclass
class SkillInvocation:
    """A single skill invocation extracted from a trajectory."""

    session_id: str
    task_description: str
    skill_name: str
    outcome: Literal["success", "failure", "unknown"]
    trajectory_length: int = 0


@dataclass
class TrainingDataset:
    """Collection of training examples for skill optimization."""

    examples: list[dspy.Example] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.examples)

    def split(
        self, train_ratio: float = 0.8
    ) -> tuple["TrainingDataset", "TrainingDataset"]:
        """Split dataset into train and validation sets."""
        split_idx = int(len(self.examples) * train_ratio)
        train = TrainingDataset(
            examples=self.examples[:split_idx],
            metadata={"split": "train", "parent": self.metadata},
        )
        val = TrainingDataset(
            examples=self.examples[split_idx:],
            metadata={"split": "validation", "parent": self.metadata},
        )
        return train, val


class TrainingDataCollector:
    """Collects training data from scope session trajectories.

    Reads trajectory.jsonl files from completed sessions and extracts
    skill invocations with their outcomes. Sessions with state='done'
    are treated as successful completions.

    Example:
        ```python
        collector = TrainingDataCollector()
        dataset = collector.collect()
        print(f"Collected {len(dataset)} training examples")
        ```
    """

    # Known skill names to look for in trajectories
    SKILL_NAMES = {"ralph", "tdd", "rlm", "map-reduce", "maker-checker", "dag"}

    def __init__(self, scope_base: Path | None = None):
        """Initialize collector.

        Args:
            scope_base: Base scope directory. If None, uses get_global_scope_base().
        """
        self.scope_base = scope_base or get_global_scope_base()

    def collect(self, min_examples: int = 0) -> TrainingDataset:
        """Collect training examples from all completed sessions.

        Args:
            min_examples: Minimum number of examples required. If not met,
                         returns empty dataset with warning in metadata.

        Returns:
            TrainingDataset with examples and collection metadata.
        """
        invocations = self._extract_all_invocations()
        examples = self._invocations_to_examples(invocations)

        metadata = {
            "total_sessions_scanned": len(load_all()),
            "total_invocations": len(invocations),
            "successful_invocations": sum(
                1 for i in invocations if i.outcome == "success"
            ),
            "failed_invocations": sum(1 for i in invocations if i.outcome == "failure"),
            "skill_distribution": self._compute_skill_distribution(invocations),
        }

        if len(examples) < min_examples:
            metadata["warning"] = (
                f"Only {len(examples)} examples found, minimum {min_examples} required"
            )

        return TrainingDataset(examples=examples, metadata=metadata)

    def _extract_all_invocations(self) -> list[SkillInvocation]:
        """Extract skill invocations from all sessions."""
        invocations = []

        for session in load_all():
            session_invocations = self._extract_from_session(session.id, session.state)
            invocations.extend(session_invocations)

        return invocations

    def _extract_from_session(
        self, session_id: str, session_state: str
    ) -> list[SkillInvocation]:
        """Extract skill invocations from a single session's trajectory.

        Args:
            session_id: The session ID to extract from.
            session_state: The session's final state (done, failed, etc.)

        Returns:
            List of SkillInvocation objects found in the trajectory.
        """
        trajectory = load_trajectory(session_id)
        if trajectory is None:
            return []

        invocations = []
        outcome: Literal["success", "failure", "unknown"] = (
            "success" if session_state == "done" else "failure"
        )

        # Look for skill invocations in user messages
        for entry in trajectory:
            if entry.get("type") != "user":
                continue

            message = entry.get("message", {})
            content = message.get("content", "")

            # Handle content that may be a list (tool results)
            if isinstance(content, list):
                continue

            # Check for /skill_name pattern or skill invocations
            skill_name = self._detect_skill_in_content(content)
            if skill_name:
                # Extract task description from the content
                task_desc = self._extract_task_description(content, skill_name)
                if task_desc:
                    invocations.append(
                        SkillInvocation(
                            session_id=session_id,
                            task_description=task_desc,
                            skill_name=skill_name,
                            outcome=outcome,
                            trajectory_length=len(trajectory),
                        )
                    )

        return invocations

    def _detect_skill_in_content(self, content: str) -> str | None:
        """Detect if content contains a skill invocation.

        Looks for patterns like:
        - /ralph, /tdd, /rlm, etc.
        - Skill tool invocations
        """
        content_lower = content.lower()

        # Check for /skill_name patterns
        for skill in self.SKILL_NAMES:
            if f"/{skill}" in content_lower:
                return skill

        # Check for Skill tool usage mentioning a skill
        if "skill" in content_lower:
            for skill in self.SKILL_NAMES:
                if skill in content_lower:
                    return skill

        return None

    def _extract_task_description(self, content: str, skill_name: str) -> str | None:
        """Extract the task description from content that invoked a skill.

        The task description is typically what follows the skill invocation,
        or can be found in the surrounding context.
        """
        # Try to find content after the skill invocation
        content_lower = content.lower()
        skill_pattern = f"/{skill_name}"

        idx = content_lower.find(skill_pattern)
        if idx != -1:
            # Get content after the skill name
            after_skill = content[idx + len(skill_pattern) :].strip()
            # Take the first meaningful line or sentence
            lines = after_skill.split("\n")
            for line in lines:
                line = line.strip()
                if line and len(line) > 10:  # Meaningful content
                    # Truncate at reasonable length
                    return line[:500]

        # Fall back to using the entire content (truncated)
        if len(content) > 50:
            return content[:500]

        return None

    def _invocations_to_examples(
        self, invocations: list[SkillInvocation]
    ) -> list[dspy.Example]:
        """Convert invocations to DSPy Examples.

        Only includes successful invocations as positive examples.
        """
        examples = []

        for inv in invocations:
            if inv.outcome != "success":
                continue

            example = dspy.Example(
                task_description=inv.task_description, skill_name=inv.skill_name
            ).with_inputs("task_description")

            examples.append(example)

        return examples

    def _compute_skill_distribution(
        self, invocations: list[SkillInvocation]
    ) -> dict[str, int]:
        """Compute the distribution of skills in the invocations."""
        distribution: dict[str, int] = {}
        for inv in invocations:
            distribution[inv.skill_name] = distribution.get(inv.skill_name, 0) + 1
        return distribution


class SkillOptimizer:
    """Optimizes the SkillRouter using DSPy optimization techniques.

    Supports BootstrapFewShot, MIPROv2, and GEPA optimization strategies.
    Takes training examples and produces an optimized router that can
    be saved and loaded for production use.

    Example:
        ```python
        import dspy

        # Configure LM
        dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-4-20250514"))

        # Collect training data
        collector = TrainingDataCollector()
        dataset = collector.collect()

        # Optimize with GEPA (recommended for best quality)
        optimizer = SkillOptimizer()
        optimized_router = optimizer.optimize(
            dataset,
            strategy="gepa",
            reflection_lm=dspy.LM("openai/gpt-4", temperature=1.0),
        )

        # Save for production
        optimizer.save(optimized_router, "optimized_router.json")
        ```
    """

    def __init__(self):
        """Initialize the optimizer."""
        self.base_router = create_router()

    def optimize(
        self,
        dataset: TrainingDataset,
        strategy: Literal["bootstrap", "mipro", "gepa"] = "bootstrap",
        max_bootstrapped_demos: int = 4,
        max_labeled_demos: int = 8,
        num_threads: int = 4,
        # GEPA-specific parameters
        reflection_lm: dspy.LM | None = None,
        gepa_auto: Literal["light", "medium", "heavy"] | None = None,
        max_metric_calls: int | None = None,
    ) -> dspy.Module:
        """Run optimization on the SkillRouter.

        Args:
            dataset: Training dataset with examples.
            strategy: Optimization strategy:
                - "bootstrap": BootstrapFewShot (fast, simple)
                - "mipro": MIPROv2 (multi-step instruction optimization)
                - "gepa": GEPA reflective evolution (best quality, fewer rollouts)
            max_bootstrapped_demos: Max demos for BootstrapFewShot.
            max_labeled_demos: Max labeled demos for MIPROv2.
            num_threads: Number of threads for parallel evaluation.
            reflection_lm: LM for GEPA reflection (required for gepa strategy).
                          Recommended: strong model like GPT-4 with temperature=1.0
            gepa_auto: GEPA budget preset - "light", "medium", or "heavy".
                      Mutually exclusive with max_metric_calls.
            max_metric_calls: Max metric evaluations for GEPA.
                             Mutually exclusive with gepa_auto. Default: 500 if neither set.

        Returns:
            Optimized dspy.Module (SkillRouter with learned prompts).

        Raises:
            ValueError: If dataset is empty, strategy is invalid, or GEPA
                       requirements not met.
        """
        if len(dataset) == 0:
            raise ValueError("Cannot optimize with empty dataset")

        # Split into train/validation
        train_set, val_set = dataset.split(train_ratio=0.8)

        if strategy == "bootstrap":
            return self._bootstrap_optimize(
                train_set.examples,
                val_set.examples,
                max_bootstrapped_demos=max_bootstrapped_demos,
                num_threads=num_threads,
            )
        elif strategy == "mipro":
            return self._mipro_optimize(
                train_set.examples,
                val_set.examples,
                max_labeled_demos=max_labeled_demos,
                num_threads=num_threads,
            )
        elif strategy == "gepa":
            return self._gepa_optimize(
                train_set.examples,
                val_set.examples,
                reflection_lm=reflection_lm,
                auto=gepa_auto,
                max_metric_calls=max_metric_calls,
                num_threads=num_threads,
            )
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def _bootstrap_optimize(
        self,
        trainset: list[dspy.Example],
        valset: list[dspy.Example],
        max_bootstrapped_demos: int,
        num_threads: int,
    ) -> dspy.Module:
        """Run BootstrapFewShot optimization."""
        optimizer = dspy.BootstrapFewShot(
            metric=self._skill_match_metric,
            max_bootstrapped_demos=max_bootstrapped_demos,
            max_labeled_demos=max_bootstrapped_demos,
        )

        optimized = optimizer.compile(
            self.base_router,
            trainset=trainset,
        )

        return optimized

    def _mipro_optimize(
        self,
        trainset: list[dspy.Example],
        valset: list[dspy.Example],
        max_labeled_demos: int,
        num_threads: int,
    ) -> dspy.Module:
        """Run MIPROv2 optimization."""
        optimizer = dspy.MIPROv2(
            metric=self._skill_match_metric,
            num_threads=num_threads,
            max_labeled_demos=max_labeled_demos,
        )

        optimized = optimizer.compile(
            self.base_router,
            trainset=trainset,
            valset=valset,
        )

        return optimized

    def _gepa_optimize(
        self,
        trainset: list[dspy.Example],
        valset: list[dspy.Example],
        reflection_lm: dspy.LM | None,
        auto: Literal["light", "medium", "heavy"] | None,
        max_metric_calls: int | None,
        num_threads: int,
    ) -> dspy.Module:
        """Run GEPA reflective optimization.

        GEPA (Genetic-Pareto) uses LM reflection to evolve prompts, achieving
        better results with fewer rollouts than traditional optimization.
        """
        if reflection_lm is None:
            raise ValueError(
                "GEPA requires a reflection_lm. "
                "Recommended: dspy.LM('openai/gpt-4', temperature=1.0)"
            )

        # GEPA requires exactly one budget parameter
        if auto is None and max_metric_calls is None:
            max_metric_calls = 500  # sensible default

        optimizer = dspy.GEPA(
            metric=self._skill_match_metric_with_feedback,
            reflection_lm=reflection_lm,
            auto=auto,
            max_metric_calls=max_metric_calls,
            num_threads=num_threads,
            reflection_minibatch_size=3,
            candidate_selection_strategy="pareto",
        )

        optimized = optimizer.compile(
            self.base_router,
            trainset=trainset,
            valset=valset,
        )

        return optimized

    @staticmethod
    def _skill_match_metric(
        example: dspy.Example, pred: dspy.Prediction, trace: list | None = None
    ) -> bool:
        """Metric for evaluating skill routing accuracy.

        Returns True if predicted skill matches the expected skill.
        """
        return example.skill_name == pred.skill_name

    @staticmethod
    def _skill_match_metric_with_feedback(
        gold: dspy.Example,
        pred: dspy.Prediction,
        trace: list | None = None,
        pred_name: str | None = None,
        pred_trace: list | None = None,
    ) -> tuple[float, str]:
        """GEPA-compatible metric with textual feedback.

        Returns (score, feedback) tuple where feedback guides GEPA's reflection.
        """
        expected = gold.skill_name
        predicted = getattr(pred, "skill_name", None)

        if predicted == expected:
            return (1.0, f"Correct: routed to '{expected}'")

        # Provide detailed feedback for GEPA reflection
        task_preview = gold.task_description[:100] + "..." if len(gold.task_description) > 100 else gold.task_description
        feedback = (
            f"Incorrect routing. Expected '{expected}' but got '{predicted}'. "
            f"Task: '{task_preview}'. "
            f"Consider patterns that distinguish '{expected}' from '{predicted}'."
        )
        return (0.0, feedback)

    def save(self, optimized_router: dspy.Module, path: str | Path) -> None:
        """Save an optimized router to disk.

        Args:
            optimized_router: The optimized router module.
            path: Path to save the router JSON file.
        """
        path = Path(path)
        optimized_router.save(str(path))

    def load(self, path: str | Path) -> dspy.Module:
        """Load an optimized router from disk.

        Args:
            path: Path to the saved router JSON file.

        Returns:
            The loaded optimized router module.
        """
        path = Path(path)
        router = create_router()
        router.load(str(path))
        return router

    def export_to_markdown(
        self, optimized_router: dspy.Module, output_dir: Path | None = None
    ) -> dict[str, str]:
        """Export optimized prompts back to markdown format.

        Extracts the learned few-shot examples and instructions from the
        optimized router and formats them as markdown that can be used
        to update the skill prompt files.

        Args:
            optimized_router: The optimized router module.
            output_dir: Optional directory to write markdown files.

        Returns:
            Dictionary mapping skill names to their optimized prompt content.
        """
        # Extract demos from the optimized router
        demos = getattr(optimized_router, "demos", [])

        # Group demos by skill
        skill_demos: dict[str, list[dspy.Example]] = {}
        for demo in demos:
            skill = getattr(demo, "skill_name", None)
            if skill:
                if skill not in skill_demos:
                    skill_demos[skill] = []
                skill_demos[skill].append(demo)

        # Generate markdown for each skill with examples
        markdown_outputs: dict[str, str] = {}

        for skill_name, examples in skill_demos.items():
            md_content = self._generate_skill_markdown(skill_name, examples)
            markdown_outputs[skill_name] = md_content

            if output_dir:
                output_file = output_dir / f"{skill_name}_optimized.md"
                output_file.write_text(md_content)

        return markdown_outputs

    def _generate_skill_markdown(
        self, skill_name: str, examples: list[dspy.Example]
    ) -> str:
        """Generate markdown content for a skill with optimized examples."""
        lines = [
            f"# {skill_name.upper()} - Optimized Examples",
            "",
            "These examples were automatically selected by DSPy optimization",
            "to improve skill routing accuracy.",
            "",
            "## Examples",
            "",
        ]

        for i, example in enumerate(examples, 1):
            task = getattr(example, "task_description", "N/A")
            reasoning = getattr(example, "reasoning", "")

            lines.append(f"### Example {i}")
            lines.append(f"**Task:** {task}")
            if reasoning:
                lines.append(f"**Reasoning:** {reasoning}")
            lines.append("")

        return "\n".join(lines)


def collect_training_data(min_examples: int = 10) -> TrainingDataset:
    """Convenience function to collect training data.

    Args:
        min_examples: Minimum number of examples required.

    Returns:
        TrainingDataset ready for optimization.
    """
    collector = TrainingDataCollector()
    return collector.collect(min_examples=min_examples)


def optimize_skill_router(
    dataset: TrainingDataset,
    strategy: Literal["bootstrap", "mipro", "gepa"] = "bootstrap",
    output_path: str | Path | None = None,
    reflection_lm: dspy.LM | None = None,
    gepa_auto: Literal["light", "medium", "heavy"] | None = None,
) -> dspy.Module:
    """Convenience function to optimize the skill router.

    Args:
        dataset: Training dataset from collect_training_data().
        strategy: Optimization strategy ("bootstrap", "mipro", or "gepa").
        output_path: Optional path to save the optimized router.
        reflection_lm: LM for GEPA reflection (required for gepa strategy).
        gepa_auto: GEPA budget preset ("light", "medium", "heavy").

    Returns:
        Optimized SkillRouter module.

    Example with GEPA:
        ```python
        import dspy

        dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-4-20250514"))
        dataset = collect_training_data()

        optimized = optimize_skill_router(
            dataset,
            strategy="gepa",
            reflection_lm=dspy.LM("openai/gpt-4", temperature=1.0),
            gepa_auto="medium",
            output_path="optimized_router.json",
        )
        ```
    """
    optimizer = SkillOptimizer()
    optimized = optimizer.optimize(
        dataset,
        strategy=strategy,
        reflection_lm=reflection_lm,
        gepa_auto=gepa_auto,
    )

    if output_path:
        optimizer.save(optimized, output_path)

    return optimized
