# Step-by-Step Prompts for Claude Code

Paste one step at a time. Review and test before moving to the next.
Run Claude Code from the repo root so it reads CLAUDE.md.

---

## Step 0: Environment and workspace setup

Before starting: create the empty folder `ai-remediation-demo`, put CLAUDE.md and STEPS.md
in it, open that folder in VS Code (File > Open Folder), and start Claude Code there.

```
Read CLAUDE.md. Then check my environment: Java 17, Maven, git, Python 3.11+, Trivy,
claude CLI and copilot CLI. Tell me what is missing and how to install it on macOS.

Then set up the root workspace with two projects as described in CLAUDE.md:
- Create the folder structure (empty project folders are fine for now)
- .gitignore: runs/, target/, __pycache__/, .venv/, *.pyc, .DS_Store, .idea/
- .vscode/extensions.json recommending: Extension Pack for Java, Spring Boot Extension Pack,
  Python, Pylance, and Claude Code
- .vscode/settings.json so that:
  - the Java extension finds the Maven project in trade-intake/
  - the Python interpreter is orchestrator/.venv
  - pytest runs from orchestrator/tests
- Create the Python virtual environment in orchestrator/.venv with pytest installed
- Initialise git and make the first commit

Do not write application code yet.
```

**Verify:** all tools report a version. VS Code shows the Java project in the Java Projects
view and uses the orchestrator/.venv Python interpreter. First commit exists.

---

## Step 1: Build the Java service with unit tests

```
Build the trade-intake Spring Boot 3 / Java 17 / Maven service described in CLAUDE.md.

Include:
- Trade record (or class) with the fields listed
- TradeValidator with the validation rules, returning a list of errors
- TradeController with POST /trades: 201 if valid, 400 with errors if not
- An in-memory store is fine; no database
- 10 to 15 JUnit 5 tests: validator tests plus a few controller tests with MockMvc

Explain briefly in comments or in your summary why you chose a record vs class,
how MockMvc works, and how validation errors are returned.
Run mvn test and show me the result.
```

**Verify:** `cd trade-intake && mvn test` passes. Try one curl request.

---

## Step 2: Add the vulnerable libraries

```
Add two vulnerable libraries to trade-intake and USE them in real code so upgrades matter:

SEC-101 (easy): org.apache.commons:commons-text 1.9 (CVE-2022-42889).
  Use it for something simple, for example formatting a trade summary string.

SEC-102 (harder): a library whose safe version CHANGES THE API so code must be updated.
  First candidate: org.yaml:snakeyaml 1.33 to 2.x (CVE-2022-1471), used in a small class
  that loads a reference-data YAML file (for example supported currencies) using the
  old Constructor style.
  Spring Boot 3 manages its own snakeyaml version, so check this does not break Spring Boot
  startup or tests. If it conflicts, propose a different library with a known CVE and a
  breaking API change in the fixed version, and explain the choice before continuing.

Then prove the demo is meaningful:
1. Run trivy fs on trade-intake and show both findings.
2. Temporarily upgrade the SEC-102 library and show that compilation FAILS.
3. Revert to the vulnerable baseline and confirm mvn test passes again.
```

**Verify:** Trivy shows both CVEs. The SEC-102 upgrade breaks compile. Baseline is green.

---

## Step 3: Create the mock issue tracker tickets

```
Create tickets/SEC-101.json and tickets/SEC-102.json mocking issue tracker security tickets.
Fields: ticket_id, title, severity, cve_id, library (groupId:artifactId),
current_version, target_version, service, description, acceptance_criteria (list).

Also create tickets/SEC-103.json for a deliberate failure case: a ticket where the fix
would require changing a test file (for example a test that directly uses the old API).
Add whatever small change to trade-intake is needed so SEC-103 is realistic, and keep
mvn test green on the baseline. Explain the scenario.
```

**Verify:** three valid JSON files. Baseline still passes tests.

---

## Step 4: Orchestrator skeleton

