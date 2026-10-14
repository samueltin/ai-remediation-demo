# Project: AI-Assisted Cyber Remediation Demo

**Core focus: show that an AI agent can fix security findings in a Java service safely,
with controls a regulated firm would accept. Every change should serve that outcome.**

## 0. Build and Checks

Run these to prove work is done. Never claim a step is complete without running them.

| What | Command |
|---|---|
| Java tests | `cd trade-intake && mvn test` |
| Python tests | `cd orchestrator && .venv/bin/pytest` |
| Dependency scan | `trivy fs trade-intake` |
| Full demo run | `orchestrator/.venv/bin/python orchestrator/remediate.py tickets/SEC-102.json --agent claude` |
| List demo shortcuts | `grep -rn "demo-shortcut:" orchestrator trade-intake` |

## 1. Background

I am Samuel, an AI Engineer with 20+ years in financial services.
I am building this demo to show how a Java development team in a regulated financial
services firm could use AI agents safely for cyber remediation.

The target audience:
- A large team of experienced Java developers
- Java microservices (Java 17+, Spring Boot, REST, message brokers)
- Typical enterprise toolchain: Git server, issue tracker, wiki, an approved AI coding assistant
- A multi-stage release process (for example DEV, test, UAT, production)
- Safety and auditability matter more than speed

Do not name or reference any real company as the target in code, docs or comments.

## 2. Demo Goal

An AI agent fixes a security finding in a Java service, tests itself, verifies the fix,
and hands a merge request summary to a human.

Key message: the coding agent is replaceable (Claude Code or GitHub Copilot CLI).
The value is the controlled workflow around it: scan, test, verify, guardrails, human approval.

## 3. Repository Layout

One git repo, opened as a single root folder in VS Code (with the Claude Code extension).
It contains two independent projects: a Java project and a Python project.

```
ai-remediation-demo/
  CLAUDE.md                 this file (context for building the demo)
  README.md
  .gitignore
  .vscode/
    settings.json           Java and Python settings for both projects
    extensions.json         recommended extensions
  trade-intake/             PROJECT 1: Spring Boot 3, Java 17, Maven (the TARGET app)
    pom.xml
    src/main/java/...
    src/main/resources/...
    src/test/java/...
  orchestrator/             PROJECT 2: Python agentic workflow
    pyproject.toml          or requirements.txt (keep dependencies minimal)
    .venv/                  local virtual environment (gitignored)
    remediate.py            entry point
    ticket.py, workspace.py, scanner.py, agents.py, guardrails.py, summary.py
    prompt_template.txt
    tests/                  pytest tests for the orchestrator
  tickets/                  JSON files that mock security tickets
  runs/                     output of each run (reports, summaries, transcripts), gitignored
  docs/                     diagrams, agent comparison
```

Rules:
- Do NOT create a CLAUDE.md or AGENTS.md inside `trade-intake/`. That folder is copied into
  the agent workspace, and the remediation agent must not receive builder instructions.
- The two projects do not import each other. The orchestrator only interacts with the
  Java app through files, git, Maven and Trivy commands.
- The orchestrator has its own pytest tests, so the workflow itself is tested, not just the Java app.

## 4. Isolation

The remediation agent must NOT see this file or the orchestrator code.
For each run, the orchestrator copies `trade-intake/` into a fresh workspace OUTSIDE this
repo (for example `/tmp/remediation-workspaces/<ticket-id>-<timestamp>/`), initialises git
there, and runs the agent in that workspace only. The baseline in `trade-intake/` always keeps
the vulnerable versions so the demo can be re-run.

## 5. The Sample App: trade-intake

- One REST endpoint: `POST /trades` accepting a simplified interest rate swap trade
  (tradeId, notional, currency, fixedRate, startDate, maturityDate, counterparty).
- A `TradeValidator` with simple rules (supported currency, positive notional,
  maturity after start date, rate within sensible range).
- Light financial flavour only. No real clearing, margin or FpML logic.
- 10 to 15 JUnit 5 tests that pass.

