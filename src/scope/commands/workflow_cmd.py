"""Workflow CLI command for scope.

Runs a Python workflow file that uses the Workflow builder API.

Usage:
    scope workflow workflows/tdd.py
"""

import importlib.util
import sys
from pathlib import Path

import click


@click.command("workflow")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
def workflow_cmd(file: str) -> None:
    """Run a Python workflow file.

    FILE is the path to a Python file that uses the scope Workflow builder.
    The file is loaded and executed — it is responsible for calling wf.run().

    Example:

        scope workflow workflows/tdd.py
    """
    file_path = Path(file).resolve()

    # Load and execute the workflow file
    spec = importlib.util.spec_from_file_location("__workflow__", file_path)
    if spec is None or spec.loader is None:
        click.echo(f"Error: could not load {file_path}", err=True)
        raise SystemExit(1)

    module = importlib.util.module_from_spec(spec)
    # Make the workflow directory available for relative imports
    sys.path.insert(0, str(file_path.parent))
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error running workflow: {e}", err=True)
        raise SystemExit(1)
    finally:
        sys.path.pop(0)
