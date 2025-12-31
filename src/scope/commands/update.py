"""Update command for scope.

Fetches the latest version from PyPI and installs it.
"""

import subprocess
import sys
from typing import Optional

import click


@click.command()
@click.argument("version", required=False)
def update(version: Optional[str] = None) -> None:
    """Update scope to the latest version from PyPI.

    Optionally specify a VERSION to install a specific version.

    Examples:

    \b
        scope update          # Install latest version
        scope update 0.1.3    # Install specific version
    """
    package = "scopeai"

    if version:
        package_spec = f"{package}=={version}"
        click.echo(f"Updating to {package} version {version}...")
    else:
        package_spec = package
        click.echo(f"Updating {package} to latest version...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", package_spec],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            click.echo(result.stdout)
            click.echo("Update complete.")
        else:
            click.echo(result.stderr, err=True)
            raise SystemExit(1)

    except FileNotFoundError:
        click.echo("pip not found. Please ensure pip is installed.", err=True)
        raise SystemExit(1)
