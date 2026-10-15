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
- **What changed:** recorded here; a per-attempt change check is proposed so the loop stops when an
  attempt adds nothing new.
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
