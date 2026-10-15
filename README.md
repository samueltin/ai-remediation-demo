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

## Deterministic first, AI second

Before any agent is called, the workflow applies the plain version bump itself and runs the
build and tests. If they pass (SEC-101), no agent is used. If they fail (SEC-102), the error is
kept as evidence that a code change is needed, and the agent starts from it. Use
`--always-agent` to call the agent anyway. Example summaries are in `docs/examples/`.

## Safety model

Two layers, and neither trusts the agent's own report:

- **Permissions limit what the agent can do.** It runs in a copy of the service outside this
  repository, may only edit files there and run `mvn`, and has no network or git access
  through its tools.
- **Guardrails verify what it actually changed.** After the agent finishes, the workflow
  runs the tests itself, inspects the git diff, compares the test count with the baseline
  and scans again. Any failure stops the run for a human.

Ticket text is untrusted input. Structured fields are validated strictly, and free text is
passed to the agent inside a delimited data section that it is told to treat as data only.

## Guardrails

Checked by the workflow after the agent finishes, on the committed change. Any failure ends
the run as `NEEDS_HUMAN_ATTENTION` with the reason.

| # | Guardrail | Risk it controls |
|---|---|---|
| 1 | No changes under `src/test/` | Agent passes by weakening tests |
| 2 | The only change to pom.xml is the ticket library's version | Hallucinated or malicious packages; tests skipped through build config |
| 3 | Tests green within 3 agent attempts; the loop stops early when an attempt adds nothing | Endless loops and runaway cost |
| 4 | At most 50 changed lines (configurable) | Unexpectedly wide changes |
| 5 | Scan before and after: the ticket's finding is gone and no finding is new | Fix that does not really fix |
| 6 | Ticket ID in branch name, commit message and summary | Lost traceability |
| 7 | Agent transcript saved for every attempt | No audit trail |
| 8 | Nothing merged or pushed: main is still the baseline, no remote | Bypassing human approval |
| 9 | Same number of tests as the baseline, none skipped | Green build because tests were disabled |
| 10 | Only existing files modified; Java changes only in the project's own package | Shadow copies of library classes |

To see guardrail 1 fire, run SEC-103 with `--agent unsafe-sim`. **This is a simulation, not a
real agent:** a short script that does what a careless agent might do (upgrade Guava, then edit
the failing test so it compiles). The build goes green with all 15 tests, and only guardrail 1
stops it.

## Setup

```
cd orchestrator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
```
