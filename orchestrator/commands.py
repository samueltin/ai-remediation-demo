"""Runs external programs (git, trivy, mvn, agent CLIs) and fails loudly when they do not succeed."""

import subprocess
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 600


class CommandError(RuntimeError):
    pass


def run(args: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS,
        stdout_path: Path | None = None) -> str:
    """Runs a command without a shell and returns its stdout. Raises CommandError otherwise.

    With stdout_path, stdout is streamed to that file instead, so it is kept even if
    the command fails or times out, and an empty string is returned.
    """
    command = " ".join(args)
    try:
        if stdout_path is None:
            result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        else:
            with open(stdout_path, "w") as out:
                result = subprocess.run(args, cwd=cwd, stdout=out, stderr=subprocess.PIPE,
                                        text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise CommandError(f"{args[0]} not found: is it installed and on PATH?") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError(f"'{command}' timed out after {timeout}s") from error
    if result.returncode != 0:
        output = (result.stderr or result.stdout or f"(see {stdout_path})").strip().splitlines()
        raise CommandError(
            f"'{command}' failed with exit code {result.returncode}:\n" + "\n".join(output[-20:]))
    return result.stdout or ""
