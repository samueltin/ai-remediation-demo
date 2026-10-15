import json
from pathlib import Path

from agents import AgentResult
from maven import BuildResult, SurefireCounts
from remediate import MAX_ATTEMPTS, declined_reason, run_attempts
from ticket import load_ticket
from workspace import create_workspace, init_git

TICKET = load_ticket(Path(__file__).resolve().parents[2] / "tickets" / "SEC-102.json")
GREEN = BuildResult(passed=True, counts=SurefireCounts(15, 0, 0, 0), error_lines=(), duration_seconds=1.0)


def red(message):
    return BuildResult(passed=False, counts=SurefireCounts(0, 0, 0, 0),
                       error_lines=(f"[ERROR] {message}",), duration_seconds=1.0)


def builds(*results):
    remaining = iter(results)
    return lambda workspace, log_path: next(remaining)


class FakeAgent:
    """Edits pom.xml in the attempts listed in edit_attempts (all attempts by default)."""

    def __init__(self, edits=True, edit_attempts=None):
        self.edit_attempts = edit_attempts if edit_attempts is not None else (range(1, 10) if edits else ())
        self.prompts = []

    def __call__(self, workspace, prompt, transcript):
        self.prompts.append(prompt)
        if len(self.prompts) in self.edit_attempts:
            (workspace / "pom.xml").write_text(f"<project>attempt {len(self.prompts)}</project>")
        return AgentResult(final_message=f"attempt {len(self.prompts)} done", model="fake-model")


def setup(tmp_path):
    service = tmp_path / "repo" / "svc"
    service.mkdir(parents=True)
    (service / "pom.xml").write_text("<project/>")
    workspace = create_workspace(service, tmp_path / "ws", tmp_path / "repo")
    init_git(workspace, TICKET.ticket_id)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return workspace, run_dir


def test_never_more_than_three_attempts(tmp_path):
    workspace, run_dir = setup(tmp_path)
    agent = FakeAgent()

    attempts = run_attempts(TICKET, "fake", agent, builds(*[red("still broken")] * 5), workspace, run_dir)

    assert MAX_ATTEMPTS == 3
    assert len(attempts) == 3
    assert len(agent.prompts) == 3
    assert not attempts[-1].build.passed


def test_retry_prompt_carries_the_previous_build_errors(tmp_path):
    workspace, run_dir = setup(tmp_path)
    agent = FakeAgent()

    run_attempts(TICKET, "fake", agent, builds(red("compile error one"), red("compile error two"), GREEN),
                 workspace, run_dir)

    assert "<build_output>" not in agent.prompts[0]
    assert "compile error one" in agent.prompts[1]
    assert "compile error two" in agent.prompts[2]


def test_stops_at_the_first_green_build(tmp_path):
    workspace, run_dir = setup(tmp_path)

    attempts = run_attempts(TICKET, "fake", FakeAgent(), builds(red("broken"), GREEN), workspace, run_dir)

    assert [a.build.passed for a in attempts] == [False, True]


def test_stops_when_the_agent_changes_nothing(tmp_path):
    workspace, run_dir = setup(tmp_path)

    attempts = run_attempts(TICKET, "fake", FakeAgent(edits=False), builds(GREEN, GREEN), workspace, run_dir)

    assert len(attempts) == 1
    assert not attempts[0].changed


def test_each_attempt_is_recorded_in_the_run_folder(tmp_path):
    workspace, run_dir = setup(tmp_path)

    run_attempts(TICKET, "fake", FakeAgent(), builds(red("broken"), GREEN), workspace, run_dir)

    records = json.loads((run_dir / "attempts.json").read_text())
    assert [(r["number"], r["build"]["passed"], r["model"]) for r in records] == [
        (1, False, "fake-model"), (2, True, "fake-model")]
    assert all("agent_seconds" in r for r in records)
    assert (run_dir / "prompt_attempt_2.txt").is_file()


def test_stops_when_an_attempt_adds_no_new_change(tmp_path):
    # SEC-103: attempt 1 changed the pom, then the agent refused; attempt 3 would only repeat the refusal.
    workspace, run_dir = setup(tmp_path)
    agent = FakeAgent(edit_attempts={1})

    attempts = run_attempts(TICKET, "fake", agent, builds(*[red("test does not compile")] * 3),
                            workspace, run_dir)

    assert len(agent.prompts) == 2
    assert [(a.changed, a.new_change) for a in attempts] == [(True, True), (True, False)]
    assert declined_reason(attempts) == "agent declined, no new change in attempt 2"


def test_no_declined_reason_when_the_last_attempt_made_progress(tmp_path):
    workspace, run_dir = setup(tmp_path)

    attempts = run_attempts(TICKET, "fake", FakeAgent(), builds(red("broken"), GREEN), workspace, run_dir)

    assert declined_reason(attempts) is None


def test_bump_errors_go_into_the_first_prompt_only(tmp_path):
    workspace, run_dir = setup(tmp_path)
    agent = FakeAgent()

    run_attempts(TICKET, "fake", agent, builds(red("after attempt one"), GREEN), workspace, run_dir,
                 bump_errors=("[ERROR] bump alone fails",))

    assert "bump alone fails" in agent.prompts[0]
    assert "bump alone fails" not in agent.prompts[1]
    assert "after attempt one" in agent.prompts[1]


def test_no_declined_reason_without_attempts():
    assert declined_reason([]) is None


def test_a_lower_attempt_limit_is_respected(tmp_path):
    # Used to cap paid agent calls, for example one premium request on a free plan.
    workspace, run_dir = setup(tmp_path)
    agent = FakeAgent()

    attempts = run_attempts(TICKET, "fake", agent, builds(*[red("broken")] * 3), workspace, run_dir,
                            max_attempts=1)

    assert len(attempts) == 1
    assert len(agent.prompts) == 1
