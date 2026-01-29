"""Session dataclass for scope."""

from dataclasses import dataclass, field
from datetime import datetime

VALID_STATES = {"pending", "running", "done", "aborted", "failed", "exited", "evicted"}


@dataclass
class Session:
    """Represents a scope session.

    Attributes:
        id: Flat dotted notation (e.g., "0", "0.1", "0.1.2")
        task: One-line description of the task
        parent: Parent session ID (empty string for root sessions)
        state: Session state - one of "pending", "running", "done", "aborted", "failed", "exited", "evicted"
        tmux_session: tmux session name (format: "scope-{id}")
        created_at: Timestamp when session was created
        alias: Human-readable alias for the session (optional)
        depends_on: List of session IDs this session depends on (optional)
    """

    id: str
    task: str
    parent: str
    state: str
    tmux_session: str
    created_at: datetime
    alias: str = ""
    depends_on: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate session state."""
        if self.state not in VALID_STATES:
            raise ValueError(
                f"Invalid state: {self.state}. Must be one of {VALID_STATES}"
            )
