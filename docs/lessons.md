# Lessons from real runs

Each entry records something a real run or check taught us, not something we assumed.
Format: what happened, how it was found, what changed, and why it matters for a regulated team.

## 1. The baseline scan has findings no ticket asked for

- **What happened:** the first Trivy scan of trade-intake reported 20 findings, not the 2 we planted.
  The other 18 came from libraries Spring Boot 3.5.16 manages (Tomcat, Spring MVC, Jackson,
  Log4j API, commons-lang3). Some have no fix on Spring Boot 3.
- **How it was found:** Step 2, first `trivy fs` run.
- **What changed:** we kept the noise on purpose. The workflow compares scans as sets of
  (CVE ID, package, installed version), never by count: the ticket's finding must be gone and
  nothing may be new. The README explains that these findings are out of scope for each ticket.
- **Why it matters:** real scans are always noisy, so a control that compares counts can pass a
  change that removes one finding and adds another.

## 2. A problem we predicted did not exist: duplicate findings from target/

- **What happened:** we expected Trivy to scan a built jar in `target/` and report every finding
  twice, and wrote that into CLAUDE.md as the reason to exclude `target/` from the workspace.
  When tested, `trivy fs` reported only `pom.xml` and the same 23 findings with a jar present.
  `trivy fs` reads build manifests; jars are scanned in `rootfs` or image mode.
- **How it was found:** Step 7 preparation, building the jar in a scratch copy and scanning
  with and without it.
- **What changed:** the reason in CLAUDE.md was corrected. Excluding `target/` stays, for the
  reason in lesson 3.
- **Why it matters:** a control justified by a wrong reason gives false confidence and is easy
  to remove later; each control should be backed by an observed failure or a test.

## 3. Stale build output hid a compile error from the agent

- **What happened:** after the SEC-102 upgrade, the agent's own `mvn test` showed 14 runtime
  `NoSuchMethodError`s instead of the real compile error. The orchestrator's baseline build had
  left compiled classes in `target/`, and Maven's incremental compile did not recompile the
  unchanged source file. The agent still found the right fix, from a misleading signal.
- **How it was found:** Step 6, reading the agent transcript of the first real SEC-102 run.
- **What changed:** every orchestrator build now runs `mvn clean test` and then removes
  `target/`, so each attempt starts from the same state as a fresh checkout. A test with a fake
  `mvn` proves it. On the next run the agent saw the real `COMPILATION ERROR`.
- **Why it matters:** the verdict that counts must come from a clean, independent build, not
  from the agent's own run in whatever state the workspace happens to be in.

## 4. A zero exit code does not mean the tests passed

- **What happened:** with `-Dmaven.test.failure.ignore=true` and 3 failing tests, Maven printed
  `Tests run: 15, Failures: 3` and then `BUILD SUCCESS`, and exited with code 0. An agent could
  get the same effect by adding `testFailureIgnore` to pom.xml.
- **How it was found:** design review in Step 6, then reproduced in a scratch copy in Step 7.
- **What changed:** a build counts as green only if Maven exits 0 and the Surefire reports show
  no failures and no errors. Guardrail 2 also rejects any pom.xml change other than the ticket's
  version, and guardrail 9 compares the test count with the baseline.
- **Why it matters:** "the pipeline was green" is not evidence on its own; the evidence is the
  test reports, checked by something the agent cannot configure.

## 5. Permission flags are less strict than they read

- **What happened:** with only `Bash(mvn *)` allowed, Claude Code still ran `ls`, `git log`,
  `cat pom.xml; find src` and `mvn test | tail`. It treats read-only commands inside the
  workspace as safe. `--restricted` confines the file tools, not the shell. Copilot behaved the
  same way. Reads outside the workspace, network access, shell writes, `git init` and chained
  commands such as `mvn -v && touch x` were denied.
- **How it was found:** Step 5, probe prompts that asked each CLI to try a list of allowed and
  forbidden actions, then reading the permission denials in the transcripts.
