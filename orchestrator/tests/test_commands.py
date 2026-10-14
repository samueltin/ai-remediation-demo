import sys

import pytest

from commands import CommandError, run, run_unchecked


def test_output_is_returned(tmp_path):
    assert run([sys.executable, "-c", "print('hello')"], cwd=tmp_path).strip() == "hello"


def test_non_zero_exit_raises_with_stderr(tmp_path):
    script = "import sys; sys.stderr.write('boom'); sys.exit(3)"

    with pytest.raises(CommandError, match="exit code 3(.|\n)*boom"):
        run([sys.executable, "-c", script], cwd=tmp_path)


def test_stdout_is_written_to_file_even_on_failure(tmp_path):
    # Agent transcripts are streamed to disk, so the audit trail survives a failed or crashed agent.
    out = tmp_path / "transcript.jsonl"
    script = "print('step 1'); import sys; sys.exit(4)"

    with pytest.raises(CommandError, match="exit code 4"):
        run([sys.executable, "-c", script], cwd=tmp_path, stdout_path=out)

    assert out.read_text().strip() == "step 1"


def test_unchecked_run_returns_a_failing_result_instead_of_raising(tmp_path):
    result = run_unchecked([sys.executable, "-c", "print('tests failed'); import sys; sys.exit(1)"], cwd=tmp_path)

    assert result.returncode == 1
    assert result.stdout.strip() == "tests failed"


def test_unchecked_run_still_raises_on_timeout(tmp_path):
    with pytest.raises(CommandError, match="timed out"):
        run_unchecked([sys.executable, "-c", "import time; time.sleep(5)"], cwd=tmp_path, timeout=1)


def test_timeout_raises(tmp_path):
    with pytest.raises(CommandError, match="timed out after 1s"):
        run([sys.executable, "-c", "import time; time.sleep(5)"], cwd=tmp_path, timeout=1)


def test_missing_program_raises(tmp_path):
    with pytest.raises(CommandError, match="not found"):
        run(["no-such-program-xyz"], cwd=tmp_path)
