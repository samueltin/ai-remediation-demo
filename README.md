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

## Tickets and the vulnerable baseline

`trade-intake/` deliberately stays on vulnerable library versions so the demo can be
re-run. Each ticket targets one finding:

| Ticket | Library | CVE | What the fix needs |
|---|---|---|---|
| SEC-101 | commons-text 1.9 to 1.10.0 | CVE-2022-42889 | Version change only |
| SEC-102 | snakeyaml 1.33 to 2.4 | CVE-2022-1471 | Version change plus a code change in `src/main` (API changed in 2.0) |
| SEC-103 | guava 20.0 to 33.7.2-jre | CVE-2023-2976 | Version change plus a change to a test file, which the guardrails forbid, so the run must stop for a human |

The baseline also contains other findings that are out of scope for each ticket. They
come from libraries managed by Spring Boot 3.5.16 (for example Tomcat, Spring MVC and
Jackson); some have no fix within Spring Boot 3. This is intentional: real scans are noisy
and each ticket targets one finding. The workflow therefore compares scans before and
after as sets of (CVE ID, package, installed version): the ticket's finding must be gone
and no finding may be new. It never compares counts.

## Setup

```
cd orchestrator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
```
