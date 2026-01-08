"""Update command for scope.

Fetches the latest version from PyPI and installs it.
"""

import shutil
import subprocess
import sys
from typing import Optional

import click


def _find_pip() -> list[str]:
    """Find pip executable, falling back to pip3 if pip is not available."""
    # First try using the current Python's pip module
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
    )
    if result.returncode == 0:
        return [sys.executable, "-m", "pip"]

    # Fall back to pip3 command
    pip3_path = shutil.which("pip3")
    if pip3_path:
        return [pip3_path]

    # Fall back to pip command
    pip_path = shutil.which("pip")
    if pip_path:
        return [pip_path]

    return []


@click.command()
@click.argument("version", required=False)
def update(version: Optional[str] = None) -> None:
    """Update scope to the latest version from PyPI.

    Optionally specify a VERSION to install a specific version.
    Hooks and skills are automatically updated on next scope invocation.

    Examples:

    \b
        scope update          # Install latest version
        scope update 0.1.3    # Install specific version
    """
    package = "scopeai"

    pip_cmd = _find_pip()
    if not pip_cmd:
        click.echo("pip not found. Please ensure pip or pip3 is installed.", err=True)
        raise SystemExit(1)

    if version:
        package_spec = f"{package}=={version}"
        click.echo(f"Updating to {package} version {version}...")
    else:
        package_spec = package
        click.echo(f"Updating {package} to latest version...")

    result = subprocess.run(
        [*pip_cmd, "install", "--upgrade", package_spec],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        click.echo(result.stdout)
        click.echo("Update complete.")
    else:
        click.echo(result.stderr, err=True)
        raise SystemExit(1)
