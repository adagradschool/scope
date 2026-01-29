"""Tests for contract generation."""

from scope.core.contract import generate_contract


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
