"""Session list widget for scope TUI."""

from collections import defaultdict
from dataclasses import dataclass

from textual.widgets import DataTable

from scope.core.session import Session
from scope.core.state import load_loop_state


@dataclass
class TreeNode:
    """A node in the session display tree.

    Attributes:
        session: The underlying Session object.
        depth: Indentation level in the tree.
        has_children: Whether this node has visible children.
        node_type: "session" (normal), "loop" (loop header), or "iteration" (loop child).
        iteration_label: Display label like "Iter 0", "Iter 1", etc.
        loop_info: Summary like "iter 2/3" for loop headers.
        mode: "do", "check", or "" for the Mode column.
    """

    session: Session
    depth: int
    has_children: bool
    node_type: str = "session"  # "session" | "loop" | "iteration"
    iteration_label: str = ""
    loop_info: str = ""
    mode: str = ""


def _build_tree(
    sessions: list[Session],
    collapsed: set[str],
    hide_done: bool = False,
) -> list[TreeNode]:
    """Build tree structure from flat session list.

    Args:
        sessions: Flat list of sessions.
        collapsed: Set of session IDs that are collapsed.
        hide_done: Whether to hide done/aborted sessions.

    Returns:
        List of TreeNode objects in display order (DFS).
    """
    # Filter out done/aborted if requested
    if hide_done:
        hidden_ids: set[str] = set()
        for s in sessions:
            if s.state in {"done", "aborted", "exited"}:
                hidden_ids.add(s.id)
        changed = True
        while changed:
            changed = False
            for s in sessions:
                if s.parent in hidden_ids and s.id not in hidden_ids:
                    hidden_ids.add(s.id)
                    changed = True
        sessions = [s for s in sessions if s.id not in hidden_ids]

    # Group sessions by parent
    children: dict[str, list[Session]] = defaultdict(list)
    for session in sessions:
        children[session.parent].append(session)

    # Sort children by ID within each parent group (numeric segment ordering)
    for parent_id in children:
        children[parent_id].sort(key=lambda s: [int(x) for x in s.id.split(".")])

    # Build lookup by id
    session_by_id: dict[str, Session] = {s.id: s for s in sessions}

    result: list[TreeNode] = []

    def traverse(parent: str, depth: int) -> None:
        for session in children.get(parent, []):
            loop_state = load_loop_state(session.id)

            if loop_state is None:
                # Normal session — same as before
                has_children = bool(children.get(session.id))
                result.append(
                    TreeNode(
                        session=session,
                        depth=depth,
                        has_children=has_children,
                        node_type="session",
                    )
                )
                if session.id not in collapsed:
                    traverse(session.id, depth + 1)
            else:
                # Loop session — emit header + iteration children
                history = loop_state.get("history", [])
                max_iter = loop_state.get("max_iterations", 0)
                current_iter = loop_state.get("current_iteration", 0)

                # Collect doer session IDs from history
                doer_ids: set[str] = set()
                for entry in history:
                    ds = entry.get("doer_session")
                    if ds:
                        doer_ids.add(str(ds))

                # All child sessions of this loop
                child_sessions = children.get(session.id, [])

                # The loop header always "has children" (the iterations)
                has_iter_children = True

                # Build loop_info string
                if session.state == "running":
                    loop_info = f"iter {current_iter + 1}/{max_iter}"
                elif history:
                    last = history[-1]
                    verdict = last.get("verdict", "")
                    loop_info = verdict if verdict else "done"
                else:
                    loop_info = ""

                # Use "loop:" prefix key for the header
                result.append(
                    TreeNode(
                        session=session,
                        depth=depth,
                        has_children=has_iter_children,
                        node_type="loop",
                        loop_info=loop_info,
                        mode="loop",
                    )
                )

                if session.id not in collapsed:
                    # Sort history by iteration number
                    sorted_history = sorted(
                        history, key=lambda h: h.get("iteration", 0)
                    )

                    # Build checker ID lookup from history
                    checker_by_iter: dict[int, str] = {}
                    for entry in sorted_history:
                        cs = entry.get("checker_session")
                        if cs:
                            checker_by_iter[entry.get("iteration", 0)] = str(cs)

                    # Iteration 0: the loop session itself is the first doer
                    result.append(
                        TreeNode(
                            session=session,
                            depth=depth + 1,
                            has_children=False,
                            node_type="iteration",
                            iteration_label="Iter 0",
                            mode="do",
                        )
                    )

                    # Iteration 0 checker (if recorded in history)
                    iter0_checker_id = checker_by_iter.get(0)
                    iter0_checker = (
                        session_by_id.get(iter0_checker_id)
                        if iter0_checker_id
                        else None
                    )
                    if iter0_checker:
                        result.append(
                            TreeNode(
                                session=iter0_checker,
                                depth=depth + 1,
                                has_children=False,
                                node_type="iteration",
                                iteration_label="check",
                                mode="check",
                            )
                        )

                    # Remaining iterations — emit do + check pairs
                    for entry in sorted_history:
                        ds_id = str(entry.get("doer_session", ""))
                        iteration_num = entry.get("iteration", 0)
                        if iteration_num == 0:
                            continue
                        child_session = session_by_id.get(ds_id)
                        if child_session:
                            result.append(
                                TreeNode(
                                    session=child_session,
                                    depth=depth + 1,
                                    has_children=False,
                                    node_type="iteration",
                                    iteration_label=f"Iter {iteration_num}",
                                    mode="do",
                                )
                            )
                        # Checker for this iteration
                        cs_id = checker_by_iter.get(iteration_num)
                        checker_session = session_by_id.get(cs_id) if cs_id else None
                        if checker_session:
                            result.append(
                                TreeNode(
                                    session=checker_session,
                                    depth=depth + 1,
                                    has_children=False,
                                    node_type="iteration",
                                    iteration_label="check",
                                    mode="check",
                                )
                            )

                    # Fallback: any child not accounted for as doer or checker
                    all_known_ids = doer_ids | set(checker_by_iter.values())
                    for child in child_sessions:
                        if child.id not in all_known_ids:
                            result.append(
                                TreeNode(
                                    session=child,
                                    depth=depth + 1,
                                    has_children=False,
                                    node_type="iteration",
                                    iteration_label="check",
                                    mode="check",
                                )
                            )

                # Don't traverse children normally — they're already placed above
                # But we do need to traverse grandchildren of child sessions
                # that aren't part of the loop iteration display
                # (not needed for now — loop children are leaf doer/checker sessions)

    traverse("", 0)
    return result


