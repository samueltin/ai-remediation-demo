# AI-Assisted Cyber Remediation Demo

How a Java team in a regulated firm could let an AI coding agent fix security findings,
with the controls such a firm would expect: isolation, independent verification, guardrails,
a full audit trail and a human who approves every change. The workflow never merges.

The coding agent is replaceable (Claude Code or GitHub Copilot CLI). The value is the
controlled workflow around it.

## The problem

Dependency scanners report a steady stream of vulnerable libraries in Java services. Most
fixes look small (raise a version number), but each one still needs a developer to make the
change, fix whatever the new version breaks, run the tests and push it through a multi-stage
release process (for example DEV, test, UAT, production). Findings pile up faster than teams
clear them, and regulators expect both timely remediation and evidence of how each change was made.

An AI agent can do much of the mechanical work, but a regulated firm cannot let an agent change
code on trust. It needs to know what the agent could touch, what it actually changed, that the
fix really fixes the finding, and that a human approved it.

## What the demo does

1. Reads a mock security ticket and confirms the finding with a Trivy scan.
2. Tries the plain version bump itself, and calls an AI agent only if that breaks the build.
3. Runs the agent in an isolated copy of the service, allowed only to edit files and run Maven.
4. Verifies the result itself: clean build, same test count, scan before and after, ten guardrails.
5. Writes a merge request summary for a human reviewer. It never merges.

## Flow

```mermaid
flowchart TD
    A[Load ticket] --> B[Check toolchain]
    B --> C[Prepare workspace]
    C --> D[Scan before]
    D --> E[Baseline tests]
    E --> F[Try version bump]
    F -->|bump alone breaks the build| G[Agent attempts]
    F -->|bump alone passes| H[Commit change]
    G --> H
    H --> I[Scan after]
    I --> J[Check guardrails]
    J --> K[Write summary]
    K --> L[Human review]
    B -.->|wrong JDK| S[Stop early: FAILED or NEEDS_HUMAN_ATTENTION]
    D -.->|finding not found| S
    E -.->|baseline not green| S
    G -.->|agent changed nothing| S
```

| Stage | What happens |
|---|---|
| Load ticket | Reads the ticket JSON and validates every field strictly (ticket text is untrusted input). |
| Check toolchain | Stops unless Maven runs on JDK 17, the version the service targets. |
| Prepare workspace | Copies the service outside this repository (without `target/`), commits it as the baseline and creates `fix/<ticket-id>`. |
| Scan before | Runs Trivy and confirms the ticket's CVE is present at the ticket's version. |
| Baseline tests | Runs `mvn clean test` on the untouched code. The test count is the baseline for guardrail 9. |
| Try version bump | Applies only the version change and runs the clean build and tests. If they pass, no agent is needed. If they fail, the error is kept as evidence. |
| Agent attempts | Resets the workspace and calls the agent with the error, up to 3 attempts. After each attempt the workflow runs the tests itself and feeds back the errors. |
| Commit change | Commits the final state on the fix branch, even when red, so the reviewer sees exactly what was checked. |
| Scan after | Scans again and compares findings as sets of (CVE ID, package, installed version). |
| Check guardrails | Runs the ten guardrails below. Any failure means NEEDS_HUMAN_ATTENTION. |
| Write summary | Writes `MR_SUMMARY.md` with the outcome, diff, evidence and audit trail. |
| Human review | Outside the workflow: a person reads the summary and approves or rejects the merge request. |

Each run ends in exactly one outcome, which is also the exit code: `READY_FOR_REVIEW` (0),
`FAILED` (1) or `NEEDS_HUMAN_ATTENTION` (2).

## Deterministic first, AI second

The cheapest, most predictable change is the one no model made. If the plain version bump
builds and passes the tests (SEC-101), no agent is called, and the same guardrails still apply.
If it breaks the build (SEC-102), the error goes into the summary as evidence that a code change
was needed, and the agent starts from it. `--always-agent` calls the agent anyway.

## Safety model

Two layers, and neither trusts the agent's own report:

- **Permissions limit what the agent can do.** It runs in a copy of the service outside this
  repository, may only edit files there and run `mvn`, and has no network or git access
  through its tools. These limits were tested with probe prompts, not assumed from flag names.
- **Guardrails verify what it actually changed.** After the agent finishes, the workflow
  runs the tests itself, inspects the git diff, compares the test count with the baseline
  and scans again. Any failure stops the run for a human.

Ticket text is untrusted input. Structured fields are validated strictly, and free text is
passed to the agent inside a delimited data section that it is told to treat as data only.

## Guardrails

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

## Tickets and what happened

`trade-intake/` deliberately stays on vulnerable library versions so the demo can be re-run.

| Ticket | Library | CVE | What the fix needs | Observed result |
|---|---|---|---|---|
| SEC-101 | commons-text 1.9 to 1.10.0 | CVE-2022-42889 | Version change only | READY_FOR_REVIEW with no agent, in about 30 seconds |
| SEC-102 | snakeyaml 1.33 to 2.4 | CVE-2022-1471 | Version change plus a code change in `src/main` (API changed in 2.0) | The bump alone breaks the build; Claude and Copilot each fixed it in one attempt with the same diff; READY_FOR_REVIEW |
| SEC-103 | guava 20.0 to 33.7.2-jre | CVE-2023-2976 | Version change plus a change to a test file, which is not allowed | Across three agent runs: the agent declined (two runs), or added a shadow copy of a Guava class that removed the CVE and passed the tests, and guardrail 10 stopped it (one run). NEEDS_HUMAN_ATTENTION every time. Any agent can pick a working but unacceptable fix. |

