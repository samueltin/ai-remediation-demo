"""Remediation workflow entry point.

Usage: python orchestrator/remediate.py tickets/SEC-102.json --agent claude

The workflow runs these stages in order; the names match the README diagram:
Load ticket, Check toolchain, Prepare workspace, Scan before, Baseline tests, Try version bump,
Agent attempts, Commit change, Scan after, Check guardrails, Write summary.
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
from guardrails import DEFAULT_DIFF_LIMIT, Check, check_all
from maven import (BuildEnvironmentError, BuildResult, VersionBumpError, bump_version, check_java_version,
                   describe, run_tests)
from scanner import Finding, ScanComparison, ScanReportError, compare, findings_for, scan
from summary import render_summary
from ticket import Ticket, TicketError, load_ticket
from workspace import (WORKSPACES_ROOT, WorkspaceError, commit_change, create_workspace, has_changes, init_git,
                       reset_workspace, snapshot)

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
MAX_ATTEMPTS = 3
TOTAL_STEPS = 11
_step_numbers = itertools.count(1)


class RunOutcome(Enum):
    # The value is the process exit code.
    READY_FOR_REVIEW = 0
    FAILED = 1
    NEEDS_HUMAN_ATTENTION = 2


class StopRun(Exception):
    """Ends the run early, before a change exists, with the given outcome and reason."""

    def __init__(self, outcome: RunOutcome, reason: str):
        super().__init__(reason)
        self.outcome = outcome
        self.reason = reason


@dataclass(frozen=True)
class Options:
    agent: str
    always_agent: bool
    max_attempts: int
    diff_limit: int


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


def save_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2))


# Stages, in order.

def check_toolchain() -> None:
    step("Check toolchain")
    detail(f"Maven runs on Java {check_java_version(REPO_ROOT)}")


def prepare_workspace(ticket: Ticket, run_id: str) -> tuple[Path, str, str]:
    """Returns the workspace, the fix branch and the baseline commit."""
    step("Prepare workspace")
    workspace = create_workspace(REPO_ROOT / ticket.service, WORKSPACES_ROOT / run_id, REPO_ROOT)
    branch = init_git(workspace, ticket.ticket_id)
    baseline_sha = run(["git", "rev-parse", "HEAD"], cwd=workspace).strip()
    detail(f"copied {ticket.service}/ (without target/) to {workspace}")
    detail(f"baseline {baseline_sha[:7]} committed on main, now on branch {branch}")
    return workspace, branch, baseline_sha


def scan_before(ticket: Ticket, workspace: Path, run_dir: Path) -> set[Finding]:
    """Scans the untouched workspace and confirms the ticket's finding is there, at the ticket's version."""
    step("Scan before")
    report = run_dir / "scan_before.json"
    findings = scan(workspace, report)
    detail(f"{len(findings)} findings, report saved to {report.relative_to(REPO_ROOT)}")
    matches = findings_for(findings, ticket.cve_id, ticket.library)
    if not matches:
        raise StopRun(RunOutcome.NEEDS_HUMAN_ATTENTION,
                      f"the scan does not report {ticket.cve_id} in {ticket.library}. "
                      "The ticket may be stale or already fixed.")
    versions = sorted(f.installed_version for f in matches)
    if versions != [ticket.current_version]:
        raise StopRun(RunOutcome.NEEDS_HUMAN_ATTENTION,
                      f"the scan reports {ticket.cve_id} in {ticket.library} at version {', '.join(versions)}, "
                      f"but the ticket says {ticket.current_version}.")
    detail(f"found: {ticket.cve_id} in {ticket.library} {ticket.current_version}")
    return findings


def baseline_tests(workspace: Path, run_dir: Path) -> BuildResult:
    """Runs the tests before any change; the counts are the baseline for guardrail 9."""
    step("Baseline tests")
    baseline = run_tests(workspace, run_dir / "mvn_test_baseline.log")
    save_json(run_dir / "baseline_tests.json", asdict(baseline))
    detail(f"mvn test {'PASS' if baseline.passed else 'FAIL'}: {describe(baseline.counts)} "
           f"in {baseline.duration_seconds}s")
    if not baseline.passed or baseline.counts.run == 0 or baseline.counts.skipped:
        raise StopRun(RunOutcome.FAILED,
                      f"the baseline is not green before any change ({describe(baseline.counts)}). "
                      "Fix the baseline first.")
    return baseline


def try_version_bump(ticket: Ticket, workspace: Path, run_dir: Path) -> BuildResult | None:
    """Deterministic first, AI second: applies only the version change and runs the clean build and tests.

    Returns None if the plain bump cannot be applied to this pom.xml.
    """
    step("Try version bump")
    pom = workspace / "pom.xml"
    try:
        bumped = bump_version(pom.read_text(), ticket.library, ticket.current_version, ticket.target_version)
    except VersionBumpError as error:
        detail(f"cannot apply the plain version bump: {error}")
        return None
    pom.write_text(bumped)
    result = run_tests(workspace, run_dir / "mvn_test_version_bump.log")
    save_json(run_dir / "version_bump.json", asdict(result))
    detail(f"{ticket.library} {ticket.current_version} -> {ticket.target_version}: mvn test "
           f"{'PASS' if result.passed else 'FAIL'} ({describe(result.counts)}) in {result.duration_seconds}s")
    if not result.passed:
        detail("the upgrade alone breaks the build:")
        for line in result.error_lines[:5]:
            detail(f"  {line}")
    return result


def agent_attempts(ticket: Ticket, options: Options, version_bump: BuildResult | None,
                   workspace: Path, run_dir: Path) -> tuple[list[Attempt], BuildResult]:
    """Calls the agent only when the plain bump is not enough (or --always-agent).

    Returns the attempts (none for a deterministic fix) and the final build.
    """
    if version_bump is not None and version_bump.passed and not options.always_agent:
        step("Agent attempts: skipped, the version bump alone builds and passes the tests")
        return [], version_bump

    step(f"Agent attempts: {options.agent}, at most {options.max_attempts}")
    if version_bump is not None:
        reset_workspace(workspace)
        detail("workspace reset to the baseline before calling the agent")
    bump_errors = version_bump.error_lines if version_bump is not None and not version_bump.passed else ()
    attempts = run_attempts(ticket, options.agent, AGENTS[options.agent], run_tests, workspace, run_dir,
                            bump_errors, options.max_attempts)
    last = attempts[-1]
    detail("agent's final message:")
    for line in last.final_message.strip().splitlines():
        detail(f"  | {line}")
    if not last.changed:
        raise StopRun(RunOutcome.NEEDS_HUMAN_ATTENTION,
                      f"{declined_reason(attempts)}; the workspace is unchanged. See the agent's final message.")
    return attempts, last.build


def commit_to_fix_branch(ticket: Ticket, workspace: Path) -> None:
    """Committed even when red, so the reviewer sees exactly the state the guardrails check."""
    step("Commit change")
    commit_change(workspace, f"{ticket.ticket_id}: {ticket.title}")
    for line in run(["git", "show", "--stat", "--format=%h %s", "HEAD"], cwd=workspace).splitlines():
        detail(line)


def scan_after(ticket: Ticket, workspace: Path, run_dir: Path,
               findings_before: set[Finding]) -> tuple[set[Finding], ScanComparison]:
    step("Scan after")
    findings_after = scan(workspace, run_dir / "scan_after.json")
    comparison = compare(findings_before, findings_after, ticket.cve_id, ticket.library)
    detail(f"{len(findings_after)} findings (before: {len(findings_before)}), "
           f"{ticket.cve_id} {'gone' if comparison.ticket_finding_gone else 'STILL PRESENT'}, "
           f"{len(comparison.new_findings)} new, {len(comparison.resolved)} resolved")
    return findings_after, comparison


def check_guardrails(ticket: Ticket, options: Options, workspace: Path, baseline_sha: str, baseline: BuildResult,
                     final_build: BuildResult, attempts: list[Attempt], comparison: ScanComparison,
                     run_dir: Path) -> list[Check]:
    step("Check guardrails")
    transcripts = [transcript_path(run_dir, options.agent, a) for a in attempts]
    checks = check_all(ticket, workspace, baseline_sha, baseline.counts, final_build, len(attempts),
                       options.max_attempts, transcripts, options.diff_limit, comparison)
    save_json(run_dir / "guardrails.json", [asdict(c) for c in checks])
    for check in checks:
        detail(f"{'PASS' if check.passed else 'FAIL'}  {check.number}. {check.name}: {check.reason}")
    return checks


def decide_outcome(checks: list[Check], attempts: list[Attempt]) -> tuple[RunOutcome, str]:
    problems = [f"guardrail {c.number} failed: {c.reason}" for c in checks if not c.passed]
    if declined_reason(attempts):
        problems.insert(0, declined_reason(attempts))
    if problems:
        return RunOutcome.NEEDS_HUMAN_ATTENTION, "; ".join(problems)
    if attempts:
        return RunOutcome.READY_FOR_REVIEW, f"all guardrails pass after {len(attempts)} attempt(s)"
    return RunOutcome.READY_FOR_REVIEW, "all guardrails pass with the version bump alone, no agent"


def write_summary(ticket: Ticket, options: Options, outcome: RunOutcome, reason: str, workspace: Path,
                  branch: str, baseline: BuildResult, version_bump: BuildResult | None, attempts: list[Attempt],
                  checks: list[Check], comparison: ScanComparison, findings_before: set[Finding],
                  findings_after: set[Finding], run_dir: Path) -> None:
    step("Write summary")

    def git(*args: str) -> str:
        return run(["git", *args], cwd=workspace)

    summary = render_summary(
        ticket=ticket, outcome=outcome.name, reason=reason, agent=options.agent, attempts=attempts,
        version_bump=version_bump, always_agent=options.always_agent,
        baseline=baseline, checks=checks, comparison=comparison,
        findings_before=len(findings_before), findings_after=len(findings_after),
        diffstat=git("diff", "--stat", "main", "HEAD"), diff=git("diff", "main", "HEAD"),
        workspace=workspace, branch=branch, commit=git("rev-parse", "--short", "HEAD").strip(),
        transcripts=[transcript_path(run_dir, options.agent, a).name for a in attempts])
    (run_dir / "MR_SUMMARY.md").write_text(summary)
    detail(f"written to {(run_dir / 'MR_SUMMARY.md').relative_to(REPO_ROOT)}")


def run_workflow(ticket: Ticket, options: Options, run_id: str, run_dir: Path) -> tuple[RunOutcome, str]:
    check_toolchain()
    workspace, branch, baseline_sha = prepare_workspace(ticket, run_id)
    findings_before = scan_before(ticket, workspace, run_dir)
    baseline = baseline_tests(workspace, run_dir)
    version_bump = try_version_bump(ticket, workspace, run_dir)
    attempts, final_build = agent_attempts(ticket, options, version_bump, workspace, run_dir)
    commit_to_fix_branch(ticket, workspace)
    findings_after, comparison = scan_after(ticket, workspace, run_dir, findings_before)
    checks = check_guardrails(ticket, options, workspace, baseline_sha, baseline, final_build, attempts,
                              comparison, run_dir)
    outcome, reason = decide_outcome(checks, attempts)
    write_summary(ticket, options, outcome, reason, workspace, branch, baseline, version_bump, attempts,
                  checks, comparison, findings_before, findings_after, run_dir)
    return outcome, reason


# The agent loop and its helpers.

def run_attempts(ticket: Ticket, agent_name: str,
                 run_agent: Callable[[Path, str, Path], AgentResult],
                 test_build: Callable[[Path, Path], BuildResult],
                 workspace: Path, run_dir: Path, bump_errors: tuple[str, ...] = (),
                 max_attempts: int = MAX_ATTEMPTS) -> list[Attempt]:
    """Runs the agent, then the tests, up to max_attempts times (guardrail 3, at most MAX_ATTEMPTS).

    Stops at the first green build, or when an attempt adds no new change: an agent that
    declined once will only decline again, so another attempt would cost money for nothing.
    A retry gets the previous build errors, and continues from the current workspace.
    """
    attempts: list[Attempt] = []
    previous_errors: tuple[str, ...] = ()
    for number in range(1, max_attempts + 1):
        prompt = build_prompt(ticket, previous_errors, bump_errors if number == 1 else ())
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
        save_json(run_dir / "attempts.json", [asdict(a) for a in attempts])
        detail(f"attempt {number}: agent {agent_seconds}s, new change: {'yes' if new_change else 'no'}, "
               f"mvn test {'PASS' if build.passed else 'FAIL'} ({describe(build.counts)})")
        if build.passed or not new_change:
            break
        previous_errors = build.error_lines
    return attempts


def declined_reason(attempts: list[Attempt]) -> str | None:
    if attempts and not attempts[-1].new_change:
        return f"agent declined, no new change in attempt {attempts[-1].number}"
    return None


def transcript_path(run_dir: Path, agent: str, attempt: Attempt) -> Path:
    return run_dir / f"{agent}_attempt_{attempt.number}.jsonl"


# Entry point.

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
    parser.add_argument("--always-agent", action="store_true",
                        help="call the agent even when the plain version bump already passes")
    parser.add_argument("--max-attempts", type=int, choices=range(1, MAX_ATTEMPTS + 1), default=MAX_ATTEMPTS,
                        help=f"agent attempts allowed (guardrail 3); can only lower the limit of {MAX_ATTEMPTS}")
    parser.add_argument("--max-diff-lines", type=int, default=DEFAULT_DIFF_LIMIT,
                        help=f"guardrail 4 limit on changed lines (default {DEFAULT_DIFF_LIMIT})")
    args = parser.parse_args(argv)
    options = Options(args.agent, args.always_agent, args.max_attempts, args.max_diff_lines)

    run_dir = None
    try:
        step("Load ticket")
        ticket = load_ticket(args.ticket)
        detail(f"{ticket.ticket_id} {ticket.severity} {ticket.cve_id}: "
               f"{ticket.library} {ticket.current_version} -> {ticket.target_version} (agent: {options.agent})")
        run_id = f"{ticket.ticket_id}-{datetime.now():%Y%m%d-%H%M%S}"
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True)
        outcome, reason = run_workflow(ticket, options, run_id, run_dir)
    except StopRun as stop:
        outcome, reason = stop.outcome, stop.reason
    except (TicketError, WorkspaceError, CommandError, ScanReportError, AgentError,
            BuildEnvironmentError) as error:
        outcome, reason = RunOutcome.FAILED, str(error)
    return finish(outcome, reason, run_dir)


if __name__ == "__main__":
    sys.exit(main())
