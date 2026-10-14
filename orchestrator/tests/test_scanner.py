import json

import pytest

from scanner import Finding, ScanReportError, compare, findings_for, load_findings


def vuln(cve, package, version):
    return {"VulnerabilityID": cve, "PkgName": package, "InstalledVersion": version, "Severity": "HIGH"}


def write_report(tmp_path, results, schema_version=2):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"SchemaVersion": schema_version, "Results": results}))
    return path


YAML_OLD = Finding("CVE-2022-1471", "org.yaml:snakeyaml", "1.33")
TOMCAT = Finding("CVE-2026-65182", "org.apache.tomcat.embed:tomcat-embed-core", "10.1.55")


def test_findings_are_loaded_as_cve_package_version(tmp_path):
    path = write_report(tmp_path, [{"Target": "pom.xml", "Vulnerabilities": [
        vuln("CVE-2022-1471", "org.yaml:snakeyaml", "1.33"),
        vuln("CVE-2026-65182", "org.apache.tomcat.embed:tomcat-embed-core", "10.1.55"),
    ]}])

    assert load_findings(path) == {YAML_OLD, TOMCAT}


def test_results_without_vulnerabilities_give_no_findings(tmp_path):
    path = write_report(tmp_path, [{"Target": "pom.xml", "Vulnerabilities": None}, {"Target": "other"}])

    assert load_findings(path) == set()


def test_report_without_results_is_rejected(tmp_path):
    # An empty scan is not a clean scan: Trivy may simply not have found pom.xml.
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"SchemaVersion": 2}))

    with pytest.raises(ScanReportError, match="no scan results"):
        load_findings(path)


def test_report_with_unexpected_schema_is_rejected(tmp_path):
    with pytest.raises(ScanReportError, match="SchemaVersion"):
        load_findings(write_report(tmp_path, [], schema_version=1))


def test_unreadable_report_is_rejected(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text("not json")

    with pytest.raises(ScanReportError, match="not valid JSON"):
        load_findings(path)


def test_findings_for_matches_cve_and_library():
    other_library_same_cve = Finding("CVE-2022-1471", "org.example:other", "1.0")

    assert findings_for({YAML_OLD, TOMCAT, other_library_same_cve},
                        "CVE-2022-1471", "org.yaml:snakeyaml") == {YAML_OLD}


def test_ticket_finding_gone_and_nothing_new():
    result = compare(before={YAML_OLD, TOMCAT}, after={TOMCAT},
                     cve_id="CVE-2022-1471", library="org.yaml:snakeyaml")

    assert result.ticket_finding_gone
    assert result.new_findings == set()
    assert result.resolved == {YAML_OLD}


def test_new_finding_is_detected_even_when_count_is_unchanged():
    new_problem = Finding("CVE-2099-0001", "org.yaml:snakeyaml", "2.4")

    result = compare(before={YAML_OLD, TOMCAT}, after={TOMCAT, new_problem},
                     cve_id="CVE-2022-1471", library="org.yaml:snakeyaml")

    assert result.ticket_finding_gone
    assert result.new_findings == {new_problem}


def test_ticket_finding_at_another_version_is_not_gone():
    still_vulnerable = Finding("CVE-2022-1471", "org.yaml:snakeyaml", "1.34")

    result = compare(before={YAML_OLD}, after={still_vulnerable},
                     cve_id="CVE-2022-1471", library="org.yaml:snakeyaml")

    assert not result.ticket_finding_gone
