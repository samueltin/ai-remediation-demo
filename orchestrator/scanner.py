"""Runs Trivy and compares findings.

Findings are compared as sets of (CVE ID, package, installed version), never by count:
the baseline has out of scope findings, and a fix that removes one finding but adds
another would leave the count unchanged.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from commands import run

# The first run downloads the vulnerability database.
TRIVY_TIMEOUT_SECONDS = 900


class ScanReportError(RuntimeError):
    pass


class Finding(NamedTuple):
    cve_id: str
    package: str
    installed_version: str


@dataclass(frozen=True)
class ScanComparison:
    ticket_finding_gone: bool
    new_findings: set[Finding]
    resolved: set[Finding]


def scan(target: Path, report_path: Path) -> set[Finding]:
    run(["trivy", "fs", "--scanners", "vuln", "--format", "json", "--quiet",
         "--output", str(report_path), str(target)],
        cwd=target, timeout=TRIVY_TIMEOUT_SECONDS)
    return load_findings(report_path)


def load_findings(report_path: Path) -> set[Finding]:
    try:
        report = json.loads(Path(report_path).read_text())
    except json.JSONDecodeError as error:
        raise ScanReportError(f"{report_path}: not valid JSON ({error})") from error
    if not isinstance(report, dict) or report.get("SchemaVersion") != 2:
        raise ScanReportError(f"{report_path}: expected a Trivy report with SchemaVersion 2")
    if not report.get("Results"):
        raise ScanReportError(f"{report_path}: no scan results, so Trivy found nothing to scan")
    return {
        Finding(vuln["VulnerabilityID"], vuln["PkgName"], vuln["InstalledVersion"])
        for result in report["Results"]
        for vuln in result.get("Vulnerabilities") or []
    }


def findings_for(findings: set[Finding], cve_id: str, library: str) -> set[Finding]:
    """The findings for one CVE in one library, at any installed version."""
    return {f for f in findings if f.cve_id == cve_id and f.package == library}


def compare(before: set[Finding], after: set[Finding], cve_id: str, library: str) -> ScanComparison:
    return ScanComparison(
        ticket_finding_gone=not findings_for(after, cve_id, library),
        new_findings=after - before,
        resolved=before - after,
    )
