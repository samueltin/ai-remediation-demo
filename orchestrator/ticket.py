"""Loads and validates a security ticket.

Ticket values end up in file paths, git branch names and the agent prompt,
so every field is checked against a strict pattern before anything else runs.
"""

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path

# demo-shortcut: tickets are read from JSON files. Production: issue tracker API or MCP server.

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
_VERSION = r"[A-Za-z0-9][A-Za-z0-9._+-]*"
PATTERNS = {
    # Only security tickets: the workflow must not be pointed at arbitrary work items.
    "ticket_id": r"SEC-[0-9]+",
    "severity": "|".join(SEVERITIES),
    "cve_id": r"CVE-[0-9]{4}-[0-9]{4,}",
    "library": r"[A-Za-z0-9._-]+:[A-Za-z0-9._-]+",
    "current_version": _VERSION,
    "target_version": _VERSION,
    "service": r"[a-z0-9][a-z0-9-]*",
}
FREE_TEXT = ("title", "description")


class TicketError(ValueError):
    pass


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    title: str
    severity: str
    cve_id: str
    library: str
    current_version: str
    target_version: str
    service: str
    description: str
    acceptance_criteria: tuple[str, ...]


FIELDS = tuple(field.name for field in fields(Ticket))


def load_ticket(path: Path) -> Ticket:
    try:
        text = Path(path).read_text()
    except OSError as error:
        raise TicketError(f"{path}: cannot read ticket ({error.strerror})") from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise TicketError(f"{path}: not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise TicketError(f"{path}: expected a JSON object")

    problems = _problems(data)
    if problems:
        raise TicketError(f"{path}: invalid ticket:\n  " + "\n  ".join(problems))
    return Ticket(**{**data, "acceptance_criteria": tuple(data["acceptance_criteria"])})


def _problems(data: dict) -> list[str]:
    problems = [f"unknown field: {name}" for name in data if name not in FIELDS]
    for name in FIELDS:
        if name not in data:
            problems.append(f"missing field: {name}")
            continue
        value = data[name]
        if name in PATTERNS:
            if not (isinstance(value, str) and re.fullmatch(PATTERNS[name], value)):
                problems.append(f"{name} has an invalid value: {value!r}")
        elif name in FREE_TEXT:
            if not (isinstance(value, str) and value.strip()):
                problems.append(f"{name} must be a non-empty string")
        elif name == "acceptance_criteria":
            if not (isinstance(value, list) and value
                    and all(isinstance(item, str) and item.strip() for item in value)):
                problems.append("acceptance_criteria must be a non-empty list of strings")
    if "current_version" in data and data.get("current_version") == data.get("target_version"):
        problems.append("target_version must differ from current_version")
    return problems
