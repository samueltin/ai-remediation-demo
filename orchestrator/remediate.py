"""Remediation workflow entry point.

Usage: python orchestrator/remediate.py tickets/SEC-102.json --agent claude
"""

import argparse
import itertools
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from agents import AGENTS, AgentError, AgentResult, build_prompt
from commands import CommandError, run
from guardrails import DEFAULT_DIFF_LIMIT, check_all
from maven import BuildEnvironmentError, BuildResult, check_java_version, describe, run_tests
from scanner import ScanReportError, compare, findings_for, scan
from summary import render_summary
from ticket import Ticket, TicketError, load_ticket
from workspace import (WORKSPACES_ROOT, WorkspaceError, commit_change, create_workspace, has_changes, init_git,
                       snapshot)

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
MAX_ATTEMPTS = 3
TOTAL_STEPS = 12
_step_numbers = itertools.count(1)


class RunOutcome(Enum):
    # The value is the process exit code.
    READY_FOR_REVIEW = 0
    FAILED = 1
    NEEDS_HUMAN_ATTENTION = 2


@dataclass(frozen=True)
class Attempt:
    number: int
    model: str
    final_message: str
    changed: bool        # the workspace differs from the baseline
    new_change: bool     # this attempt changed something compared with the previous one
    agent_seconds: float
    build: BuildResult


def step(message: str) -> None:
    print(f"[{next(_step_numbers)}/{TOTAL_STEPS}] {message}")


def detail(message: str) -> None:
    print(f"      {message}")


def run_attempts(ticket: Ticket, agent_name: str,
                 run_agent: Callable[[Path, str, Path], AgentResult],
                 test_build: Callable[[Path, Path], BuildResult],
                 workspace: Path, run_dir: Path) -> list[Attempt]:
    """Runs the agent, then the tests, up to MAX_ATTEMPTS times (guardrail 3).

    Stops at the first green build, or when an attempt adds no new change: an agent that
    declined once will only decline again, so another attempt would cost money for nothing.
    A retry gets the previous build errors, and continues from the current workspace.
    """
    attempts: list[Attempt] = []
    previous_errors: tuple[str, ...] = ()
    for number in range(1, MAX_ATTEMPTS + 1):
        prompt = build_prompt(ticket, previous_errors)
        (run_dir / f"prompt_attempt_{number}.txt").write_text(prompt)
        detail(f"attempt {number}: running {agent_name}")
        before = snapshot(workspace)
        started = time.monotonic()
        result = run_agent(workspace, prompt, run_dir / f"{agent_name}_attempt_{number}.jsonl")
        agent_seconds = round(time.monotonic() - started, 1)
        new_change = snapshot(workspace) != before
        changed = has_changes(workspace)
        build = test_build(workspace, run_dir / f"mvn_test_attempt_{number}.log")

        attempts.append(Attempt(number, result.model, result.final_message, changed, new_change,
                                agent_seconds, build))
        (run_dir / "attempts.json").write_text(json.dumps([asdict(a) for a in attempts], indent=2))
        detail(f"attempt {number}: agent {agent_seconds}s, new change: {'yes' if new_change else 'no'}, "
               f"mvn test {'PASS' if build.passed else 'FAIL'} ({describe(build.counts)})")
        if build.passed or not new_change:
            break
        previous_errors = build.error_lines
    return attempts


def declined_reason(attempts: list[Attempt]) -> str | None:
    last = attempts[-1]
    if not last.new_change:
        return f"agent declined, no new change in attempt {last.number}"
    return None


