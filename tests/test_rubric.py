"""Tests for rubric parsing, sugar conversion, and composite verification."""

from scope.core.contract import generate_checker_contract
from scope.core.loop import (
    Rubric,
    detect_checker_type,
    iter_session_id,
    load_rubric,
    parse_rubric,
    rubric_hash,
    sugar_to_rubric,
)
from scope.core.state import parent_of
from scope.tui.widgets.session_tree import _session_sort_key


# --- Rubric dataclass tests ---


def test_rubric_defaults():
    """Test Rubric has sensible defaults."""
    r = Rubric()
    assert r.title == ""
    assert r.gates == []
    assert r.criteria == []
    assert r.nice_to_have == []
    assert r.notes == ""
    assert not r.has_gates
    assert not r.has_criteria


def test_rubric_has_gates():
    """Test has_gates property."""
    r = Rubric(gates=["pytest tests/"])
    assert r.has_gates
    assert not r.has_criteria


def test_rubric_has_criteria():
    """Test has_criteria with criteria or nice_to_have."""
    r1 = Rubric(criteria=["Code is correct"])
    assert r1.has_criteria

    r2 = Rubric(nice_to_have=["Good naming"])
    assert r2.has_criteria

    r3 = Rubric()
    assert not r3.has_criteria


# --- parse_rubric tests ---


def test_parse_rubric_full():
    """Test parsing a complete rubric with all sections."""
    text = """# Search Feature

## Gates
- `pytest tests/test_search.py`
- `ruff check src/search/`

## Criteria
- Search results are relevant to query intent
- Empty queries handled gracefully
- Error states show user-friendly messages

## Nice to Have
- Performance: search returns within 200ms
- Code follows existing naming conventions

## Notes
The search uses Elasticsearch. Focus on the API layer.
"""
    rubric = parse_rubric(text)

    assert rubric.title == "Search Feature"
    assert rubric.gates == ["pytest tests/test_search.py", "ruff check src/search/"]
    assert len(rubric.criteria) == 3
    assert "Search results are relevant to query intent" in rubric.criteria[0]
    assert len(rubric.nice_to_have) == 2
    assert "Performance" in rubric.nice_to_have[0]
    assert "Elasticsearch" in rubric.notes


def test_parse_rubric_gates_only():
    """Test parsing a gates-only rubric."""
    text = """## Gates
- `pytest tests/`
- `ruff check`
"""
    rubric = parse_rubric(text)

    assert rubric.gates == ["pytest tests/", "ruff check"]
    assert rubric.criteria == []
    assert rubric.nice_to_have == []
    assert rubric.notes == ""
    assert rubric.has_gates
    assert not rubric.has_criteria


def test_parse_rubric_criteria_only():
    """Test parsing a criteria-only rubric."""
    text = """## Criteria
- Code is correct
- Tests pass
"""
    rubric = parse_rubric(text)

    assert rubric.gates == []
    assert rubric.criteria == ["Code is correct", "Tests pass"]
    assert rubric.has_criteria
    assert not rubric.has_gates


def test_parse_rubric_empty():
    """Test parsing an empty rubric."""
    rubric = parse_rubric("")
    assert rubric.title == ""
    assert rubric.gates == []
    assert rubric.criteria == []


def test_parse_rubric_notes_only():
    """Test parsing a rubric with just notes."""
    text = """## Notes
Some context about the project.
Multiple lines of notes.
"""
    rubric = parse_rubric(text)

    assert "Some context" in rubric.notes
    assert "Multiple lines" in rubric.notes
    assert not rubric.has_gates
    assert not rubric.has_criteria


def test_parse_rubric_no_title():
    """Test parsing a rubric without a title heading."""
    text = """## Gates
- `make test`
"""
    rubric = parse_rubric(text)
    assert rubric.title == ""
    assert rubric.gates == ["make test"]


def test_parse_rubric_gate_without_backticks_ignored():
    """Test that gate items without backticks are ignored."""
    text = """## Gates
- `pytest tests/`
- bare command without backticks
- `ruff check`
"""
    rubric = parse_rubric(text)
    assert rubric.gates == ["pytest tests/", "ruff check"]


# --- detect_checker_type tests ---


def test_detect_file():
    """Test detecting a .md file path."""
    assert detect_checker_type("rubric.md") == "file"
    assert detect_checker_type("path/to/rubric.md") == "file"
    assert detect_checker_type("checks.markdown") == "file"


def test_detect_agent():
    """Test detecting an agent: prefix."""
    assert detect_checker_type("agent: Review for correctness") == "agent"
    assert detect_checker_type("agent:check it") == "agent"


