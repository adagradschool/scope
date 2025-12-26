"""DAG utilities for dependency management."""

from scope.core.state import get_dependencies


def detect_cycle(new_session_id: str, depends_on: list[str]) -> bool:
    """Detect if adding a dependency would create a cycle.

    Uses DFS to check if any of the dependencies (or their transitive dependencies)
    already depend on the new session.

    Args:
        new_session_id: The ID of the session being created.
        depends_on: List of session IDs the new session will depend on.

    Returns:
        True if adding this dependency would create a cycle, False otherwise.
    """
    if not depends_on:
        return False

    # Check if any dependency (directly or transitively) depends on new_session_id
    visited: set[str] = set()

    def has_path_to(start: str, target: str) -> bool:
        """Check if there's a path from start to target in the dependency graph."""
        if start == target:
            return True
        if start in visited:
            return False

        visited.add(start)
        deps = get_dependencies(start)
        for dep in deps:
            if has_path_to(dep, target):
                return True
        return False

    # For each dependency, check if it has a path back to the new session
    for dep in depends_on:
        visited.clear()
        if has_path_to(dep, new_session_id):
            return True

    return False
