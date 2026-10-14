# AI-Assisted Cyber Remediation Demo

A demo of how a Java team in a regulated firm could use an AI coding agent to fix a
security finding safely: scan, fix, test, verify, apply guardrails, and hand a merge
request summary to a human. The workflow never merges.

## Projects

- `trade-intake/`: Spring Boot 3 / Java 17 / Maven service. The target app, with a
  deliberately vulnerable dependency.
- `orchestrator/`: Python workflow that runs the agent in an isolated workspace and
  enforces the guardrails.
- `tickets/`: JSON files that mock security tickets from an issue tracker.
- `docs/`: diagrams and agent comparison.
- `runs/`: output of each run (not committed).

## Setup

```
cd orchestrator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
```
