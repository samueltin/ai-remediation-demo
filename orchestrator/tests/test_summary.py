from pathlib import Path

from guardrails import Check
from maven import BuildResult, SurefireCounts
from remediate import Attempt
from scanner import Finding, compare
from summary import render_summary, ticket_url
from ticket import load_ticket

TICKET = load_ticket(Path(__file__).resolve().parents[2] / "tickets" / "SEC-102.json")
COUNTS = SurefireCounts(run=15, failures=0, errors=0, skipped=0)
GREEN = BuildResult(True, COUNTS, (), 12.0)
RED = BuildResult(False, SurefireCounts(0, 0, 0, 0), ("[ERROR] incompatible types",), 9.0)
YAML_OLD = Finding("CVE-2022-1471", "org.yaml:snakeyaml", "1.33")
TOMCAT = Finding("CVE-2026-65182", "org.apache.tomcat.embed:tomcat-embed-core", "10.1.55")


TWO_ATTEMPTS = [Attempt(1, "claude-test", "Fixed | done", True, True, 40.0, RED),
                Attempt(2, "claude-test", "Upgraded and fixed the constructor.", True, True, 30.0, GREEN)]


def render(outcome="READY_FOR_REVIEW", reason="all guardrails pass", checks=None, attempts=TWO_ATTEMPTS,
           version_bump=None, always_agent=False, transcripts=("claude_attempt_1.jsonl", "claude_attempt_2.jsonl")):
    return render_summary(
        ticket=TICKET, outcome=outcome, reason=reason, agent="claude",
        attempts=attempts, version_bump=version_bump, always_agent=always_agent,
        baseline=GREEN,
        checks=checks or [Check(1, "No changes under src/test/", True, "no test files changed"),
                          Check(5, "Scan before and after", True, "CVE-2022-1471 gone, no new findings")],
        comparison=compare({YAML_OLD, TOMCAT}, {TOMCAT}, TICKET.cve_id, TICKET.library),
        findings_before=2, findings_after=1,
        diffstat=" pom.xml | 2 +-\n 1 file changed",
        diff="-            <version>1.33</version>\n+            <version>2.4</version>",
        workspace=Path("/tmp/remediation-workspaces/SEC-102-x"), branch="fix/SEC-102", commit="a85d79e",
        transcripts=list(transcripts))


def test_ticket_link_is_built_from_the_ticket_id():
    assert ticket_url("SEC-102") == "https://issues.example.com/browse/SEC-102"


def test_summary_has_everything_a_reviewer_needs():
    text = render()

    assert text.startswith("# SEC-102: Upgrade snakeyaml to fix CVE-2022-1471")
    assert "[SEC-102](https://issues.example.com/browse/SEC-102)" in text
    assert "CVE-2022-1471" in text
    assert "HIGH (severity as reported by the scanner)" in text
    assert "**Outcome: READY_FOR_REVIEW**" in text
    assert "+            <version>2.4</version>" in text
    assert "| Baseline (before the agent) | PASS | 15 | 0 | 0 | 0 |" in text
    assert "| Attempt 1 | FAIL | 0 | 0 | 0 | 0 |" in text
    assert "Findings before: 2. Findings after: 1." in text
    assert "New findings: none" in text
    assert "| 1 | No changes under src/test/ | PASS | no test files changed |" in text
    assert "[claude_attempt_2.jsonl](claude_attempt_2.jsonl)" in text
    assert "claude (model claude-test), 2 attempt(s)" in text
    assert text.rstrip().endswith("Requires human review and approval. Not merged.")


def test_agent_message_is_labelled_unverified_and_pipes_do_not_break_tables():
    text = render()

    assert "unverified" in text
    assert "Upgraded and fixed the constructor." in text


def test_failed_guardrails_and_reason_are_shown():
    text = render(outcome="NEEDS_HUMAN_ATTENTION", reason="guardrail 1 failed: changed test files: A | B",
                  checks=[Check(1, "No changes under src/test/", False, "changed test files: A | B")])

    assert "**Outcome: NEEDS_HUMAN_ATTENTION**" in text
    assert "| 1 | No changes under src/test/ | **FAIL** | changed test files: A \\| B |" in text


def test_deterministic_fix_says_no_agent_was_used():
    text = render(attempts=[], version_bump=GREEN, transcripts=())

    assert "| Agent | none (deterministic fix) |" in text
    assert "| Version bump alone (by the workflow) | PASS | 15 | 0 | 0 | 0 |" in text
    assert "no agent was needed" in text
    assert "Agent attempts" not in text
    assert "Agent's own summary" not in text


def test_failed_bump_is_recorded_as_evidence_before_the_agent():
    text = render(version_bump=RED)

    assert "The upgrade alone breaks the build" in text
    assert "[ERROR] incompatible types" in text
    assert "| Version bump alone (by the workflow) | FAIL |" in text
    assert "claude (model claude-test), 2 attempt(s)" in text


def test_forced_agent_is_explained():
    text = render(version_bump=GREEN, always_agent=True)

    assert "--always-agent" in text