class SessionTable(DataTable):
    """DataTable widget displaying scope sessions.

    Columns: ID, Task, Status, Mode, Activity
    Sessions are displayed in tree hierarchy with indentation.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._collapsed: set[str] = set()
        self._sessions: list[Session] = []
        self._hide_done: bool = False
        self._selected_session_id: str | None = None

    def on_mount(self) -> None:
        """Set up the table columns on mount."""
        self.add_columns("ID", "Task", "Status", "Mode", "Activity")
        self.cursor_type = "row"

    def watch_cursor_row(self, old_row: int | None, new_row: int | None) -> None:
        """Track cursor changes to preserve selection across refreshes."""
        if new_row is not None and self.row_count > 0:
            try:
                row = self.get_row_at(new_row)
                if row is not None:
                    display_id = row[0]
                    session_id = display_id.lstrip("▶▼ ").strip()
                    if session_id:
                        self._selected_session_id = session_id
            except Exception:
                pass

    def toggle_collapse(self) -> None:
        """Toggle collapse state on currently selected session."""
        if self.cursor_row is None:
            return

        row_key = self.get_row_at(self.cursor_row)
        if not row_key:
            return

        # Extract session ID from first column (may have indicator prefix)
        display_id = row_key[0]
        session_id = display_id.lstrip("▶▼ ").strip()

        if session_id in self._collapsed:
            self._collapsed.remove(session_id)
        else:
            self._collapsed.add(session_id)

        # Re-render with updated collapse state
        self._render_sessions()

    def update_sessions(self, sessions: list[Session], hide_done: bool = False) -> None:
        """Update the table with the given sessions.

        Args:
            sessions: List of sessions to display.
            hide_done: Whether to hide done/aborted sessions.
        """
        self._sessions = sessions
        self._hide_done = hide_done
        self._render_sessions()

    def set_selected_session(self, session_id: str | None) -> None:
        """Set the selected session ID for the next render."""
        self._selected_session_id = session_id

    def _render_sessions(self) -> None:
        """Render sessions to the table."""
        # Preserve current cursor selection before clearing rows.
        if (
            self._selected_session_id is None
            and self.cursor_row is not None
            and self.row_count > 0
        ):
            try:
                row = self.get_row_at(self.cursor_row)
                if row is not None:
                    display_id = row[0]
                    session_id = display_id.lstrip("▶▼ ").strip()
                    if session_id:
                        self._selected_session_id = session_id
            except Exception:
                pass

        selected_session_id = self._selected_session_id

        self.clear()

        # Build tree and iterate in display order
        tree = _build_tree(self._sessions, self._collapsed, self._hide_done)

        for node in tree:
            session = node.session

            if node.node_type == "loop":
                # Loop header row
                task = session.task if session.task else "(pending...)"
                if len(task) > 40:
                    task = task[:37] + "..."
                activity = node.loop_info
                indent = "  " * node.depth
                indicator = "▶ " if session.id in self._collapsed else "▼ "
                display_id = f"{indent}{indicator}{session.id}"
                row_key = f"loop:{session.id}"
            elif node.node_type == "iteration":
                # Iteration child row
                task = node.iteration_label
                if len(task) > 40:
                    task = task[:37] + "..."
                activity = self._get_activity(session.id, session.state)
                indent = "  " * node.depth
                display_id = f"{indent}  {session.id}"
                row_key = session.id
            else:
                # Normal session row
                task = session.task if session.task else "(pending...)"
                if len(task) > 40:
                    task = task[:37] + "..."
                activity = self._get_activity(session.id, session.state)
                indent = "  " * node.depth
                if node.has_children:
                    indicator = "▶ " if session.id in self._collapsed else "▼ "
                else:
                    indicator = "  "
                display_id = f"{indent}{indicator}{session.id}"
                row_key = session.id

            self.add_row(
                display_id,
                task,
                session.state,
                node.mode,
                activity,
                key=row_key,
            )

        # Restore selection if the session still exists
        if selected_session_id is not None:
            session_id = selected_session_id
            while session_id:
                # Try both raw ID and loop: prefixed
                for key_candidate in [session_id, f"loop:{session_id}"]:
                    try:
                        row_index = self.get_row_index(key_candidate)
                        self.move_cursor(row=row_index)
                        self._selected_session_id = session_id
                        return
                    except Exception:
                        pass
                # Walk up to parent
                if "." in session_id:
                    session_id = session_id.rsplit(".", 1)[0]
                else:
                    self._selected_session_id = None
                    break

    def _get_activity(self, session_id: str, session_state: str) -> str:
        """Get the current activity for a session.

        Args:
            session_id: The session ID.
            session_state: The session state.

        Returns:
            Activity string or "-" if none.
        """
        from scope.core.state import ensure_scope_dir

        scope_dir = ensure_scope_dir()
        activity_file = scope_dir / "sessions" / session_id / "activity"
        if activity_file.exists():
            activity = ""
            for line in activity_file.read_text().splitlines():
                if line.strip():
                    activity = line.strip()
            if activity:
                if session_state in {"done", "aborted", "exited"}:
                    activity = _past_tense_activity(activity)
                # Truncate long activity
                if len(activity) > 30:
                    return activity[:27] + "..."
                return activity
        return "-"


def _past_tense_activity(activity: str) -> str:
    """Convert present-tense activity to past tense for done sessions."""
    conversions = {
        "reading ": "read ",
        "editing ": "edited ",
        "running: ": "ran: ",
        "searching: ": "searched: ",
        "spawning subtask": "spawned subtask",
        "finding: ": "found: ",
        "reading file": "read file",
        "editing file": "edited file",
        "running command": "ran command",
        "searching": "searched",
        "finding files": "found files",
    }
    for prefix, replacement in conversions.items():
        if activity.startswith(prefix):
            return replacement + activity[len(prefix) :]
    return activity
