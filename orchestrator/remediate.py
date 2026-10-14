"""Remediation workflow entry point.

Usage: python orchestrator/remediate.py tickets/SEC-102.json --agent claude
"""

import argparse
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path

from agents import AGENTS, AgentError, build_prompt
from commands import CommandError, run
from scanner import ScanReportError, findings_for, scan
from ticket import Ticket, TicketError, load_ticket
from workspace import WORKSPACES_ROOT, WorkspaceError, create_workspace, init_git

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
TOTAL_STEPS = 6


class RunOutcome(Enum):
    # The value is the process exit code.
    READY_FOR_REVIEW = 0
    FAILED = 1
    NEEDS_HUMAN_ATTENTION = 2


def step(number: int, message: str) -> None:
    print(f"[{number}/{TOTAL_STEPS}] {message}")


def detail(message: str) -> None:
    print(f"      {message}")


def run_workflow(ticket: Ticket, agent: str, run_id: str, run_dir: Path) -> tuple[RunOutcome, str]:
    step(2, "Creating isolated workspace")
    workspace = create_workspace(REPO_ROOT / ticket.service, WORKSPACES_ROOT / run_id, REPO_ROOT)
    detail(f"copied {ticket.service}/ (without target/) to {workspace}")

    step(3, "Initialising git in the workspace")
    branch = init_git(workspace, ticket.ticket_id)
    detail(f"baseline committed on main, now on branch {branch}")

    step(4, "Scanning dependencies before the change")
    report = run_dir / "scan_before.json"
    findings = scan(workspace, report)
    detail(f"{len(findings)} findings, report saved to {report.relative_to(REPO_ROOT)}")

    step(5, f"Confirming {ticket.cve_id} is present in {ticket.library}")
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

    step(6, f"Running agent: {agent} (attempt 1)")
    prompt = build_prompt(ticket)
    (run_dir / "prompt.txt").write_text(prompt)
    transcript = run_dir / f"{agent}_attempt_1.jsonl"
    result = AGENTS[agent](workspace, prompt, transcript)
    detail(f"model: {result.model}, transcript saved to {transcript.relative_to(REPO_ROOT)}")
    detail("agent's final message:")
    for line in result.final_message.strip().splitlines():
        detail(f"  | {line}")
    detail("changed files in the workspace (git status):")
    for line in run(["git", "status", "--short"], cwd=workspace).splitlines() or ["(none)"]:
        detail(f"  {line}")

    # Steps 6 to 8 of the build replace this ending with tests, guardrails, the after scan and the summary.
    return (RunOutcome.NEEDS_HUMAN_ATTENTION,
            "the agent has run, but its change is not yet verified by tests, guardrails or a scan.")


def finish(outcome: RunOutcome, reason: str, run_dir: Path | None) -> int:
    line = f"{outcome.name}: {reason}"
    print(f"\n{line}")
    if run_dir is not None:
        (run_dir / "outcome.txt").write_text(line + "\n")
        print(f"Run folder: {run_dir.relative_to(REPO_ROOT)}")
    return outcome.value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remediate one security ticket in an isolated workspace.")
    parser.add_argument("ticket", type=Path, help="path to the ticket JSON file")
    parser.add_argument("--agent", required=True, choices=AGENTS, help="coding agent CLI to use")
    args = parser.parse_args(argv)

    run_dir = None
    try:
        step(1, f"Loading ticket {args.ticket}")
        ticket = load_ticket(args.ticket)
        detail(f"{ticket.ticket_id} {ticket.severity} {ticket.cve_id}: "
               f"{ticket.library} {ticket.current_version} -> {ticket.target_version} (agent: {args.agent})")

        run_id = f"{ticket.ticket_id}-{datetime.now():%Y%m%d-%H%M%S}"
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True)
        outcome, reason = run_workflow(ticket, args.agent, run_id, run_dir)
    except (TicketError, WorkspaceError, CommandError, ScanReportError, AgentError) as error:
        outcome, reason = RunOutcome.FAILED, str(error)
    return finish(outcome, reason, run_dir)


if __name__ == "__main__":
    sys.exit(main())