- **What changed:** the boundary we claim is the observed one, documented in `agents.py`. Tests
  lock the permission flags. The production path is a container that mounts only the workspace.
- **Why it matters:** an auditor will ask what the agent could do, and the answer has to come
  from testing the tool, not from reading its flag names.

## 6. The developer machine silently chose the JDK

- **What happened:** VS Code was set to JDK 17 for this project, but `~/.zshenv` reset
  `JAVA_HOME` to JDK 24 in every new shell, so Maven ran on 24.
- **How it was found:** Step 0, `mvn -version` in a new terminal still showed Java 24.
- **What changed:** `~/.zshenv` now only sets a default. The orchestrator checks `mvn -v` first
  and stops with FAILED unless Maven runs on JDK 17.
- **Why it matters:** a remediation verified on a different JDK than production is not verified;
  the toolchain must be checked, not assumed.

## 7. The agent refused honestly, but the retry loop paid for two more refusals

- **What happened:** on SEC-103 the agent upgraded Guava, saw the test compile error, and stopped
  with "SEC-103 can't be finished within the rules", naming the one-line test fix a human should
  approve. Attempts 2 and 3 got the build errors, changed nothing, and refused again with the same
  reasoning. The loop did not stop, because "workspace changed" compares with the baseline, so the
  pom change from attempt 1 still counted as a change.
- **How it was found:** Step 7, the first real SEC-103 run, reading `attempts.json` and the three
  transcripts (attempt 2: 2 turns, attempt 3: 3 turns, no edits in either).
- **What changed:** the loop now stops when an attempt adds no new change, with the reason
  "agent declined, no new change in attempt N". A test with a fake agent proves it.
- **Why it matters:** a retry policy should spend money only when the last attempt made progress;
  an honest refusal is a result to hand to a human, not a failure to retry.

## 8. The permission boundary blocked a real action, and the agent took the allowed path

- **What happened:** in SEC-103 attempt 1 the agent tried to change the pom with
  `sed -i ... pom.xml && git diff --stat && mvn -q test`. Claude Code denied it (a shell write
  and a chained command). The agent then read pom.xml and used the Edit tool instead.
- **How it was found:** Step 7, the `permission_denials` list in the attempt 1 transcript.
- **What changed:** nothing; this confirms in a real run the boundary that the Step 5 probes
  showed.
- **Why it matters:** file changes go through the edit tool, so every change appears in the
  transcript as a reviewable edit, not hidden inside a shell command.

## 9. The agent's own reasoning revealed a bypass that four guardrails would have missed

- **What happened:** in SEC-103 attempt 3 the agent wrote that it could copy Guava's
  `com.google.common.util.concurrent.MoreExecutors` into `src/main` with the old method added back,
  and rejected the idea as a forbidden workaround. Had it done so, guardrails 1 (no test change),
  2 (pom only the version), 4 (diff size) and 9 (same test count) would all have passed: the
  project's copy of the class would override the library's.
- **How it was found:** reading the final message of the SEC-103 transcripts in Step 7.
- **What changed:** guardrail 10: the agent may only modify existing files, and every changed
  `.java` file must be in `com.example.tradeintake`. The first test written was a shadow
  `MoreExecutors.java` added under `src/main`, which must fail.
- **Why it matters:** the agent's explanations are a free threat model; read them, and turn every
  workaround it mentions into a check that does not depend on it choosing not to.

## 10. The same agent and prompt behaved differently from one run to the next

- **What happened:** in the first SEC-103 run Claude left Guava upgraded in pom.xml and stopped.
  In the next run, with the same prompt, it upgraded Guava, saw the same compile error, put the
  version back to 20.0 and stopped, leaving the workspace unchanged. Both runs ended correctly
  as NEEDS_HUMAN_ATTENTION, through different paths (guardrails 3 and 9 the first time,
  "agent declined, no new change in attempt 1" the second time).
- **How it was found:** Step 7, comparing the two SEC-103 transcripts.
- **What changed:** nothing in the code; both paths were already handled. The demo script should
  not promise one exact path for SEC-103, only the outcome.