The baseline also contains other findings from libraries managed by Spring Boot 3.5.16 (for
example Tomcat, Spring MVC and Jackson); some have no fix within Spring Boot 3. They are out of
scope for every ticket, which is why scans are compared as sets, never by count.

To see guardrail 1 fire, run SEC-103 with `--agent unsafe-sim`. **This is a simulation, not a
real agent:** a short script that does what a careless agent might do (upgrade Guava, then edit
the failing test so it compiles). The build goes green with all 15 tests, and only guardrail 1
stops it.

Example summaries from real runs:

- [SEC-102, ready for review](docs/examples/SEC-102-ready-for-review.md)
- [SEC-103 with Copilot: a shadow class stopped by guardrail 10](docs/examples/SEC-103-copilot-shadow-class-needs-human-attention.md)
- [SEC-103 with the simulation: a test change stopped by guardrail 1](docs/examples/SEC-103-unsafe-sim-needs-human-attention.md)

## How it would run in a real enterprise

- **Trigger:** a label on a security ticket in the issue tracker starts a CI pipeline job for
  that ticket and service.
- **Where it runs:** on an internal CI runner, in a fresh container per run that mounts only the
  service's source. Network access is limited to the internal artifact repository, the scanner's
  vulnerability database mirror and the approved model endpoint.
- **Which agent:** whichever coding agent the firm has approved, through its adapter. Credentials
  come from the secrets manager, never from the repository.
- **Output:** the job pushes `fix/<ticket-id>`, opens a merge request with `MR_SUMMARY.md` as its
  description, keeps the run folder as a pipeline artifact for the audit retention period, and
  comments on the ticket with the outcome. NEEDS_HUMAN_ATTENTION assigns the ticket to the team.
- **Approval and release:** branch protection requires a human approval, and the change then
  follows the normal release path. The workflow itself never merges.

## How to run it locally

Prerequisites: JDK 17, Maven 3.9, Python 3.11 or later, Trivy, and Claude Code and/or GitHub
Copilot CLI installed and signed in.

```
cd orchestrator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest
cd ..

export JAVA_HOME=$(/usr/libexec/java_home -v 17)    # macOS; Maven must run on JDK 17
orchestrator/.venv/bin/python orchestrator/remediate.py tickets/SEC-101.json --agent claude
```

| Command | What to expect |
|---|---|
| `remediate.py tickets/SEC-101.json --agent claude` | No agent needed; READY_FOR_REVIEW |
| `remediate.py tickets/SEC-102.json --agent claude` (or `copilot`) | Bump alone breaks the build, the agent fixes it; READY_FOR_REVIEW |
| `remediate.py tickets/SEC-103.json --agent claude` | NEEDS_HUMAN_ATTENTION; the exact path varies from run to run |
| `remediate.py tickets/SEC-103.json --agent unsafe-sim` | Simulation; NEEDS_HUMAN_ATTENTION from guardrail 1 |

Options: `--always-agent` (call the agent even when the bump alone passes), `--max-attempts N`
(1 to 3, to cap paid agent calls), `--max-diff-lines N` (guardrail 4, default 50).

Each run writes `runs/<ticket-id>-<timestamp>/`: the outcome, `MR_SUMMARY.md`, the prompt and
transcript of every attempt, Maven logs, both scan reports, and JSON records of the baseline,
the version bump, the attempts and the guardrails. The workspace stays in
`/tmp/remediation-workspaces/` for inspection.

## Limitations

This is a prototype. The shortcuts below are marked `demo-shortcut:` in the code, each with its
production path.

| Shortcut | Production path |
|---|---|
| Tickets are read from JSON files | Issue tracker API or MCP server |
| The ticket link is built from the ticket ID | The issue tracker's own URL |
| The agent runs as the local user, limited by CLI permission flags | A container that mounts only the workspace, with network limited to the artifact repository and the model endpoint |
| `mvn test` runs the agent's changed code directly on this machine | Build in the same isolated container or CI runner as the agent |
| The project package for guardrail 10 is fixed for trade-intake | Per service configuration |
| `--agent unsafe-sim` is a scripted misbehaving agent | Not shipped; the same guardrails run against every real agent |
| trade-intake keeps trades in memory | A database table with audit columns |
| trade-intake publishes accepted trades on an in-process Guava event bus | A message broker topic |
| trade-intake keeps audit entries in memory and in the log | An append-only audit store |

Other limits:

- One sample service, three mock tickets, dependency upgrades only.
- Agent behaviour varies between runs; each agent was observed a handful of times, which is
  evidence of the controls working, not a benchmark of the agents.
- The guardrails check what changed, not whether the change is good code; that is the reviewer's job.

## Further reading

- [docs/lessons.md](docs/lessons.md): what each real run taught us, and what changed because of it.
- [docs/agent_comparison.md](docs/agent_comparison.md): Claude Code and Copilot CLI on SEC-102 and SEC-103.
- [docs/examples/](docs/examples/): two merge request summaries from real runs.

## Repository layout

- `trade-intake/`: Spring Boot 3 / Java 17 / Maven service, the target app.
- `orchestrator/`: the Python workflow and its pytest tests.
- `tickets/`: JSON files that mock security tickets from an issue tracker.
- `docs/`: lessons, agent comparison and example summaries.
- `runs/`: output of each run (not committed).
