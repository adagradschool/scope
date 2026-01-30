"""Tests for contract generation."""

from scope.core.contract import generate_checker_contract, generate_contract


def test_generate_contract_simple():
    """Test contract generation with a simple prompt."""
    contract = generate_contract(prompt="Write tests for auth module")

    assert contract.startswith("# Task")
    assert "Write tests for auth module" in contract


def test_generate_contract_multiline():
    """Test contract with multiline prompt."""
    prompt = """Fix the authentication bug.

The issue is in src/auth.py where tokens expire too quickly.
See error logs for details."""

    contract = generate_contract(prompt=prompt)

    assert "# Task" in contract
    assert "Fix the authentication bug" in contract
    assert "src/auth.py" in contract


def test_generate_contract_with_dependencies():
    """Test contract includes wait instruction when depends_on provided."""
    contract = generate_contract(
        prompt="Implement feature based on research",
        depends_on=["0.0", "0.1"],
    )

    # Dependencies should come first, then Task
    assert contract.startswith("# Dependencies")
    assert "# Task" in contract
    assert contract.index("# Dependencies") < contract.index("# Task")

    # Should include wait command with all dependencies
    assert "scope wait 0.0 0.1" in contract
    assert "Before starting, wait for your dependencies to complete" in contract
    assert "Use the results from these sessions to inform your work" in contract

    # Task content should still be present
    assert "Implement feature based on research" in contract


def test_generate_contract_with_single_dependency():
    """Test contract with a single dependency."""
    contract = generate_contract(
        prompt="Build on previous work",
        depends_on=["research"],
    )

    assert "# Dependencies" in contract
    assert "scope wait research" in contract
    assert "Build on previous work" in contract


def test_generate_contract_no_dependencies_when_empty_list():
    """Test contract has no dependencies section when depends_on is empty."""
    contract = generate_contract(prompt="Simple task", depends_on=[])

    assert "# Dependencies" not in contract
    assert "scope wait" not in contract
    assert "# Task" in contract
    assert "Simple task" in contract


def test_generate_contract_no_dependencies_when_none():
    """Test contract has no dependencies section when depends_on is None."""
    contract = generate_contract(prompt="Simple task", depends_on=None)

    assert "# Dependencies" not in contract
    assert "scope wait" not in contract
    assert "# Task" in contract
    assert "Simple task" in contract


# --- Phase metadata tests ---


def test_generate_contract_with_phase():
    """Test contract includes phase metadata."""
    contract = generate_contract(prompt="Write failing test", phase="RED")

    assert "# Phase" in contract
    assert "**RED**" in contract
    assert "# Task" in contract
    assert contract.index("# Phase") < contract.index("# Task")


def test_generate_contract_phase_none():
    """Test no phase section when phase is None."""
    contract = generate_contract(prompt="Do work", phase=None)

    assert "# Phase" not in contract


# --- Parent intent tests ---


def test_generate_contract_with_parent_intent():
    """Test contract includes parent intent."""
    contract = generate_contract(
        prompt="Implement auth endpoint",
        parent_intent="The orchestrator goal is to add user authentication. Your sub-goal is to implement the /login endpoint.",
    )

    assert "# Parent Intent" in contract
    assert "orchestrator goal" in contract
    assert "# Task" in contract
    assert contract.index("# Parent Intent") < contract.index("# Task")


def test_generate_contract_parent_intent_none():
    """Test no parent intent section when None."""
    contract = generate_contract(prompt="Do work", parent_intent=None)

    assert "# Parent Intent" not in contract


# --- Prior results tests ---


def test_generate_contract_with_prior_results():
    """Test contract includes prior results."""
    contract = generate_contract(
        prompt="Continue the work",
        prior_results=[
            "Research found 3 auth libraries: jwt, oauth2, sessions.",
            "Benchmark shows jwt is 2x faster.",
        ],
    )

    assert "# Prior Results" in contract
    assert "3 auth libraries" in contract
    assert "jwt is 2x faster" in contract
    assert "# Task" in contract
    assert contract.index("# Prior Results") < contract.index("# Task")


def test_generate_contract_with_single_prior_result():
    """Test contract with a single prior result."""
    contract = generate_contract(
        prompt="Use these findings",
        prior_results=["The API uses REST with JSON responses."],
    )

    assert "# Prior Results" in contract
    assert "REST with JSON" in contract


