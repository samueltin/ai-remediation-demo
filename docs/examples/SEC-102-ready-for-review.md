_Example copied from a real run. Local paths are replaced by `<workspace>`. The linked transcripts and logs stay in the run folder and are not included here._

# SEC-102: Upgrade snakeyaml to fix CVE-2022-1471

**Outcome: READY_FOR_REVIEW**: all guardrails pass after 1 attempt(s)

Requires human review and approval. Not merged.

| | |
|---|---|
| Ticket | [SEC-102](https://issues.example.com/browse/SEC-102) |
| Finding | CVE-2022-1471 in org.yaml:snakeyaml 1.33, HIGH (severity as reported by the scanner) |
| Change requested | org.yaml:snakeyaml 1.33 to 2.4 |
| Branch | `fix/SEC-102` at `784c7d3` in `<workspace>` |
| Agent | claude (model claude-opus-5-5), 1 attempt(s) |

## What changed

```
 pom.xml                                                        | 2 +-
 src/main/java/com/example/tradeintake/ReferenceDataConfig.java | 3 ++-
 2 files changed, 3 insertions(+), 2 deletions(-)
```

```diff
diff --git a/pom.xml b/pom.xml
index cdef007..106aea2 100644
--- a/pom.xml
+++ b/pom.xml
@@ -36,7 +36,7 @@
         <dependency>
             <groupId>org.yaml</groupId>
             <artifactId>snakeyaml</artifactId>
-            <version>1.33</version>
+            <version>2.4</version>
         </dependency>
 
         <dependency>
diff --git a/src/main/java/com/example/tradeintake/ReferenceDataConfig.java b/src/main/java/com/example/tradeintake/ReferenceDataConfig.java
index 0d961f9..38c1ead 100644
--- a/src/main/java/com/example/tradeintake/ReferenceDataConfig.java
+++ b/src/main/java/com/example/tradeintake/ReferenceDataConfig.java
@@ -7,6 +7,7 @@ import java.io.UncheckedIOException;
 import org.springframework.context.annotation.Bean;
 import org.springframework.context.annotation.Configuration;
 import org.springframework.core.io.ClassPathResource;
+import org.yaml.snakeyaml.LoaderOptions;
 import org.yaml.snakeyaml.Yaml;
 import org.yaml.snakeyaml.constructor.Constructor;
 
@@ -17,7 +18,7 @@ public class ReferenceDataConfig {
 
     @Bean
     public ReferenceData referenceData() {
-        Yaml yaml = new Yaml(new Constructor(ReferenceData.class));
+        Yaml yaml = new Yaml(new Constructor(ReferenceData.class, new LoaderOptions()));
         ReferenceData data;
         try (InputStream in = new ClassPathResource(RESOURCE).getInputStream()) {
             data = yaml.load(in);
```

## Version bump alone (by the workflow)

**The upgrade alone breaks the build.** The workflow applied only the version change and ran
mvn test before calling any agent. This is the evidence that a code change was needed.
The workspace was reset before the agent started. Key errors:

```
[ERROR] COMPILATION ERROR : 
[ERROR] <workspace>/src/main/java/com/example/tradeintake/ReferenceDataConfig.java:[20,59] incompatible types: java.lang.Class<com.example.tradeintake.ReferenceData> cannot be converted to org.yaml.snakeyaml.LoaderOptions
[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.14.1:compile (default-compile) on project trade-intake: Compilation failure
```

## Tests (run by the workflow, not by the agent)

| Run | Result | Tests run | Failed | Errors | Skipped |
|---|---|---|---|---|---|
| Baseline (before the agent) | PASS | 15 | 0 | 0 | 0 |
| Version bump alone (by the workflow) | FAIL | 0 | 0 | 0 | 0 |
| Attempt 1 | PASS | 15 | 0 | 0 | 0 |

## Dependency scan (Trivy)

Findings before: 23. Findings after: 22. Compared as sets of (CVE ID, package, installed version).

- CVE-2022-1471 in org.yaml:snakeyaml: gone
- New findings: none
- Resolved: CVE-2022-1471 in org.yaml:snakeyaml 1.33
- Other findings are unchanged. They come from libraries managed by Spring Boot and are out of
  scope for this ticket.

## Guardrails

| # | Guardrail | Result | Detail |
|---|---|---|---|
| 1 | No changes under src/test/ | PASS | no test files changed |
| 2 | Only the ticket's library version changed in pom.xml | PASS | org.yaml:snakeyaml 1.33 -> 2.4, nothing else |
| 3 | Tests green within 3 agent attempts | PASS | green after 1 attempt(s) |
| 4 | Diff size within 50 changed lines | PASS | 5 changed lines (limit 50) |
| 5 | Scan after: ticket finding gone, no new findings | PASS | CVE-2022-1471 gone, no new findings, 1 finding(s) resolved |
| 6 | Ticket ID in branch name and commit message | PASS | branch fix/SEC-102, commit 'SEC-102: Upgrade snakeyaml to fix CVE-2022-1471' |
| 7 | Agent transcript saved for every attempt | PASS | 1 transcript(s) saved |
| 8 | Nothing merged or pushed | PASS | main is still the baseline and there is no remote |
| 9 | Same number of tests as the baseline, none skipped | PASS | 15 run, same as the baseline, 0 skipped |
| 10 | Only existing files changed, Java only in com.example.tradeintake | PASS | only existing files modified |

## Agent attempts

| Attempt | Agent time | New change | mvn test | Transcript |
|---|---|---|---|---|
| 1 | 45.3s | yes | PASS | [claude_attempt_1.jsonl](claude_attempt_1.jsonl) |

Agent's own summary of its last attempt (unverified; the evidence above is what counts):

> SnakeYAML is now at 2.4 and `mvn test` passes: BUILD SUCCESS, 15 tests run, 0 failures, 0 errors, 0 skipped.
>
> **Files changed**
> - `pom.xml`: changed `org.yaml:snakeyaml` from `1.33` to `2.4`. Nothing else in the file was touched.
> - `src/main/java/com/example/tradeintake/ReferenceDataConfig.java`: SnakeYAML 2.x requires `LoaderOptions` when building a `Constructor`. I changed `new Constructor(ReferenceData.class)` to `new Constructor(ReferenceData.class, new LoaderOptions())` and added the import. The default `LoaderOptions` keep the same behaviour for loading `reference-data.yml`, and also block the arbitrary global tags behind CVE-2022-1471.
>
> I didn't change anything under `src/test` and didn't run any git commands. I also didn't run the dependency scan, so the scan-related acceptance criteria are still to be checked.

## Audit trail

All files are in this run folder: the prompt for each attempt (`prompt_attempt_N.txt`), the agent
transcripts, the Maven logs (`mvn_test_*.log`), `scan_before.json`, `scan_after.json`,
`attempts.json`, `baseline_tests.json`, `version_bump.json` and `guardrails.json`.

## For the reviewer

- Read the diff and check that the change keeps the existing behaviour.
- Approve or reject in the merge request. The workflow does not merge.

Requires human review and approval. Not merged.