def test_detect_command():
    """Test detecting a shell command."""
    assert detect_checker_type("pytest tests/") == "command"
    assert detect_checker_type("ruff check") == "command"
    assert detect_checker_type("true") == "command"
    assert detect_checker_type("make test && ruff check") == "command"


# --- sugar_to_rubric tests ---


def test_sugar_command_to_rubric():
    """Test converting a shell command to rubric."""
    rubric_md = sugar_to_rubric("pytest tests/")
    assert "## Gates" in rubric_md
    assert "`pytest tests/`" in rubric_md
    assert "## Criteria" not in rubric_md


def test_sugar_agent_to_rubric():
    """Test converting an agent prompt to rubric."""
    rubric_md = sugar_to_rubric("agent: Review for correctness")
    assert "## Criteria" in rubric_md
    assert "Review for correctness" in rubric_md
    assert "## Gates" not in rubric_md


def test_sugar_roundtrip_command():
    """Test that command sugar roundtrips through parse_rubric."""
    rubric_md = sugar_to_rubric("pytest tests/")
    rubric = parse_rubric(rubric_md)
    assert rubric.gates == ["pytest tests/"]
    assert rubric.criteria == []


def test_sugar_roundtrip_agent():
    """Test that agent sugar roundtrips through parse_rubric."""
    rubric_md = sugar_to_rubric("agent: Review for correctness")
    rubric = parse_rubric(rubric_md)
    assert rubric.criteria == ["Review for correctness"]
    assert rubric.gates == []


# --- rubric_hash tests ---


def test_rubric_hash_deterministic():
    """Test hash is deterministic."""
    h1 = rubric_hash("hello")
    h2 = rubric_hash("hello")
    assert h1 == h2


def test_rubric_hash_differs():
    """Test different content produces different hashes."""
    h1 = rubric_hash("hello")
    h2 = rubric_hash("world")
    assert h1 != h2


def test_rubric_hash_short():
    """Test hash is 8 characters."""
    h = rubric_hash("some content")
    assert len(h) == 8


# --- load_rubric tests ---


def test_load_rubric(tmp_path):
    """Test loading a rubric from a file."""
    rubric_file = tmp_path / "rubric.md"
    rubric_file.write_text("## Gates\n- `pytest`\n\n## Criteria\n- Code works\n")

    rubric, content, hash_val = load_rubric(str(rubric_file))
    assert rubric.gates == ["pytest"]
    assert rubric.criteria == ["Code works"]
    assert len(hash_val) == 8
    assert "## Gates" in content


# --- Rubric-aware checker contract tests ---


def test_rubric_checker_contract_with_criteria():
    """Test rubric-aware contract generation with criteria."""
    contract = generate_checker_contract(
        checker_prompt="",
        doer_result="Implemented search feature",
        iteration=0,
        criteria=["Results are relevant", "Edge cases handled"],
        nice_to_have=["Performance is good"],
        notes="Uses Elasticsearch",
    )

    assert "# Role" in contract
    assert "# Must-Have Criteria" in contract
    assert "1. Results are relevant" in contract
    assert "2. Edge cases handled" in contract
    assert "# Nice-to-Have Criteria" in contract
    assert "1. Performance is good" in contract
    assert "# Notes" in contract
    assert "Elasticsearch" in contract
    assert "# Doer Output" in contract
    assert "# Verdict" in contract


def test_rubric_checker_contract_with_gate_results():
    """Test rubric-aware contract includes gate results."""
    contract = generate_checker_contract(
        checker_prompt="",
        doer_result="Output",
        iteration=1,
        gate_results=[
            {"command": "pytest tests/", "verdict": "fail", "output": "2 tests failed"},
            {"command": "ruff check", "verdict": "pass", "output": ""},
        ],
        criteria=["Code is correct"],
    )

    assert "# Gate Results" in contract
    assert "`pytest tests/`" in contract
    assert "FAIL" in contract
    assert "`ruff check`" in contract
    assert "PASS" in contract
    assert "## Gate Output" in contract
    assert "2 tests failed" in contract


def test_rubric_checker_contract_no_gate_results():
    """Test rubric contract without gates omits gate section."""
    contract = generate_checker_contract(
        checker_prompt="",
        doer_result="Output",
        iteration=0,
        criteria=["Code works"],
    )

    assert "# Gate Results" not in contract
    assert "# Must-Have Criteria" in contract