```
Create orchestrator/remediate.py, run as:
  python orchestrator/remediate.py tickets/SEC-102.json --agent claude

For now implement only:
1. Load and validate the ticket
2. Create a fresh workspace outside the repo by copying trade-intake/ (see CLAUDE.md isolation rule)
3. git init in the workspace, commit the baseline, create branch fix/<ticket_id>
4. Run trivy before, save JSON report to runs/<ticket_id>-<timestamp>/scan_before.json
5. Confirm the ticket's CVE is present; if not, stop with a clear message

Keep the code split into small modules (ticket.py, workspace.py, scanner.py).
Print clear step-by-step progress to the console.
```

**Verify:** a run creates the workspace and the before-scan report.

---

## Step 5: Pluggable agent adapter

```
Add orchestrator/agents.py with one function per agent: run_claude(workspace, prompt)
and run_copilot(workspace, prompt). Both run non-interactively in the workspace.

Check the current flags with `claude --help` and `copilot help`. Restrict tools as far as
each CLI allows: file edits in the workspace and running mvn only. Save the full agent
output or transcript to the run folder.

Create the agent prompt from the ticket with a template in orchestrator/prompt_template.txt:
upgrade the named library to the target version in pom.xml, fix compile errors in
src/main only, do not modify tests, do not add or change other dependencies,
run mvn test, stop when tests pass.

Run SEC-101 with the claude agent and show the result.
```

**Verify:** SEC-101 run upgrades commons-text. Transcript saved.

---

## Step 6: Build, test and retry loop

```
After the agent runs, the orchestrator itself (not the agent) runs mvn test in the workspace.
If tests fail, call the agent again with the test failure output appended, up to 3 attempts
in total. Record each attempt (number, duration, pass or fail) in the run folder.
Commit the agent's changes in the workspace with message "<ticket_id>: <title>".

Run SEC-102 and show the attempts.
```

**Verify:** SEC-102 shows a compile failure, then a fix, then green tests.

---

## Step 7: Guardrails

```
Add orchestrator/guardrails.py implementing all guardrails from CLAUDE.md, checked
after the agent finishes and before the summary:
- No changes under src/test/
- In pom.xml, only the ticket's library version changed; no added or removed dependencies
- Diff size within the limit (configurable, default 50 lines)
- Attempt limit respected

Each check returns pass or fail with a reason. If any fail, stop and write
NEEDS HUMAN ATTENTION: <reason> to the run folder and the console.

Run SEC-103 and show the guardrail blocking it (or the agent correctly refusing).
```

**Verify:** SEC-103 ends with NEEDS HUMAN ATTENTION and a clear reason.

---

## Step 8: Verify and hand over

```
Add the final stage:
1. Run trivy after; confirm the ticket's CVE is gone and no new findings were introduced
2. Write runs/<run>/MR_SUMMARY.md containing:
   ticket link and title, CVE, what changed (diff stat and key lines), tests run and result,
   scan before vs after, guardrail results, number of agent attempts, agent used,
   link to transcript, and the line "Requires human review and approval. Not merged."
3. Print the path to MR_SUMMARY.md

Run SEC-101 and SEC-102 end to end and show both summaries.
```

**Verify:** both summaries are clear enough for a reviewer who did not watch the run.

---

## Step 9: Run with GitHub Copilot CLI

```
Run SEC-102 with --agent copilot. Fix any adapter issues. Compare the result with the
claude run in a short table (attempts, time, diff size, outcome). Save it to docs/agent_comparison.md.
```

**Verify:** the same workflow works with Copilot CLI.

---

## Step 10: README and diagram

```
Write README.md for the repo:
- The problem: cyber remediation backlog in a regulated Java team
- What the demo does, in 5 lines
- Flow diagram (Mermaid): ticket, scan, agent, test loop, guardrails, scan, MR summary, human
- Guardrails table: each guardrail and the risk it controls
- How it would run in a real enterprise: Git server CI job on an internal runner, triggered by
  an issue tracker label, using the approved coding agent, posting the MR and updating the issue tracker
- How to run it locally
- Limitations (prototype, mock tickets, single service)
Plain English, no hype, no double dashes.
```

**Verify:** a stranger can understand the demo in 2 minutes from the README.

---

## After the build: record the demo (3 minutes)

1. Ticket and Trivy finding
2. Run SEC-102: compile failure, agent fixes, tests pass
3. Scan after: finding closed
4. MR_SUMMARY.md
5. SEC-103: guardrail stops it
6. Close: "The agent is replaceable. The value is the controls around it."