def run_workflow(ticket: Ticket, agent: str, diff_limit: int, run_id: str,
                 run_dir: Path) -> tuple[RunOutcome, str]:
    step("Checking that Maven runs on JDK 17")
    detail(f"Java {check_java_version(REPO_ROOT)}")

    step("Creating isolated workspace")
    workspace = create_workspace(REPO_ROOT / ticket.service, WORKSPACES_ROOT / run_id, REPO_ROOT)
    detail(f"copied {ticket.service}/ (without target/) to {workspace}")

    step("Initialising git in the workspace")
    branch = init_git(workspace, ticket.ticket_id)
    baseline_sha = run(["git", "rev-parse", "HEAD"], cwd=workspace).strip()
    detail(f"baseline {baseline_sha[:7]} committed on main, now on branch {branch}")

    step("Scanning dependencies before the change")
    report = run_dir / "scan_before.json"
    findings = scan(workspace, report)
    detail(f"{len(findings)} findings, report saved to {report.relative_to(REPO_ROOT)}")

    step(f"Confirming {ticket.cve_id} is present in {ticket.library}")
    matches = findings_for(findings, ticket.cve_id, ticket.library)
    if not matches:
        return (RunOutcome.NEEDS_HUMAN_ATTENTION,
                f"the scan does not report {ticket.cve_id} in {ticket.library}. "
                "The ticket may be stale or already fixed.")
    versions = sorted(f.installed_version for f in matches)
    if versions != [ticket.current_version]:
        return (RunOutcome.NEEDS_HUMAN_ATTENTION,
                f"the scan reports {ticket.cve_id} in {ticket.library} at version {', '.join(versions)}, "
                f"but the ticket says {ticket.current_version}.")
    detail(f"found: {ticket.cve_id} in {ticket.library} {ticket.current_version}")

    step("Running the tests on the untouched workspace (baseline for guardrail 9)")
    baseline = run_tests(workspace, run_dir / "mvn_test_baseline.log")
    (run_dir / "baseline_tests.json").write_text(json.dumps(asdict(baseline), indent=2))
    detail(f"mvn test {'PASS' if baseline.passed else 'FAIL'}: {describe(baseline.counts)} "
           f"in {baseline.duration_seconds}s")
    if not baseline.passed or baseline.counts.run == 0 or baseline.counts.skipped:
        return (RunOutcome.FAILED,
                f"the baseline is not green before any change ({describe(baseline.counts)}). "
                "Fix the baseline first.")

    step(f"Running the agent and the tests (at most {MAX_ATTEMPTS} attempts)")
    attempts = run_attempts(ticket, agent, AGENTS[agent], run_tests, workspace, run_dir)
    last = attempts[-1]
    detail("agent's final message:")
    for line in last.final_message.strip().splitlines():
        detail(f"  | {line}")
    if not last.changed:
        return (RunOutcome.NEEDS_HUMAN_ATTENTION,
                f"{declined_reason(attempts)}; the workspace is unchanged. See the agent's final message.")

    # Committed even when red, so the reviewer sees exactly the state the guardrails checked.
    step("Committing the agent's change on the fix branch")
    commit_change(workspace, f"{ticket.ticket_id}: {ticket.title}")
    for line in run(["git", "show", "--stat", "--format=%h %s", "HEAD"], cwd=workspace).splitlines():
        detail(line)

    step("Scanning dependencies after the change")
    findings_after = scan(workspace, run_dir / "scan_after.json")
    comparison = compare(findings, findings_after, ticket.cve_id, ticket.library)
    detail(f"{len(findings_after)} findings (before: {len(findings)}), "
           f"{ticket.cve_id} {'gone' if comparison.ticket_finding_gone else 'STILL PRESENT'}, "
           f"{len(comparison.new_findings)} new, {len(comparison.resolved)} resolved")

    step("Checking guardrails")
    transcripts = [run_dir / f"{agent}_attempt_{a.number}.jsonl" for a in attempts]
    checks = check_all(ticket, workspace, baseline_sha, baseline.counts, last.build, len(attempts),
                       MAX_ATTEMPTS, transcripts, diff_limit, comparison)
    (run_dir / "guardrails.json").write_text(json.dumps([asdict(c) for c in checks], indent=2))
    for check in checks:
        detail(f"{'PASS' if check.passed else 'FAIL'}  {check.number}. {check.name}: {check.reason}")
    problems = [f"guardrail {c.number} failed: {c.reason}" for c in checks if not c.passed]
    if declined_reason(attempts):
        problems.insert(0, declined_reason(attempts))
    if problems:
        outcome, reason = RunOutcome.NEEDS_HUMAN_ATTENTION, "; ".join(problems)
    else:
        outcome, reason = (RunOutcome.READY_FOR_REVIEW,
                           f"all guardrails pass after {len(attempts)} attempt(s)")

    step("Writing the merge request summary")
    def git(*args: str) -> str:
        return run(["git", *args], cwd=workspace)
    summary = render_summary(
        ticket=ticket, outcome=outcome.name, reason=reason, agent=agent, attempts=attempts,
        baseline=baseline, checks=checks, comparison=comparison,
        findings_before=len(findings), findings_after=len(findings_after),
        diffstat=git("diff", "--stat", "main", "HEAD"), diff=git("diff", "main", "HEAD"),
        workspace=workspace, branch=branch, commit=git("rev-parse", "--short", "HEAD").strip(),
        transcripts=[path.name for path in transcripts])
    (run_dir / "MR_SUMMARY.md").write_text(summary)
    detail(f"written to {(run_dir / 'MR_SUMMARY.md').relative_to(REPO_ROOT)}")
    return outcome, reason


def finish(outcome: RunOutcome, reason: str, run_dir: Path | None) -> int:
    line = f"{outcome.name}: {reason}"
    print(f"\n{line}")
    if run_dir is not None:
        (run_dir / "outcome.txt").write_text(line + "\n")
        print(f"Run folder: {run_dir.relative_to(REPO_ROOT)}")
        if (run_dir / "MR_SUMMARY.md").is_file():
            print(f"Merge request summary: {(run_dir / 'MR_SUMMARY.md').relative_to(REPO_ROOT)}")
    return outcome.value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remediate one security ticket in an isolated workspace.")
    parser.add_argument("ticket", type=Path, help="path to the ticket JSON file")
    parser.add_argument("--agent", required=True, choices=sorted(AGENTS),
                        help="coding agent CLI to use (unsafe-sim is a simulated misbehaving agent)")
    parser.add_argument("--max-diff-lines", type=int, default=DEFAULT_DIFF_LIMIT,
                        help=f"guardrail 4 limit on changed lines (default {DEFAULT_DIFF_LIMIT})")
    args = parser.parse_args(argv)

    run_dir = None
    try:
        step(f"Loading ticket {args.ticket}")
        ticket = load_ticket(args.ticket)
        detail(f"{ticket.ticket_id} {ticket.severity} {ticket.cve_id}: "
               f"{ticket.library} {ticket.current_version} -> {ticket.target_version} (agent: {args.agent})")

        run_id = f"{ticket.ticket_id}-{datetime.now():%Y%m%d-%H%M%S}"
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True)
        outcome, reason = run_workflow(ticket, args.agent, args.max_diff_lines, run_id, run_dir)
    except (TicketError, WorkspaceError, CommandError, ScanReportError, AgentError,
            BuildEnvironmentError) as error:
        outcome, reason = RunOutcome.FAILED, str(error)
    return finish(outcome, reason, run_dir)


if __name__ == "__main__":
    sys.exit(main())