def test_rubric_checker_contract_criteria_only():
    """Test rubric contract with only criteria (no nice-to-have)."""
    contract = generate_checker_contract(
        checker_prompt="",
        doer_result="Output",
        iteration=0,
        criteria=["Criterion 1"],
    )

    assert "# Must-Have Criteria" in contract
    assert "# Nice-to-Have" not in contract


def test_rubric_checker_contract_nice_only():
    """Test rubric contract with only nice-to-have."""
    contract = generate_checker_contract(
        checker_prompt="",
        doer_result="Output",
        iteration=0,
        nice_to_have=["Good style"],
    )

    assert "# Nice-to-Have Criteria" in contract
    assert "# Must-Have" not in contract


def test_legacy_checker_contract_unchanged():
    """Test legacy (non-rubric) checker contract still works."""
    contract = generate_checker_contract(
        checker_prompt="Verify the code is correct",
        doer_result="I wrote a hello world function.",
        iteration=0,
    )

    assert "# Role" in contract
    assert "# Checker Criteria" in contract
    assert "Verify the code is correct" in contract
    assert "# Doer Output" in contract
    # Should NOT have rubric-specific sections
    assert "# Must-Have Criteria" not in contract
    assert "# Verdict" not in contract


def test_rubric_checker_contract_with_history():
    """Test rubric contract includes history."""
    contract = generate_checker_contract(
        checker_prompt="",
        doer_result="Output",
        iteration=1,
        history=[{"iteration": 0, "verdict": "retry", "feedback": "Failed tests"}],
        criteria=["Tests pass"],
    )

    assert "# Prior Iterations" in contract
    assert "Iteration 0" in contract
    assert "RETRY" in contract


def test_rubric_checker_contract_section_ordering():
    """Test rubric contract sections are in correct order."""
    contract = generate_checker_contract(
        checker_prompt="",
        doer_result="Output",
        iteration=1,
        history=[{"iteration": 0, "verdict": "retry", "feedback": "Fix it"}],
        gate_results=[{"command": "pytest", "verdict": "pass", "output": "ok"}],
        criteria=["Code works"],
        nice_to_have=["Good style"],
        notes="Context here",
    )

    role_idx = contract.index("# Role")
    gates_idx = contract.index("# Gate Results")
    must_idx = contract.index("# Must-Have Criteria")
    nice_idx = contract.index("# Nice-to-Have Criteria")
    notes_idx = contract.index("# Notes")
    doer_idx = contract.index("# Doer Output")
    iter_idx = contract.index("# Iteration")
    history_idx = contract.index("# Prior Iterations")
    verdict_idx = contract.index("# Verdict")

    assert role_idx < gates_idx < must_idx < nice_idx < notes_idx < doer_idx < iter_idx < history_idx < verdict_idx


# --- iter_session_id tests ---


def test_iter_session_id_check():
    """Test iter_session_id for checker role."""
    assert iter_session_id("2.1", 0, "check") == "2.1-0-check"


def test_iter_session_id_do():
    """Test iter_session_id for doer role."""
    assert iter_session_id("2.1", 1, "do") == "2.1-1-do"


def test_iter_session_id_root():
    """Test iter_session_id with root loop session."""
    assert iter_session_id("0", 2, "check") == "0-2-check"


# --- parent_of tests ---


def test_parent_of_dash_child():
    """Test parent_of with iteration-indexed dash child."""
    assert parent_of("2.1-0-check") == "2.1"


def test_parent_of_dash_do():
    """Test parent_of with iteration-indexed dash doer."""
    assert parent_of("2.1-1-do") == "2.1"


def test_parent_of_dot_child():
    """Test parent_of with dot child."""
    assert parent_of("2.1") == "2"


def test_parent_of_root():
    """Test parent_of with root session."""
    assert parent_of("0") == ""


def test_parent_of_root_dash():
    """Test parent_of with root session dash child."""
    assert parent_of("0-0-check") == "0"


# --- _session_sort_key tests ---


def test_sort_key_ordering():
    """Test that _session_sort_key produces correct ordering."""
    ids = ["2.1-1-check", "2.1-0-check", "2.1", "2.1-1-do"]
    sorted_ids = sorted(ids, key=_session_sort_key)
    assert sorted_ids == ["2.1", "2.1-0-check", "2.1-1-check", "2.1-1-do"]


def test_sort_key_check_before_do_same_iter():
    """Test that within the same iteration, check < do alphabetically."""
    # "check" < "do" alphabetically
    assert _session_sort_key("2.1-0-check") < _session_sort_key("2.1-0-do")


def test_sort_key_plain_before_dash():
    """Test that plain ID sorts before dash children."""
    assert _session_sort_key("2.1") < _session_sort_key("2.1-0-check")
