"""Creates the isolated workspace the agent works in.

The workspace is a copy of the service outside this repository, so the agent never sees
the orchestrator code or the builder instructions in CLAUDE.md. It has its own git
history, so every change the agent makes shows up in a diff.
"""

import shutil
from pathlib import Path

from commands import run

WORKSPACES_ROOT = Path("/tmp/remediation-workspaces")

# Workspace commits are made by the orchestrator, not by whoever runs it.
GIT_USER_NAME = "Remediation Orchestrator"
GIT_USER_EMAIL = "remediation-orchestrator@example.invalid"


class WorkspaceError(RuntimeError):
    pass


def create_workspace(service_dir: Path, workspace: Path, repo_root: Path) -> Path:
    service_dir, workspace, repo_root = service_dir.resolve(), workspace.resolve(), repo_root.resolve()
    if workspace.is_relative_to(repo_root):
        raise WorkspaceError(f"workspace {workspace} must be outside the repository {repo_root}")
    if not (service_dir / "pom.xml").is_file():
        raise WorkspaceError(f"{service_dir} has no pom.xml")
    if workspace.exists():
        raise WorkspaceError(f"workspace {workspace} already exists")

    # Only the top level target/ is Maven build output; a source folder may also be called target.
    shutil.copytree(service_dir, workspace,
                    ignore=lambda folder, names: ["target"] if Path(folder) == service_dir else [])
    return workspace


def init_git(workspace: Path, ticket_id: str) -> str:
    """Commits the baseline on main and switches to the fix branch. Returns the branch name."""
    branch = f"fix/{ticket_id}"
    for args in (
        ["git", "init", "--quiet"],
        # Name the branch directly: older git versions have no "init -b".
        ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
        ["git", "config", "user.name", GIT_USER_NAME],
        ["git", "config", "user.email", GIT_USER_EMAIL],
        ["git", "config", "commit.gpgsign", "false"],
        ["git", "add", "--all"],
        ["git", "commit", "--quiet", "-m", f"{ticket_id}: baseline before remediation"],
        ["git", "checkout", "--quiet", "-b", branch],
    ):
        run(args, cwd=workspace)
    return branch