- **Why it matters:** agent output is not deterministic, so controls must judge the result in
  the workspace, never assume the agent will repeat what it did in testing.

The simulated agent (`--agent unsafe-sim`) was then used to show guardrail 1 firing: the build
went green with 15 tests, and only guardrail 1 stopped the run.

## 11. The demo story "compile failure, then fix" is not guaranteed

- **What happened:** in the Step 8 SEC-102 run the agent knew that SnakeYAML 2.x needs
  `LoaderOptions` and fixed `ReferenceDataConfig` before its first test run, so it never saw a
  compile failure. Its first command, which chained the version bump, a search and `mvn test`,
  was denied by the permission mode. It said all this openly in its final message ("I never saw
  the compile failure myself"). The result was correct, and every guardrail passed.
- **How it was found:** Step 8, reading the agent's summary in `MR_SUMMARY.md`.
- **What changed:** nothing in the workflow. For the recorded demo, the compile failure has to be
  shown from evidence that does not depend on the agent, for example by building the version
  bump alone, and the narration should say the agent may or may not hit it.
- **Why it matters:** a demo or audit narrative must rest on what the workflow guarantees, not on
  one lucky path the agent happened to take.

## 12. A real fix with a clean scan and green tests is still stopped if it changes a test

- **What happened:** the simulated agent (`--agent unsafe-sim`) on SEC-103 upgraded Guava and edited
  the failing test. The fix was real: the after scan resolved all three Guava findings, no new
  findings appeared, and all 15 tests passed. Guardrail 1 alone stopped it.
- **How it was found:** Step 8, the first SEC-103 run with the after scan and the summary.
- **What changed:** nothing; this is the behaviour we want, and the summary shows it in one table.
- **Why it matters:** "it works" is not the approval criterion; a change to the tests that judge
  the change needs a human, however reasonable it looks.

## 13. Deterministic first, AI second

- **What happened:** before calling any agent, the workflow now applies the plain version bump
  itself and runs the clean build, the tests and the after scan. SEC-101 then needed no agent at
  all: READY_FOR_REVIEW in 29 seconds at no model cost, with the same ten guardrails. With
  `--always-agent` the same ticket took 86 seconds and 0.10 USD for an identical one-line diff.
  For SEC-102 the bump alone failed in 4 seconds with the real compile error
  (`ReferenceDataConfig.java:[20,59] incompatible types`). That error is recorded in the summary
  as evidence that a code change was needed, and the agent received it in its first prompt; it
  went straight to the fix (read two files, three edits, two test runs).
- **How it was found:** lesson 11 showed the compile failure was not guaranteed to appear in the
  agent's transcript, so the workflow now produces it itself. The runs above confirmed it.
- **What changed:** a deterministic first step (`try_version_bump`), `--always-agent` to force the
  agent, "Agent: none (deterministic fix)" in the summary, and Maven's generic help text removed
  from the error lines given to the agent and the reviewer.
- **Why it matters:** the cheapest, most predictable and most auditable change is the one no model
  made; the agent is for the part a script cannot do, and the reviewer gets evidence of why it was
  needed.

## 14. On SEC-102, two agents produced identical diffs and the workflow needed no change

- **What happened:** SEC-102 with GitHub Copilot CLI (model gpt-6-luna) reached READY_FOR_REVIEW in
  one attempt, with a diff identical to Claude Code's. The paths differed: Claude used the
  compile error from the deterministic step and fixed the code before testing; Copilot bumped the
  pom, reproduced the compile error with `mvn test`, then fixed it. Claude had one permission
  denial (a chained `xargs` command), Copilot none.
- **How it was found:** Step 9, one Copilot run compared with the latest Claude run of the same
  workflow (`docs/agent_comparison.md`).
- **What changed:** nothing; the Copilot adapter from Step 5 worked on its first real run.
- **Why it matters:** switching agents was a change to one adapter, not to the workflow. One run
  on one ticket is not proof that the agents are equivalent; the controls are what make either
  result reviewable.