def test_generate_contract_prior_results_none():
    """Test no prior results section when None."""
    contract = generate_contract(prompt="Do work", prior_results=None)

    assert "# Prior Results" not in contract


def test_generate_contract_prior_results_empty():
    """Test no prior results section when empty list."""
    contract = generate_contract(prompt="Do work", prior_results=[])

    assert "# Prior Results" not in contract


# --- File scope tests ---


def test_generate_contract_with_file_scope():
    """Test contract includes file scope constraints."""
    contract = generate_contract(
        prompt="Refactor auth module",
        file_scope=["src/auth/", "tests/test_auth.py"],
    )

    assert "# File Scope" in contract
    assert "Only modify files within" in contract
    assert "`src/auth/`" in contract
    assert "`tests/test_auth.py`" in contract
    assert "# Task" in contract
    # File scope comes AFTER task
    assert contract.index("# Task") < contract.index("# File Scope")


def test_generate_contract_with_single_file_scope():
    """Test contract with a single file scope."""
    contract = generate_contract(
        prompt="Fix bug",
        file_scope=["src/auth/"],
    )

    assert "# File Scope" in contract
    assert "`src/auth/`" in contract


def test_generate_contract_file_scope_none():
    """Test no file scope section when None."""
    contract = generate_contract(prompt="Do work", file_scope=None)

    assert "# File Scope" not in contract


def test_generate_contract_file_scope_empty():
    """Test no file scope section when empty list."""
    contract = generate_contract(prompt="Do work", file_scope=[])

    assert "# File Scope" not in contract


# --- Section ordering tests ---


def test_generate_contract_full_section_ordering():
    """Test that all sections appear in correct order."""
    contract = generate_contract(
        prompt="Implement feature",
        depends_on=["0.0"],
        phase="GREEN",
        parent_intent="Build the auth system",
        prior_results=["Previous research completed."],
        file_scope=["src/auth/"],
    )

    deps_idx = contract.index("# Dependencies")
    phase_idx = contract.index("# Phase")
    intent_idx = contract.index("# Parent Intent")
    results_idx = contract.index("# Prior Results")
    task_idx = contract.index("# Task")
    scope_idx = contract.index("# File Scope")

    assert deps_idx < phase_idx < intent_idx < results_idx < task_idx < scope_idx


def test_generate_contract_partial_sections_ordering():
    """Test ordering with only some optional sections."""
    contract = generate_contract(
        prompt="Do work",
        phase="REFACTOR",
        file_scope=["src/"],
    )

    phase_idx = contract.index("# Phase")
    task_idx = contract.index("# Task")
    scope_idx = contract.index("# File Scope")

    assert phase_idx < task_idx < scope_idx
    assert "# Dependencies" not in contract
    assert "# Parent Intent" not in contract
    assert "# Prior Results" not in contract


# --- Backward compatibility tests ---


def test_generate_contract_backward_compatible_positional():
    """Test that existing callers with positional args still work."""
    contract = generate_contract("Simple prompt")
    assert "# Task" in contract
    assert "Simple prompt" in contract


def test_generate_contract_backward_compatible_kwargs():
    """Test that existing callers with keyword args still work."""
    contract = generate_contract(prompt="Task prompt", depends_on=["a"])
    assert "# Dependencies" in contract
    assert "# Task" in contract


# --- Combination tests ---


def test_generate_contract_phase_and_dependencies():
    """Test phase with dependencies."""
    contract = generate_contract(
        prompt="Write failing test",
        depends_on=["setup"],
        phase="RED",
    )

    assert "# Dependencies" in contract
    assert "# Phase" in contract
    assert "# Task" in contract
    assert contract.index("# Dependencies") < contract.index("# Phase") < contract.index("# Task")


def test_generate_contract_parent_intent_and_prior_results():
    """Test parent intent with prior results."""
    contract = generate_contract(
        prompt="Continue work",
        parent_intent="Build auth system",
        prior_results=["Found 3 options"],
    )

    assert "# Parent Intent" in contract
    assert "# Prior Results" in contract
    assert "# Task" in contract
    assert contract.index("# Parent Intent") < contract.index("# Prior Results") < contract.index("# Task")


# --- Verification tests ---


