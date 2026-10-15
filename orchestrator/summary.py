"""Writes MR_SUMMARY.md, the handover document for the human reviewer.

It is written for someone who did not watch the run: what changed, the evidence that it is
safe (tests, scans, guardrails), and where the full audit trail is.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from guardrails import Check
from maven import BuildResult
from scanner import ScanComparison
from ticket import Ticket

if TYPE_CHECKING:
    from remediate import Attempt

# demo-shortcut: the ticket link is built from the ticket ID. Production: the issue tracker's own URL.
ISSUE_TRACKER_URL = "https://issues.example.com/browse/"
HANDOVER_LINE = "Requires human review and approval. Not merged."
MAX_DIFF_LINES_SHOWN = 100


def ticket_url(ticket_id: str) -> str:
    return f"{ISSUE_TRACKER_URL}{ticket_id}"


def render_summary(*, ticket: Ticket, outcome: str, reason: str, agent: str, attempts: list[Attempt],
                   baseline: BuildResult, checks: list[Check], comparison: ScanComparison,
                   findings_before: int, findings_after: int, diffstat: str, diff: str,
                   workspace: Path, branch: str, commit: str, transcripts: list[str]) -> str:
    last = attempts[-1]
    diff_lines = diff.splitlines()
    shown_diff = "\n".join(diff_lines[:MAX_DIFF_LINES_SHOWN])
    if len(diff_lines) > MAX_DIFF_LINES_SHOWN:
        shown_diff += f"\n... {len(diff_lines) - MAX_DIFF_LINES_SHOWN} more lines, see git diff main fix branch"

    lines = [
        f"# {ticket.ticket_id}: {ticket.title}",
        "",
        f"**Outcome: {outcome}**: {reason}",
        "",
        HANDOVER_LINE,
        "",
        "| | |",
        "|---|---|",
        f"| Ticket | [{ticket.ticket_id}]({ticket_url(ticket.ticket_id)}) |",
        f"| Finding | {ticket.cve_id} in {ticket.library} {ticket.current_version}, "
        f"{ticket.severity} (severity as reported by the scanner) |",
        f"| Change requested | {ticket.library} {ticket.current_version} to {ticket.target_version} |",
        f"| Branch | `{branch}` at `{commit}` in `{workspace}` |",
        f"| Agent | {agent} (model {last.model}), {len(attempts)} attempt(s) |",
        "",
        "## What changed",
        "",
        "```",
        diffstat.rstrip(),
        "```",
        "",
        "```diff",
        shown_diff,
        "```",
        "",
        "## Tests (run by the workflow, not by the agent)",
        "",
        "| Run | Result | Tests run | Failed | Errors | Skipped |",
        "|---|---|---|---|---|---|",
        _test_row("Baseline (before the agent)", baseline),
        *[_test_row(f"Attempt {a.number}", a.build) for a in attempts],
        "",
        "## Dependency scan (Trivy)",
        "",
        f"Findings before: {findings_before}. Findings after: {findings_after}. "
        "Compared as sets of (CVE ID, package, installed version).",
        "",
        f"- {ticket.cve_id} in {ticket.library}: {'gone' if comparison.ticket_finding_gone else '**still present**'}",
        f"- New findings: {_findings(comparison.new_findings) or 'none'}",
        f"- Resolved: {_findings(comparison.resolved) or 'none'}",
        "- Other findings are unchanged. They come from libraries managed by Spring Boot and are out of",
        "  scope for this ticket.",
        "",
        "## Guardrails",
        "",
        "| # | Guardrail | Result | Detail |",
        "|---|---|---|---|",
        *[f"| {c.number} | {c.name} | {'PASS' if c.passed else '**FAIL**'} | {_cell(c.reason)} |" for c in checks],
        "",
        "## Agent attempts",
        "",
        "| Attempt | Agent time | New change | mvn test | Transcript |",
        "|---|---|---|---|---|",
        *[f"| {a.number} | {a.agent_seconds}s | {'yes' if a.new_change else 'no'} | "
          f"{'PASS' if a.build.passed else 'FAIL'} | [{name}]({name}) |" for a, name in zip(attempts, transcripts)],
        "",
        "Agent's own summary of its last attempt (unverified; the evidence above is what counts):",
        "",
        *[f"> {line}" if line else ">" for line in last.final_message.strip().splitlines()],
        "",
        "## Audit trail",
        "",
        "All files are in this run folder: the prompt for each attempt (`prompt_attempt_N.txt`), the agent",
        "transcripts, the Maven logs (`mvn_test_*.log`), `scan_before.json`, `scan_after.json`,",
        "`attempts.json`, `baseline_tests.json` and `guardrails.json`.",
        "",
        "## For the reviewer",
        "",
        "- Read the diff and check that the change keeps the existing behaviour.",
        "- Approve or reject in the merge request. The workflow does not merge.",
        "",
        HANDOVER_LINE,
        "",
    ]
    return "\n".join(lines)


def _test_row(label: str, build: BuildResult) -> str:
    c = build.counts
    return (f"| {label} | {'PASS' if build.passed else 'FAIL'} | {c.run} | {c.failures} | "
            f"{c.errors} | {c.skipped} |")


def _findings(findings: set) -> str:
    return ", ".join(f"{f.cve_id} in {f.package} {f.installed_version}" for f in sorted(findings))


def _cell(text: str) -> str:
    return text.replace("|", "\\|")
