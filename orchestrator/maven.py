"""Runs the Maven build for the orchestrator itself, independent of what the agent reports."""

import re
import shutil
import time
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

from commands import run, run_unchecked

REQUIRED_JAVA_MAJOR = "17"
MAVEN_TIMEOUT_SECONDS = 900
MAX_ERROR_LINES = 60
TAIL_LINES = 40

# demo-shortcut: mvn test runs the agent's changed code directly on this machine.
# Production: build in the same isolated container or CI runner as the agent.


class BuildEnvironmentError(RuntimeError):
    pass


class VersionBumpError(ValueError):
    pass


# Maven's standard advice after any failure; it says nothing about this failure.
_MAVEN_HELP_TEXT = re.compile(r"\[Help \d+\]|re-run Maven|Re-run Maven|For more information about the errors")
_DEPENDENCY = re.compile(r"<dependency>.*?</dependency>", re.DOTALL)
_VERSION = re.compile(r"<version>([^<]*)</version>")


def bump_version(pom_text: str, library: str, current_version: str, target_version: str) -> str:
    """The plain version change the ticket asks for, as a text edit that keeps all other formatting."""
    group_id, artifact_id = library.split(":")
    blocks = [block for block in _DEPENDENCY.finditer(pom_text)
              if re.search(rf"<groupId>\s*{re.escape(group_id)}\s*</groupId>", block.group())
              and re.search(rf"<artifactId>\s*{re.escape(artifact_id)}\s*</artifactId>", block.group())]
    if len(blocks) != 1:
        raise VersionBumpError(f"{library} is declared {len(blocks)} times in pom.xml, expected once")
    block = blocks[0]
    version = _VERSION.search(block.group())
    found = version.group(1).strip() if version else "no version"
    if found != current_version:
        raise VersionBumpError(f"{library} is at {found} in pom.xml, not {current_version}")
    start = block.start() + version.start(1) + version.group(1).index(found)
    return pom_text[:start] + target_version + pom_text[start + len(found):]


@dataclass(frozen=True)
class SurefireCounts:
    run: int
    failures: int
    errors: int
    skipped: int


@dataclass(frozen=True)
class BuildResult:
    passed: bool
    counts: SurefireCounts
    error_lines: tuple[str, ...]
    duration_seconds: float


def check_java_version(cwd: Path) -> str:
    """Fails fast unless Maven runs on JDK 17, the version the target team uses."""
    version = java_version(run(["mvn", "-v"], cwd=cwd))
    if version.split(".")[0] != REQUIRED_JAVA_MAJOR:
        raise BuildEnvironmentError(
            f"Maven runs on Java {version}, but the service targets Java {REQUIRED_JAVA_MAJOR}. "
            f"Set JAVA_HOME to a JDK {REQUIRED_JAVA_MAJOR}.")
    return version


def java_version(mvn_version_output: str) -> str:
    match = re.search(r"^Java version: ([^,\s]+)", mvn_version_output, re.MULTILINE)
    if match is None:
        raise BuildEnvironmentError("cannot find the Java version in the output of mvn -v")
    return match.group(1)


def run_tests(workspace: Path, log_path: Path) -> BuildResult:
    started = time.monotonic()
    # clean first, so Surefire reports from an earlier run are never counted.
    result = run_unchecked(["mvn", "-B", "clean", "test"], cwd=workspace, timeout=MAVEN_TIMEOUT_SECONDS)
    duration = round(time.monotonic() - started, 1)
    log_path.write_text(result.stdout + result.stderr)

    counts = read_surefire_reports(workspace / "target" / "surefire-reports")
    # Stale classes left in target/ made the agent's own incremental build hide a compile error
    # behind runtime NoSuchMethodErrors, so the agent always starts without build output.
    if (workspace / "target").exists():
        shutil.rmtree(workspace / "target")
    # Green needs both: Maven succeeded and the reports show no failures, because a build
    # setting such as testFailureIgnore could make Maven succeed with failing tests.
    passed = result.returncode == 0 and counts.failures == 0 and counts.errors == 0
    return BuildResult(passed, counts, () if passed else error_lines(result.stdout), duration)


def read_surefire_reports(folder: Path) -> SurefireCounts:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for report in sorted(folder.glob("TEST-*.xml")):
        suite = ElementTree.parse(report).getroot()
        for name in totals:
            totals[name] += int(suite.attrib[name])
    return SurefireCounts(totals["tests"], totals["failures"], totals["errors"], totals["skipped"])


def error_lines(output: str) -> tuple[str, ...]:
    """The [ERROR] lines of a Maven run, once each and in order, to feed back to the agent."""
    lines = output.splitlines()
    errors = [line for line in lines if line.startswith("[ERROR]") and line[len("[ERROR]"):].strip()
              and not _MAVEN_HELP_TEXT.search(line)]
    if not errors:
        return tuple(lines[-TAIL_LINES:])
    return tuple(dict.fromkeys(errors))[:MAX_ERROR_LINES]


def describe(counts: SurefireCounts) -> str:
    return (f"{counts.run} run, {counts.failures} failed, "
            f"{counts.errors} errors, {counts.skipped} skipped")
