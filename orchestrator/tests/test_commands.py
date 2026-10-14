import sys

import pytest

from commands import CommandError, run


def test_output_is_returned(tmp_path):
    assert run([sys.executable, "-c", "print('hello')"], cwd=tmp_path).strip() == "hello"


def test_non_zero_exit_raises_with_stderr(tmp_path):
    script = "import sys; sys.stderr.write('boom'); sys.exit(3)"

    with pytest.raises(CommandError, match="exit code 3(.|\n)*boom"):
        run([sys.executable, "-c", script], cwd=tmp_path)


def test_timeout_raises(tmp_path):
    with pytest.raises(CommandError, match="timed out after 1s"):
        run([sys.executable, "-c", "import time; time.sleep(5)"], cwd=tmp_path, timeout=1)


def test_missing_program_raises(tmp_path):
    with pytest.raises(CommandError, match="not found"):
        run(["no-such-program-xyz"], cwd=tmp_path)