## 6. Guardrails the Workflow Must Enforce

| # | Guardrail | Risk it controls |
|---|---|---|
| 1 | Agent may not modify any file under `src/test/` | Agent passes by weakening tests |
| 2 | Only the ticket's library version may change in pom.xml; no added or removed dependencies | Hallucinated or malicious packages |
| 3 | Maximum 3 agent attempts per ticket | Endless loops and runaway cost |
| 4 | Diff size limit (default 50 changed lines) | Unexpectedly wide changes |
| 5 | Scan before and after; the finding is gone and no new findings appear | Fix that does not really fix |
| 6 | Ticket ID in branch name, commit message and summary | Lost traceability |
| 7 | Agent transcript saved | No audit trail |
| 8 | The workflow NEVER merges | Bypassing human approval |

## 7. Engineering Rules

- **Minimalism**: write the minimum code. No abstraction without a second real use.
  The agent adapter is justified (Claude and Copilot). Nothing else needs a framework.
- **Fail fast, never fail silent**: no silent fallbacks, no `except` that swallows errors.
  If a ticket is invalid, a scan fails, an agent CLI errors or a command times out,
  stop with a clear reason. Catch only what you can handle.
- **Validate at the boundary**: the ticket JSON is validated when loaded. Everything the agent
  changed is untrusted until all guardrails pass. Command output is checked, not assumed.
- **One outcome, not scattered flags**: each run ends in exactly one `RunOutcome`:
  `READY_FOR_REVIEW`, `NEEDS_HUMAN_ATTENTION` (with reason) or `FAILED` (with reason).
  Decide it once; the console, summary and exit code all use it.
- **Marked shortcuts**: any demo simplification gets a comment that names its limit
  and the production path, for example:
  `# demo-shortcut: ticket read from JSON file. Production: issue tracker API or MCP server.`
  The README Limitations section is built from these comments.
- **Test first (red, green)**: for new behaviour or a fix, write the test, watch it fail for the
  intended reason, make the minimum change, rerun green. Example: write the test
  "a change under src/test is rejected" before writing that guardrail.
- **Comments**: explain only the *why* the code cannot show. The rest goes in commit messages.
- **Secrets**: never hard-code secrets or API keys.

## 8. Glossary (one concept, one word)

| Term | Meaning |
|---|---|
| ticket | A mocked security work item in `tickets/` |
| finding | A vulnerability reported by the scanner (one CVE in one library) |
| run | One execution of the workflow for one ticket |
| attempt | One call to the coding agent within a run (max 3) |
| workspace | The isolated copy of trade-intake used for a run |
| guardrail | An automated check that must pass before handover |
| outcome | The single final result of a run (`RunOutcome`) |
| summary | `MR_SUMMARY.md`, the handover document for the human reviewer |

Use these words in code, docs and the README. Add a term here before coining a new one.

## 9. Tools

- Java 17, Maven
- Trivy for dependency scanning (`trivy fs`)
- Python 3.11+ (standard library preferred)
- Coding agent CLI: `claude -p` or `copilot -p` (pluggable via `--agent`)
- Always check current CLI flags with `claude --help` and `copilot help` rather than assuming

## 10. Git Safety

- Commit after each completed step with a conventional commit message.
- Push only when I explicitly ask.
- Never commit anything under `runs/` or any `.venv/`.

## 11. How to Work With Me

- Work in small steps. Stop at the end of each step.
- I have not written Java day to day for some years. Briefly explain Java and Spring choices
  so I can defend them in an interview. Keep code simple and readable, not clever.
- Use plain English in docs and comments. No double dashes in generated text.
- Default to one agent. No subagents unless I ask.

At the end of each step, reply in this format:
1. A 2 to 4 point summary of what was done and what it means
2. New or changed files, each with its purpose
3. A short ASCII diagram or table only if a flow spans several components
4. Verified (with the commands run) vs unverified, open questions and assumptions,
   and a **confidence score from 0 to 100%**
5. A one-line conventional commit message