def test_generate_contract_with_verify():
    """Test contract includes verification criteria."""
    contract = generate_contract(
        prompt="Implement feature",
        verify=["pytest tests/", "ruff check", "all types pass"],
    )

    assert "# Verification" in contract
    assert "verified against these criteria" in contract
    assert "- pytest tests/" in contract
    assert "- ruff check" in contract
    assert "- all types pass" in contract


def test_generate_contract_verify_after_file_scope():
    """Test verification section comes after file scope."""
    contract = generate_contract(
        prompt="Do work",
        file_scope=["src/"],
        verify=["pytest"],
    )

    assert "# File Scope" in contract
    assert "# Verification" in contract
    assert contract.index("# File Scope") < contract.index("# Verification")


def test_generate_contract_verify_none():
    """Test no verification section when None."""
    contract = generate_contract(prompt="Do work", verify=None)

    assert "# Verification" not in contract


def test_generate_contract_verify_empty():
    """Test no verification section when empty list."""
    contract = generate_contract(prompt="Do work", verify=[])

    assert "# Verification" not in contract


def test_generate_contract_full_with_verify():
    """Test all sections including verify appear in correct order."""
    contract = generate_contract(
        prompt="Implement feature",
        depends_on=["0.0"],
        phase="GREEN",
        parent_intent="Build the auth system",
        prior_results=["Previous research completed."],
        file_scope=["src/auth/"],
        verify=["pytest"],
    )

    deps_idx = contract.index("# Dependencies")
    phase_idx = contract.index("# Phase")
    intent_idx = contract.index("# Parent Intent")
    results_idx = contract.index("# Prior Results")
    task_idx = contract.index("# Task")
    scope_idx = contract.index("# File Scope")
    verify_idx = contract.index("# Verification")

    assert deps_idx < phase_idx < intent_idx < results_idx < task_idx < scope_idx < verify_idx


# --- Checker contract tests ---


def test_generate_checker_contract_basic():
    """Test basic checker contract generation."""
    contract = generate_checker_contract(
        checker_prompt="Verify the code is correct",
        doer_result="I wrote a hello world function.",
        iteration=0,
    )

    assert "# Role" in contract
    assert "checker" in contract.lower()
    assert "ACCEPT" in contract
    assert "RETRY" in contract
    assert "TERMINATE" in contract
    assert "# Checker Criteria" in contract
    assert "Verify the code is correct" in contract
    assert "# Doer Output" in contract
    assert "hello world function" in contract
    assert "# Iteration" in contract
    assert "iteration 0" in contract


def test_generate_checker_contract_with_history():
    """Test checker contract includes iteration history."""
    history = [
        {"iteration": 0, "verdict": "retry", "feedback": "Missing error handling"},
        {"iteration": 1, "verdict": "retry", "feedback": "Still missing edge cases"},
    ]

    contract = generate_checker_contract(
        checker_prompt="Check completeness",
        doer_result="Updated implementation.",
        iteration=2,
        history=history,
    )

    assert "# Prior Iterations" in contract
    assert "Iteration 0" in contract
    assert "RETRY" in contract
    assert "Missing error handling" in contract
    assert "Iteration 1" in contract
    assert "Still missing edge cases" in contract
    assert "iteration 2" in contract


def test_generate_checker_contract_no_history():
    """Test checker contract without history omits that section."""
    contract = generate_checker_contract(
        checker_prompt="Check it",
        doer_result="Output",
        iteration=0,
        history=None,
    )

    assert "# Prior Iterations" not in contract


def test_generate_checker_contract_empty_history():
    """Test checker contract with empty history omits that section."""
    contract = generate_checker_contract(
        checker_prompt="Check it",
        doer_result="Output",
        iteration=0,
        history=[],
    )

    assert "# Prior Iterations" not in contract


def test_generate_checker_contract_section_ordering():
    """Test checker contract sections are in correct order."""
    contract = generate_checker_contract(
        checker_prompt="Review code",
        doer_result="Code output",
        iteration=1,
        history=[{"iteration": 0, "verdict": "retry", "feedback": "Needs work"}],
    )

    role_idx = contract.index("# Role")
    criteria_idx = contract.index("# Checker Criteria")
    output_idx = contract.index("# Doer Output")
    iter_idx = contract.index("# Iteration")
    history_idx = contract.index("# Prior Iterations")

    assert role_idx < criteria_idx < output_idx < iter_idx < history_idx
