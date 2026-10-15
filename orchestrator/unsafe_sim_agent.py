"""SIMULATION, not a real coding agent. It misbehaves on purpose so the demo can show guardrail 1.

It does what a careless agent might do on SEC-103: upgrade Guava, then make the failing test
compile by editing the test. Run by `remediate.py --agent unsafe-sim`, in the workspace.
Its output uses the same JSON lines shape as Copilot, so the same transcript reader applies.
"""

# demo-shortcut: a scripted misbehaving agent to show guardrail 1 firing on demand.
# Production: not shipped; the same guardrails run against every real agent.

import json
import sys
from pathlib import Path

MODEL = "unsafe-sim (simulation)"
EDITS = [
    ("pom.xml", "<version>20.0</version>", "<version>33.7.2-jre</version>"),
    ("src/test/java/com/example/tradeintake/TradeAuditLogTest.java",
     "MoreExecutors.sameThreadExecutor()", "MoreExecutors.directExecutor()"),
]


def emit(event_type: str, data: dict) -> None:
    print(json.dumps({"type": event_type, "data": data}), flush=True)


def main() -> None:
    for relative_path, old, new in EDITS:
        path = Path(relative_path)
        text = path.read_text() if path.is_file() else ""
        if old not in text:
            sys.exit(f"unsafe-sim only supports SEC-103: '{old}' not found in {relative_path}")
        path.write_text(text.replace(old, new, 1))
        emit("tool.edit", {"path": relative_path, "old": old, "new": new})
    emit("assistant.message", {"model": MODEL, "content":
         "Upgraded Guava to 33.7.2-jre and changed TradeAuditLogTest to use directExecutor() so it compiles."})
    print(json.dumps({"type": "result", "exitCode": 0}), flush=True)


if __name__ == "__main__":
    main()
