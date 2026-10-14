import json
from pathlib import Path

import pytest

from agents import AgentError, build_prompt, claude_command, claude_result, copilot_command, copilot_result
from ticket import load_ticket

SEC_101 = Path(__file__).resolve().parents[2] / "tickets" / "SEC-101.json"


def write_jsonl(tmp_path, events):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return path


def option_values(command, option):
    return [command[i + 1] for i, arg in enumerate(command) if arg == option]


def test_prompt_contains_ticket_details_and_rules():
    prompt = build_prompt(load_ticket(SEC_101))

    assert "SEC-101" in prompt
    assert "org.apache.commons:commons-text from 1.9 to 1.10.0" in prompt
    assert "- mvn test passes" in prompt
    assert "src/test" in prompt
    assert "$" not in prompt


# These two tests lock the permission boundary: loosening it must be a deliberate, reviewed change.

def test_claude_may_only_edit_files_and_run_mvn():
    command = claude_command("fix it")

    assert "--restricted" in command
    assert option_values(command, "--permission-mode") == ["dontAsk"]
    assert option_values(command, "--allowedTools") == ["Read Edit Write Glob Grep Bash(mvn *)"]
    assert "--strict-mcp-config" in command
    assert "--dangerously-skip-permissions" not in command


def test_copilot_may_only_edit_files_and_run_mvn(tmp_path):
    command = copilot_command("fix it", tmp_path / "session.md")

    assert option_values(command, "--allow-tool") == ["write", "shell(mvn:*)"]
    assert "--no-custom-instructions" in command
    assert "--disable-builtin-mcps" in command
    for too_wide in ("--allow-all-tools", "--allow-all-paths", "--allow-all-urls", "--allow-all", "--yolo"):
        assert too_wide not in command


def test_claude_result_reads_final_message_and_model(tmp_path):
    transcript = write_jsonl(tmp_path, [
        {"type": "system", "subtype": "init", "model": "claude-test"},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Upgraded and tests pass."},
    ])

    result = claude_result(transcript)

    assert result.final_message == "Upgraded and tests pass."
    assert result.model == "claude-test"


def test_claude_error_result_raises(tmp_path):
    transcript = write_jsonl(tmp_path, [
        {"type": "system", "subtype": "init", "model": "claude-test"},
        {"type": "result", "subtype": "error_max_budget_usd", "is_error": True},
    ])

    with pytest.raises(AgentError, match="error_max_budget_usd"):
        claude_result(transcript)


def test_claude_transcript_without_result_raises(tmp_path):
    transcript = write_jsonl(tmp_path, [{"type": "system", "subtype": "init", "model": "claude-test"}])

    with pytest.raises(AgentError, match="no result"):
        claude_result(transcript)


def test_copilot_result_reads_last_non_empty_message_and_model(tmp_path):
    transcript = write_jsonl(tmp_path, [
        {"type": "assistant.message", "data": {"model": "gpt-test", "content": "First."}},
        {"type": "assistant.message", "data": {"model": "gpt-test", "content": "Done, tests pass."}},
        {"type": "assistant.message", "data": {"model": "gpt-test", "content": ""}},
        {"type": "result", "exitCode": 0},
    ])

    result = copilot_result(transcript)

    assert result.final_message == "Done, tests pass."
    assert result.model == "gpt-test"


def test_copilot_non_zero_exit_code_raises(tmp_path):
    transcript = write_jsonl(tmp_path, [
        {"type": "assistant.message", "data": {"model": "gpt-test", "content": "Gave up."}},
        {"type": "result", "exitCode": 1},
    ])

    with pytest.raises(AgentError, match="exit code 1"):
        copilot_result(transcript)


def test_copilot_transcript_without_result_raises(tmp_path):
    transcript = write_jsonl(tmp_path, [{"type": "assistant.message", "data": {"model": "m", "content": "x"}}])

    with pytest.raises(AgentError, match="no result"):
        copilot_result(transcript)


def test_transcript_with_a_non_json_line_raises(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"type": "result"}\nnot json\n')

    with pytest.raises(AgentError, match="line 2"):
        claude_result(transcript)
