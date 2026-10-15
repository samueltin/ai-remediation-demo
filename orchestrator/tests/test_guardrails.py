from pathlib import Path

import pytest

from commands import run
from guardrails import (attempt_limit, check_all, diff_size, never_merged, no_test_changes,
                        only_existing_project_files, pom_only_ticket_version, same_test_count_as_baseline,
                        scan_clean, traceability, transcripts_saved)
from maven import BuildResult, SurefireCounts
from scanner import Finding, compare
from ticket import load_ticket
from workspace import commit_change, create_workspace, init_git

TICKET = load_ticket(Path(__file__).resolve().parents[2] / "tickets" / "SEC-102.json")

POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <dependencies>
        <dependency>
            <groupId>org.yaml</groupId>
            <artifactId>snakeyaml</artifactId>
            <version>1.33</version>
        </dependency>
        <dependency>
            <groupId>com.google.guava</groupId>
            <artifactId>guava</artifactId>
            <version>20.0</version>
        </dependency>
    </dependencies>
</project>
"""
UPGRADED = POM.replace("<version>1.33</version>", "<version>2.4</version>")


# Guardrail 1

def test_change_under_src_test_is_rejected():
    check = no_test_changes(["pom.xml", "src/test/java/com/example/tradeintake/TradeAuditLogTest.java"])

    assert check.number == 1
    assert not check.passed
    assert "TradeAuditLogTest.java" in check.reason


def test_changes_outside_src_test_pass():
    assert no_test_changes(["pom.xml", "src/main/java/com/example/A.java"]).passed


# Guardrail 2

def test_only_the_ticket_version_changed_passes():
    assert pom_only_ticket_version(TICKET, POM, UPGRADED).passed


def test_reformatting_alone_is_not_a_change():
    reformatted = UPGRADED.replace("    ", "  ")

    assert pom_only_ticket_version(TICKET, POM, reformatted).passed


@pytest.mark.parametrize("pom_after, expected", [
    (POM, "expected 2.4"),
    (POM.replace("<version>1.33</version>", "<version>2.3</version>"), "expected 2.4"),
    (UPGRADED.replace("<version>20.0</version>", "<version>33.7.2-jre</version>"), "more than the version"),
    (UPGRADED.replace("<modelVersion>4.0.0</modelVersion>",
                      "<modelVersion>4.0.0</modelVersion><properties>"
                      "<maven.test.skip>true</maven.test.skip></properties>"), "more than the version"),
    (UPGRADED.replace("</project>",
                      "<build><plugins><plugin><artifactId>maven-surefire-plugin</artifactId>"
                      "<configuration><excludes><exclude>**/TradeAuditLogTest.java</exclude></excludes>"
                      "</configuration></plugin></plugins></build></project>"), "more than the version"),
    (UPGRADED.replace("<artifactId>snakeyaml</artifactId>", "<artifactId>snakeyaml-engine</artifactId>"),
     "declared 0 times"),
    ("<project", "not valid XML"),
])
def test_any_other_pom_change_is_rejected(pom_after, expected):
    check = pom_only_ticket_version(TICKET, POM, pom_after)

    assert check.number == 2
    assert not check.passed
    assert expected in check.reason


# Guardrail 3

@pytest.mark.parametrize("count, last_passed, ok", [(1, True, True), (3, True, True), (3, False, False),
                                                   (4, True, False)])
def test_attempt_limit(count, last_passed, ok):
    assert attempt_limit(count, last_passed, max_attempts=3).passed is ok


# Guardrail 4

def test_small_diff_passes():
    check = diff_size("1\t1\tpom.xml\n2\t1\tsrc/main/A.java\n", limit=50)

    assert check.passed
    assert "5 changed lines" in check.reason


def test_large_diff_is_rejected():
    check = diff_size("40\t11\tsrc/main/A.java\n", limit=50)

    assert check.number == 4
    assert not check.passed
    assert "51 changed lines" in check.reason


def test_binary_change_is_rejected():
    assert not diff_size("-\t-\tlib/evil.jar\n", limit=50).passed


# Guardrail 6

def test_ticket_id_in_branch_and_commit_passes():
    assert traceability("SEC-102", "fix/SEC-102", "SEC-102: Upgrade snakeyaml").passed


@pytest.mark.parametrize("branch, subject", [("main", "SEC-102: x"), ("fix/SEC-102", "Upgrade snakeyaml")])
def test_missing_ticket_id_is_rejected(branch, subject):
    assert not traceability("SEC-102", branch, subject).passed


# Guardrail 7

def test_transcripts_must_exist_and_not_be_empty(tmp_path):
    full = tmp_path / "claude_attempt_1.jsonl"
    full.write_text('{"type": "result"}\n')
    empty = tmp_path / "claude_attempt_2.jsonl"
    empty.write_text("")

    assert transcripts_saved([full]).passed
    assert not transcripts_saved([full, empty]).passed
    assert not transcripts_saved([tmp_path / "missing.jsonl"]).passed


# Guardrail 8

def test_main_untouched_and_no_remote_passes():
    assert never_merged(main_sha="abc", baseline_sha="abc", remotes="").passed


@pytest.mark.parametrize("main_sha, remotes", [("def", ""), ("abc", "origin\n")])
def test_moved_main_or_a_remote_is_rejected(main_sha, remotes):
    assert not never_merged(main_sha=main_sha, baseline_sha="abc", remotes=remotes).passed


# Guardrail 9

BASELINE = SurefireCounts(run=15, failures=0, errors=0, skipped=0)


def test_same_test_count_passes():
    assert same_test_count_as_baseline(BASELINE, BASELINE, final_passed=True).passed


@pytest.mark.parametrize("final, final_passed", [
    (SurefireCounts(run=14, failures=0, errors=0, skipped=0), True),
    (SurefireCounts(run=15, failures=0, errors=0, skipped=1), True),
    (BASELINE, False),
])
def test_fewer_skipped_or_failing_tests_are_rejected(final, final_passed):
    check = same_test_count_as_baseline(BASELINE, final, final_passed)

    assert check.number == 9
    assert not check.passed


# All guardrails against a real git workspace

def test_check_all_reads_the_evidence_from_git(tmp_path):
    service = tmp_path / "repo" / "svc"
    (service / "src" / "test" / "java" / "com" / "example" / "tradeintake").mkdir(parents=True)
    (service / "pom.xml").write_text(POM)
    (service / "src" / "test" / "java" / "com" / "example" / "tradeintake" / "AuditTest.java").write_text("sameThreadExecutor();\n")
    workspace = create_workspace(service, tmp_path / "ws", tmp_path / "repo")
    init_git(workspace, TICKET.ticket_id)
    baseline_sha = run(["git", "rev-parse", "HEAD"], cwd=workspace).strip()

    (workspace / "pom.xml").write_text(UPGRADED)
    (workspace / "src" / "test" / "java" / "com" / "example" / "tradeintake" / "AuditTest.java").write_text("directExecutor();\n")
    commit_change(workspace, f"{TICKET.ticket_id}: {TICKET.title}")
    transcript = tmp_path / "claude_attempt_1.jsonl"
    transcript.write_text("{}\n")

    checks = check_all(TICKET, workspace, baseline_sha, BASELINE,
                       BuildResult(True, BASELINE, (), 1.0), attempt_count=1, max_attempts=3,
                       transcripts=[transcript], diff_limit=50,
                       comparison=compare({YAML_OLD}, set(), TICKET.cve_id, TICKET.library))

    assert {c.number: c.passed for c in checks} == {1: False, 2: True, 3: True, 4: True, 5: True, 6: True, 7: True,
                                                     8: True, 9: True, 10: True}
    assert "src/test/java/com/example/tradeintake/AuditTest.java" in checks[0].reason


# Guardrail 10

def test_shadow_class_of_a_library_is_rejected():
    # SEC-103: the agent considered copying Guava's MoreExecutors into src/main with the old method
    # added back. Guardrails 1, 2, 4 and 9 would all have passed.
    name_status = ("M\tpom.xml\n"
                   "A\tsrc/main/java/com/google/common/util/concurrent/MoreExecutors.java\n")

    check = only_existing_project_files(name_status)

    assert check.number == 10
    assert not check.passed
    assert "added: src/main/java/com/google/common/util/concurrent/MoreExecutors.java" in check.reason


def test_modified_files_in_the_project_package_pass():
    name_status = ("M\tpom.xml\n"
                   "M\tsrc/main/java/com/example/tradeintake/ReferenceDataConfig.java\n")

    assert only_existing_project_files(name_status).passed


@pytest.mark.parametrize("name_status, expected", [
    ("D\tsrc/main/java/com/example/tradeintake/TradeSummary.java\n", "deleted"),
    ("A\tdocs/notes.md\n", "added"),
    ("M\tsrc/main/java/org/other/Helper.java\n", "outside com.example.tradeintake"),
])
def test_added_deleted_or_foreign_files_are_rejected(name_status, expected):
    check = only_existing_project_files(name_status)

    assert not check.passed
    assert expected in check.reason


# Guardrail 5

YAML_OLD = Finding("CVE-2022-1471", "org.yaml:snakeyaml", "1.33")
TOMCAT = Finding("CVE-2026-65182", "org.apache.tomcat.embed:tomcat-embed-core", "10.1.55")


def test_ticket_finding_gone_and_nothing_new_passes():
    comparison = compare({YAML_OLD, TOMCAT}, {TOMCAT}, TICKET.cve_id, TICKET.library)

    check = scan_clean(TICKET, comparison)

    assert check.number == 5
    assert check.passed
    assert "no new findings" in check.reason


def test_ticket_finding_still_present_fails():
    still = Finding("CVE-2022-1471", "org.yaml:snakeyaml", "1.34")

    check = scan_clean(TICKET, compare({YAML_OLD, TOMCAT}, {still, TOMCAT}, TICKET.cve_id, TICKET.library))

    assert not check.passed
    assert "still reports CVE-2022-1471" in check.reason


def test_new_finding_fails_even_when_the_ticket_finding_is_gone():
    new = Finding("CVE-2099-0001", "org.yaml:snakeyaml", "2.4")

    check = scan_clean(TICKET, compare({YAML_OLD, TOMCAT}, {TOMCAT, new}, TICKET.cve_id, TICKET.library))

    assert not check.passed
    assert "CVE-2099-0001 in org.yaml:snakeyaml 2.4" in check.reason
