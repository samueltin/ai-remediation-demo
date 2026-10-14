"""Runs external programs (git, trivy, mvn) and fails loudly when they do not succeed."""

import subprocess
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 600


class CommandError(RuntimeError):
    pass


def run(args: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Runs a command without a shell and returns its stdout. Raises CommandError otherwise."""
    command = " ".join(args)
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise CommandError(f"{args[0]} not found: is it installed and on PATH?") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError(f"'{command}' timed out after {timeout}s") from error
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip().splitlines()
        raise CommandError(
            f"'{command}' failed with exit code {result.returncode}:\n" + "\n".join(output[-20:]))
    return result.stdout
