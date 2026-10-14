"""Runs external programs (git, trivy, mvn, agent CLIs) and fails loudly when they do not succeed."""

import subprocess
from pathlib import Path
from typing import IO

DEFAULT_TIMEOUT_SECONDS = 600


class CommandError(RuntimeError):
    pass


def run(args: list[str], cwd: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS,
        stdout_path: Path | None = None) -> str:
    """Runs a command without a shell and returns its stdout. Raises CommandError otherwise.

    With stdout_path, stdout is streamed to that file instead, so it is kept even if
    the command fails or times out, and an empty string is returned.
    """
    if stdout_path is None:
        result = run_unchecked(args, cwd, timeout)
    else:
        with open(stdout_path, "w") as out:
            result = _execute(args, cwd, timeout, stdout=out)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or f"(see {stdout_path})").strip().splitlines()
        raise CommandError(
            f"'{' '.join(args)}' failed with exit code {result.returncode}:\n" + "\n".join(output[-20:]))
    return result.stdout or ""


def run_unchecked(args: list[str], cwd: Path,
                  timeout: int = DEFAULT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Like run, but a non-zero exit code is returned to the caller instead of raised.

    For commands where failing is a normal result, such as mvn test. A missing program
    or a timeout still raises CommandError.
    """
    return _execute(args, cwd, timeout, stdout=subprocess.PIPE)


def _execute(args: list[str], cwd: Path, timeout: int, stdout: int | IO) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=cwd, stdout=stdout, stderr=subprocess.PIPE, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise CommandError(f"{args[0]} not found: is it installed and on PATH?") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError(f"'{' '.join(args)}' timed out after {timeout}s") from error
