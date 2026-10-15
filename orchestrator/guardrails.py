"""Guardrails: automated checks on what the agent actually changed, run before any handover.

Each check is a plain function over evidence (file lists, pom.xml text, test counts), so it can
be tested without git or Maven. check_all gathers that evidence from the workspace's git history.
Guardrail 5 (scan before and after) is checked separately, after the after scan.
"""

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

from commands import run
from maven import BuildResult, SurefireCounts, describe
from ticket import Ticket

POM_NAMESPACE = "{http://maven.apache.org/POM/4.0.0}"
DEFAULT_DIFF_LIMIT = 50


@dataclass(frozen=True)
class Check:
    number: int
    name: str
    passed: bool
    reason: str


def no_test_changes(changed_files: list[str]) -> Check:
    name = "No changes under src/test/"
    touched = [path for path in changed_files if path.startswith("src/test/")]
    if touched:
        return Check(1, name, False, f"changed test files: {', '.join(touched)}")
    return Check(1, name, True, "no test files changed")


def pom_only_ticket_version(ticket: Ticket, pom_before: str, pom_after: str) -> Check:
    name = "Only the ticket's library version changed in pom.xml"
    try:
        before = ElementTree.fromstring(pom_before)
        after = ElementTree.fromstring(pom_after)
    except ElementTree.ParseError as error:
        return Check(2, name, False, f"pom.xml is not valid XML ({error})")

    declarations = _dependencies(after, ticket.library)
    if len(declarations) != 1:
        return Check(2, name, False,
                     f"{ticket.library} is declared {len(declarations)} times in pom.xml, expected once")
    version = declarations[0].find(f"{POM_NAMESPACE}version")
    found = (version.text or "").strip() if version is not None else "no version"
    if found != ticket.target_version:
        return Check(2, name, False, f"pom.xml sets {ticket.library} to {found}, expected {ticket.target_version}")

    # Put the old version back: everything else must then be identical, so any added
    # dependency, plugin, property or test exclusion is caught. Formatting is ignored.
    version.text = ticket.current_version
    if _canonical(before) != _canonical(after):
        return Check(2, name, False, f"pom.xml changes more than the version of {ticket.library}")
    return Check(2, name, True, f"{ticket.library} {ticket.current_version} -> {ticket.target_version}, "
                                "nothing else")


def attempt_limit(attempt_count: int, last_passed: bool, max_attempts: int) -> Check:
    name = f"Tests green within {max_attempts} agent attempts"
    if attempt_count > max_attempts:
        return Check(3, name, False, f"{attempt_count} attempts exceed the limit of {max_attempts}")
    if not last_passed:
        return Check(3, name, False, f"mvn test still fails after {attempt_count} attempt(s)")
    return Check(3, name, True, f"green after {attempt_count} attempt(s)")


def diff_size(numstat: str, limit: int) -> Check:
    name = f"Diff size within {limit} changed lines"
    total = 0
    for line in numstat.splitlines():
        added, removed, path = line.split("\t", 2)
        if added == "-":
            return Check(4, name, False, f"binary file changed: {path}")
        total += int(added) + int(removed)
    return Check(4, name, total <= limit, f"{total} changed lines (limit {limit})")


def traceability(ticket_id: str, branch: str, head_subject: str) -> Check:
    name = "Ticket ID in branch name and commit message"
    if branch != f"fix/{ticket_id}":
        return Check(6, name, False, f"branch is {branch}, expected fix/{ticket_id}")
    if not head_subject.startswith(f"{ticket_id}: "):
        return Check(6, name, False, f"commit message '{head_subject}' does not start with {ticket_id}")
    return Check(6, name, True, f"branch {branch}, commit '{head_subject}'")


def transcripts_saved(transcripts: list[Path]) -> Check:
    name = "Agent transcript saved for every attempt"
    missing = [path.name for path in transcripts if not path.is_file() or path.stat().st_size == 0]
    if missing:
        return Check(7, name, False, f"missing or empty: {', '.join(missing)}")
    return Check(7, name, True, f"{len(transcripts)} transcript(s) saved")


def never_merged(main_sha: str, baseline_sha: str, remotes: str) -> Check:
    name = "Nothing merged or pushed"
    if main_sha != baseline_sha:
        return Check(8, name, False, "main no longer points at the baseline commit")
    if remotes.strip():
        return Check(8, name, False, f"workspace has a git remote: {remotes.strip()}")
    return Check(8, name, True, "main is still the baseline and there is no remote")


def same_test_count_as_baseline(baseline: SurefireCounts, final: SurefireCounts, final_passed: bool) -> Check:
    name = "Same number of tests as the baseline, none skipped"
    if not final_passed:
        return Check(9, name, False, f"final mvn test is not green ({describe(final)})")
    if final.run != baseline.run or final.skipped:
        return Check(9, name, False, f"{describe(final)}; baseline had {describe(baseline)}")
    return Check(9, name, True, f"{final.run} run, same as the baseline, 0 skipped")


def check_all(ticket: Ticket, workspace: Path, baseline_sha: str, baseline: SurefireCounts,
              final_build: BuildResult, attempt_count: int, max_attempts: int,
              transcripts: list[Path], diff_limit: int) -> list[Check]:
    def git(*args: str) -> str:
        return run(["git", *args], cwd=workspace)

    changed_files = git("diff", "--name-only", "--no-renames", "main", "HEAD").split()
    return [
        no_test_changes(changed_files),
        pom_only_ticket_version(ticket, git("show", "main:pom.xml"), git("show", "HEAD:pom.xml")),
        attempt_limit(attempt_count, final_build.passed, max_attempts),
        diff_size(git("diff", "--numstat", "--no-renames", "main", "HEAD"), diff_limit),
        traceability(ticket.ticket_id, git("rev-parse", "--abbrev-ref", "HEAD").strip(),
                     git("log", "-1", "--format=%s").strip()),
        transcripts_saved(transcripts),
        never_merged(git("rev-parse", "main").strip(), baseline_sha, git("remote")),
        same_test_count_as_baseline(baseline, final_build.counts, final_build.passed),
    ]


def _dependencies(pom: ElementTree.Element, library: str) -> list[ElementTree.Element]:
    group_id, artifact_id = library.split(":")
    return [dependency for dependency in pom.iter(f"{POM_NAMESPACE}dependency")
            if dependency.findtext(f"{POM_NAMESPACE}groupId") == group_id
            and dependency.findtext(f"{POM_NAMESPACE}artifactId") == artifact_id]


def _canonical(pom: ElementTree.Element) -> str:
    return ElementTree.canonicalize(ElementTree.tostring(pom, encoding="unicode"), strip_text=True)
