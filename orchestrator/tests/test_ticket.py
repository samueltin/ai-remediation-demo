import json
from pathlib import Path

import pytest

from ticket import TicketError, load_ticket

REPO_TICKETS = Path(__file__).resolve().parents[2] / "tickets"

VALID = {
    "ticket_id": "SEC-900",
    "title": "Upgrade example-lib",
    "severity": "HIGH",
    "cve_id": "CVE-2024-12345",
    "library": "org.example:example-lib",
    "current_version": "1.0",
    "target_version": "1.1",
    "service": "trade-intake",
    "description": "Example finding.",
    "acceptance_criteria": ["mvn test passes"],
}


def write_ticket(tmp_path, data):
    path = tmp_path / "ticket.json"
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize("name", ["SEC-101", "SEC-102", "SEC-103"])
def test_repo_tickets_are_valid(name):
    ticket = load_ticket(REPO_TICKETS / f"{name}.json")

    assert ticket.ticket_id == name


def test_valid_ticket_is_loaded(tmp_path):
    ticket = load_ticket(write_ticket(tmp_path, VALID))

    assert ticket.library == "org.example:example-lib"
    assert ticket.acceptance_criteria == ("mvn test passes",)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(TicketError, match="cannot read"):
        load_ticket(tmp_path / "missing.json")


def test_invalid_json_is_rejected(tmp_path):
    path = tmp_path / "ticket.json"
    path.write_text("{not json")

    with pytest.raises(TicketError, match="not valid JSON"):
        load_ticket(path)


def test_missing_field_is_rejected(tmp_path):
    data = dict(VALID)
    del data["cve_id"]

    with pytest.raises(TicketError, match="missing field: cve_id"):
        load_ticket(write_ticket(tmp_path, data))


def test_unknown_field_is_rejected(tmp_path):
    with pytest.raises(TicketError, match="unknown field: assignee"):
        load_ticket(write_ticket(tmp_path, {**VALID, "assignee": "someone"}))


@pytest.mark.parametrize("field, value", [
    ("ticket_id", "sec 900"),
    ("ticket_id", "../SEC-900"),
    ("cve_id", "CVE-24-1"),
    ("library", "example-lib"),
    ("service", "../orchestrator"),
    ("severity", "SEVERE"),
    ("current_version", ""),
    ("target_version", "1.1; rm -rf /"),
    ("title", "  "),
    ("title", 42),
    ("acceptance_criteria", []),
    ("acceptance_criteria", "mvn test passes"),
])
def test_bad_value_is_rejected(tmp_path, field, value):
    with pytest.raises(TicketError, match=field):
        load_ticket(write_ticket(tmp_path, {**VALID, field: value}))


def test_same_current_and_target_version_is_rejected(tmp_path):
    with pytest.raises(TicketError, match="target_version must differ"):
        load_ticket(write_ticket(tmp_path, {**VALID, "target_version": "1.0"}))


def test_all_problems_are_reported_together(tmp_path):
    data = {**VALID, "cve_id": "bad", "severity": "bad"}

    with pytest.raises(TicketError, match="severity(.|\n)*cve_id"):
        load_ticket(write_ticket(tmp_path, data))
