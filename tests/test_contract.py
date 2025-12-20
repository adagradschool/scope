"""Tests for contract generation."""

from scope.core.contract import generate_contract


def test_generate_contract_simple():
    """Test contract generation with a simple prompt."""
    contract = generate_contract(prompt="Write tests for auth module")

    assert "# Task" in contract
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
