import os
import stat
import sys
from pathlib import Path

import pytest

from guardrails import pom_only_ticket_version
from maven import (BuildEnvironmentError, SurefireCounts, VersionBumpError, bump_version, error_lines, java_version,
                   read_surefire_reports, run_tests)
from ticket import load_ticket

FAKE_MVN = """#!{python}
import pathlib, sys
reports = pathlib.Path("target/surefire-reports")
reports.mkdir(parents=True, exist_ok=True)
(reports / "TEST-Fake.xml").write_text(
    '<testsuite tests="15" failures="{failures}" errors="0" skipped="0"/>')
print("[INFO] fake build")
sys.exit({exit_code})
"""


@pytest.fixture
def fake_mvn(tmp_path, monkeypatch):
    def install(failures=0, exit_code=0):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        mvn = bin_dir / "mvn"
        mvn.write_text(FAKE_MVN.format(python=sys.executable, failures=failures, exit_code=exit_code))
        mvn.chmod(mvn.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        workspace = tmp_path / "ws"
        workspace.mkdir()
        return workspace
    return install


def test_green_build_is_counted_and_leaves_no_build_output(fake_mvn, tmp_path):
    # Stale classes in target/ once hid a compile error from the agent, so every build cleans up.
    workspace = fake_mvn()

    result = run_tests(workspace, tmp_path / "mvn.log")

    assert result.passed
    assert result.counts == SurefireCounts(run=15, failures=0, errors=0, skipped=0)
    assert not (workspace / "target").exists()
    assert "fake build" in (tmp_path / "mvn.log").read_text()


def test_failures_in_reports_are_not_green_even_when_maven_succeeds(fake_mvn, tmp_path):
    workspace = fake_mvn(failures=2, exit_code=0)

    assert not run_tests(workspace, tmp_path / "mvn.log").passed

MVN_V_17 = """Apache Maven 3.9.9 (8e8579a9e76f7d015ee5ec7bfcdc97d260186937)
Maven home: /opt/apache-maven
Java version: 17.0.20.1, vendor: Eclipse Adoptium, runtime: /Library/Java/temurin-17.jdk/Contents/Home
"""


def write_suite(folder, name, tests, failures=0, errors=0, skipped=0):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"TEST-{name}.xml").write_text(
        f'<?xml version="1.0"?><testsuite name="{name}" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"><testcase name="a"/></testsuite>')


def test_java_version_is_read_from_mvn_output():
    assert java_version(MVN_V_17) == "17.0.20.1"


def test_missing_java_version_raises():
    with pytest.raises(BuildEnvironmentError, match="Java version"):
        java_version("Apache Maven 3.9.9")


def test_surefire_counts_are_summed_over_all_suites(tmp_path):
    reports = tmp_path / "surefire-reports"
    write_suite(reports, "ValidatorTest", tests=10)
    write_suite(reports, "ControllerTest", tests=3, failures=1, skipped=1)
    (reports / "ValidatorTest.txt").write_text("not a report")

    assert read_surefire_reports(reports) == SurefireCounts(run=13, failures=1, errors=0, skipped=1)


def test_no_reports_means_no_tests_ran(tmp_path):
    assert read_surefire_reports(tmp_path / "missing") == SurefireCounts(run=0, failures=0, errors=0, skipped=0)


def test_error_lines_are_kept_once_in_order():
    output = "\n".join([
        "[INFO] Compiling 9 source files",
        "[ERROR] /ws/src/main/A.java:[20,59] incompatible types",
        "[ERROR] ",
        "[INFO] BUILD FAILURE",
        "[ERROR] /ws/src/main/A.java:[20,59] incompatible types",
        "[ERROR] Failed to execute goal compile",
    ])

    assert error_lines(output) == (
        "[ERROR] /ws/src/main/A.java:[20,59] incompatible types",
        "[ERROR] Failed to execute goal compile",
    )


def test_output_without_error_lines_falls_back_to_the_tail():
    output = "\n".join(f"line {n}" for n in range(100))

    assert error_lines(output)[-1] == "line 99"
    assert len(error_lines(output)) == 40


# The deterministic version bump

POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
    <dependencies>
        <dependency>
            <groupId>org.yaml</groupId>
            <artifactId>snakeyaml</artifactId>
            <version>1.33</version>
        </dependency>
        <dependency>
            <groupId>com.google.guava</groupId>
            <artifactId>guava</artifactId>
            <version>1.33</version>
        </dependency>
    </dependencies>
</project>
"""


def test_bump_changes_only_the_ticket_library_version():
    bumped = bump_version(POM, "org.yaml:snakeyaml", "1.33", "2.4")

    changed = [(old, new) for old, new in zip(POM.splitlines(), bumped.splitlines()) if old != new]
    assert changed == [("            <version>1.33</version>", "            <version>2.4</version>")]


def test_bumped_pom_passes_guardrail_2():
    ticket = load_ticket(Path(__file__).resolve().parents[2] / "tickets" / "SEC-102.json")

    bumped = bump_version(POM, ticket.library, ticket.current_version, ticket.target_version)

    assert pom_only_ticket_version(ticket, POM, bumped).passed


@pytest.mark.parametrize("library, current, expected", [
    ("org.example:missing", "1.0", "declared 0 times"),
    ("org.yaml:snakeyaml", "1.30", "not 1.30"),
])
def test_bump_that_cannot_be_applied_raises(library, current, expected):
    with pytest.raises(VersionBumpError, match=expected):
        bump_version(POM, library, current, "9.9")


def test_bump_refuses_a_library_declared_twice():
    twice = POM.replace("<groupId>com.google.guava</groupId>", "<groupId>org.yaml</groupId>").replace(
        "<artifactId>guava</artifactId>", "<artifactId>snakeyaml</artifactId>")

    with pytest.raises(VersionBumpError, match="declared 2 times"):
        bump_version(twice, "org.yaml:snakeyaml", "1.33", "2.4")


def test_maven_help_text_is_not_an_error_line():
    output = "\n".join([
        "[ERROR] /ws/src/main/A.java:[20,59] incompatible types",
        "[ERROR] -> [Help 1]",
        "[ERROR] To see the full stack trace of the errors, re-run Maven with the -e switch.",
        "[ERROR] Re-run Maven using the -X switch to enable full debug logging.",
        "[ERROR] For more information about the errors and possible solutions, please read the following articles:",
        "[ERROR] [Help 1] http://cwiki.apache.org/confluence/display/MAVEN/MojoFailureException",
    ])

    assert error_lines(output) == ("[ERROR] /ws/src/main/A.java:[20,59] incompatible types",)
