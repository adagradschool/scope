"""Prompt loading utilities for scope.

This module provides functions to load prompt content from the prompts directory,
enabling data-driven iteration on prompt content without code changes.

It also exports DSPy-based modules for optimizable skill routing:
- SkillRouter: DSPy signature for routing tasks to orchestration patterns
- create_router: Factory function for creating a router module
- load_optimized_router: Load a previously optimized router from disk
- SKILL_DESCRIPTIONS: Mapping of skill names to their descriptions
"""

from functools import lru_cache
from importlib import resources

# DSPy exports (lazy import to avoid hard dependency)
from scope.prompts.dspy_skills import (
    SKILL_DESCRIPTIONS,
    SkillRouter,
    create_router,
    load_optimized_router,
)

__all__ = [
    # Markdown loaders
    "load_skill",
    "load_command",
    "list_skills",
    "get_all_skills",
    # DSPy modules
    "SkillRouter",
    "create_router",
    "load_optimized_router",
    "SKILL_DESCRIPTIONS",
]


@lru_cache(maxsize=None)
def load_skill(name: str) -> str:
    """Load a skill prompt by name.

    Args:
        name: The skill name (e.g., 'ralph', 'tdd', 'map-reduce')

    Returns:
        The full content of the skill markdown file.

    Raises:
        FileNotFoundError: If the skill file doesn't exist.
    """
    ref = resources.files("scope.prompts.skills").joinpath(f"{name}.md")
    return ref.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def load_command(name: str) -> str:
    """Load a command prompt by name.

    Args:
        name: The command name (e.g., 'scope')

    Returns:
        The full content of the command markdown file.

    Raises:
        FileNotFoundError: If the command file doesn't exist.
    """
    ref = resources.files("scope.prompts.commands").joinpath(f"{name}.md")
    return ref.read_text(encoding="utf-8")


def list_skills() -> list[str]:
    """List all available skill names.

    Returns:
        List of skill names (without .md extension).
    """
    skills_dir = resources.files("scope.prompts.skills")
    return [
        f.name.removesuffix(".md")
        for f in skills_dir.iterdir()
        if f.name.endswith(".md")
    ]


def get_all_skills() -> dict[str, str]:
    """Load all skills as a dictionary.

    Returns:
        Dictionary mapping skill names to their content.
    """
    return {name: load_skill(name) for name in list_skills()}
