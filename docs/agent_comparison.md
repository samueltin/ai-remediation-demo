# Agent comparison: SEC-102 with Claude Code and GitHub Copilot CLI

Both agents ran the same ticket through the same workflow: the same isolated workspace, the
same deterministic version bump first (which failed with the compile error), the same prompt
including that error, and the same ten guardrails. Only the `--agent` option differed.

| | Claude Code | GitHub Copilot CLI |
|---|---|---|
| CLI version | 2.1.288 | 1.0.97 |
| Model (as reported in the transcript) | claude-opus-5-5 | gpt-6-luna (Copilot's default) |
| Agent attempts | 1 | 1 |
| Agent time | 45.3 s | 39.9 s |
| Whole run, including baseline, bump, scans | 77 s | 66 s |
| Diff size | 5 changed lines | 5 changed lines |
| The change | `new Constructor(ReferenceData.class, new LoaderOptions())` plus the import | **identical** |
| Outcome | READY_FOR_REVIEW, all 10 guardrails pass | READY_FOR_REVIEW, all 10 guardrails pass |
| Tool calls | 10: shell 3, read 2, glob, grep, edit 3 | 7: search, view 2, patch 2, shell 2 |
| Permission denials | 1: a chained `cat ... \| xargs ls -la ...` | 0 |
| Approach | Used the error from the prompt and fixed the code before its first test run | Bumped the pom, ran `mvn test`, saw the compile error, fixed the code, ran again |
| Usage reported by the CLI | 0.121 USD API cost | 1 premium request |
| Transcript | stream-json lines | JSON lines, plus a readable markdown export (`--share`) |

Runs: `runs/SEC-102-20261015-133525` (Claude) and `runs/SEC-102-20261015-133811` (Copilot).

## What this shows

- **The agent is replaceable.** Switching agents needed no change to the workflow: one adapter
  function per CLI (`agents.py`), and everything around it (workspace, deterministic bump,
  tests, scans, guardrails, summary) is shared. The Copilot adapter worked on its first real run.
- **The controls judge the result, not the agent.** Two different models took different paths
  and produced the same diff; the same evidence (workflow test run, scan comparison, ten
  guardrails) supports both summaries.
- **Both CLIs could be held to the same boundary**: edit files in the workspace and run `mvn`,
  with everything else denied in non-interactive mode. The flags differ (`--permission-mode
  dontAsk` and `Bash(mvn *)` for Claude, `--allow-tool shell(mvn:*)` without `--allow-all-tools`
  for Copilot); the observed boundary is the same (see `docs/lessons.md`, lesson 5).

## Limits of this comparison

- One run per agent on one ticket. It is not a benchmark, and the same agent behaves differently
  from run to run (lesson 10).
- Cost is not comparable: Claude reports API cost in USD, Copilot reports premium requests on a
  free plan.
- Copilot ran only SEC-102, to keep within the free plan. The permission probe in Step 5 is the
  evidence for its boundary on the other actions.
