"""Coding agent adapters.

Each adapter runs one agent attempt non-interactively in the workspace. Tools are limited
to reading and editing files in the workspace and running mvn; anything else needs an
approval that nobody can give, so the CLI denies it. The full transcript is streamed to
the run folder for audit.

The restriction flags were checked with probe prompts against Claude Code 2.1.288 and
Copilot CLI 1.0.97. Both still allow read-only shell commands such as ls inside the workspace.
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template

from commands import run
from ticket import Ticket, TicketError

PROMPT_TEMPLATE = Path(__file__).resolve().parent / "prompt_template.txt"
UNSAFE_SIM_SCRIPT = Path(__file__).resolve().parent / "unsafe_sim_agent.py"
SECTION_MARKER = re.compile(r"</?\s*(ticket_data|build_output)\s*>", re.IGNORECASE)
RETRY_TEMPLATE = Template("""
A previous attempt left the workspace in its current state. The workflow then ran mvn test
itself and the build failed. Continue from the current state. The build errors were:

<build_output>
$errors
</build_output>
""")
BUMP_TEMPLATE = Template("""
Before calling you, the workflow applied only the version change in pom.xml and ran mvn test
itself. The build failed, so a code change under src/main is probably needed. The workspace
has been reset to its original state, so you still need to make the version change yourself.
The build errors were:

<build_output>
$errors
</build_output>
""")
AGENT_TIMEOUT_SECONDS = 1800
CLAUDE_MAX_BUDGET_USD = "5"

# demo-shortcut: the agent runs as the local user, limited by CLI permission flags.
# Production: run it in a container that mounts only the workspace, with network limited
# to the internal artifact repository and the model endpoint.


class AgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentResult:
    final_message: str
    model: str


def build_prompt(ticket: Ticket, previous_errors: tuple[str, ...] = (),
                 bump_errors: tuple[str, ...] = ()) -> str:
    """The agent prompt. Ticket free text and build output only ever appear inside data sections.

    previous_errors come from the workflow's build after the previous attempt; bump_errors from
    the workflow's own build of the plain version bump, before the first attempt.
    """
    for text in (ticket.title, ticket.description, *ticket.acceptance_criteria):
        if SECTION_MARKER.search(text):
            raise TicketError(f"{ticket.ticket_id}: ticket text contains a prompt data section marker")
    previous_attempt = ""
    for template, lines in ((BUMP_TEMPLATE, bump_errors), (RETRY_TEMPLATE, previous_errors)):
        if lines:
            # Build output can echo text the agent wrote, so markers are removed rather than trusted.
            errors = "\n".join(SECTION_MARKER.sub("", line) for line in lines)
            previous_attempt += template.substitute(errors=errors)

    template = Template(PROMPT_TEMPLATE.read_text())
    return template.substitute(
        previous_attempt=previous_attempt,
        ticket_id=ticket.ticket_id,
        title=ticket.title,
        cve_id=ticket.cve_id,
        library=ticket.library,
        severity=ticket.severity,
        description=ticket.description,
        current_version=ticket.current_version,
        target_version=ticket.target_version,
        acceptance_criteria="\n".join(f"- {item}" for item in ticket.acceptance_criteria),
    )


def claude_command(prompt: str) -> list[str]:
    return [
        "claude", "-p", prompt,
        # Confines file tools to the workspace and ignores user, project and local settings.
        "--restricted",
        # No CLAUDE.md, hooks, plugins, skills or MCP servers from this machine.
        "--safe-mode", "--strict-mcp-config", "--disable-slash-commands",
        "--tools", "Read,Edit,Write,Glob,Grep,Bash",
        "--allowedTools", "Read Edit Write Glob Grep Bash(mvn *)",
        "--permission-mode", "dontAsk",
        "--max-budget-usd", CLAUDE_MAX_BUDGET_USD,
        "--no-session-persistence",
        "--output-format", "stream-json", "--verbose",
    ]


def copilot_command(prompt: str, share_path: Path) -> list[str]:
    return [
        "copilot", "-p", prompt,
        # Without --allow-all-tools, anything not allowed here is denied in non-interactive mode.
        "--allow-tool", "write",
        "--allow-tool", "shell(mvn:*)",
        "--disallow-temp-dir",
        "--no-custom-instructions", "--disable-builtin-mcps",
        "--no-ask-user", "--no-auto-update",
        "--output-format", "json",
        "--share", str(share_path),
    ]


def run_claude(workspace: Path, prompt: str, transcript: Path) -> AgentResult:
    run(claude_command(prompt), cwd=workspace, timeout=AGENT_TIMEOUT_SECONDS, stdout_path=transcript)
    return claude_result(transcript)


def run_copilot(workspace: Path, prompt: str, transcript: Path) -> AgentResult:
    run(copilot_command(prompt, transcript.with_suffix(".md")),
        cwd=workspace, timeout=AGENT_TIMEOUT_SECONDS, stdout_path=transcript)
    return copilot_result(transcript)


def run_unsafe_sim(workspace: Path, prompt: str, transcript: Path) -> AgentResult:
    """The simulated misbehaving agent (see unsafe_sim_agent.py). It ignores the prompt."""
    run([sys.executable, str(UNSAFE_SIM_SCRIPT)], cwd=workspace, timeout=60, stdout_path=transcript)
    return copilot_result(transcript)


AGENTS = {"claude": run_claude, "copilot": run_copilot, "unsafe-sim": run_unsafe_sim}


def claude_result(transcript: Path) -> AgentResult:
    events = _read_jsonl(transcript)
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if init is None or result is None:
        raise AgentError(f"{transcript}: claude transcript has no result or no init event")
    if result.get("is_error") or result.get("subtype") != "success":
        raise AgentError(f"claude ended with {result.get('subtype')}: {result.get('result', '')}")
    return AgentResult(result.get("result", ""), init.get("model", ""))


def copilot_result(transcript: Path) -> AgentResult:
    events = _read_jsonl(transcript)
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result is None:
        raise AgentError(f"{transcript}: copilot transcript has no result event")
    if result.get("exitCode") != 0:
        raise AgentError(f"copilot ended with exit code {result.get('exitCode')}")
    messages = [e["data"] for e in events
                if e.get("type") == "assistant.message" and e.get("data", {}).get("content")]
    if not messages:
        raise AgentError(f"{transcript}: copilot transcript has no assistant message")
    return AgentResult(messages[-1]["content"], messages[-1].get("model", ""))


def _read_jsonl(path: Path) -> list[dict]:
    events = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise AgentError(f"{path}: line {number} is not valid JSON ({error})") from error
    return events
