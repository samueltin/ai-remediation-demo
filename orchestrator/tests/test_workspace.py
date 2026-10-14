import subprocess

import pytest

from workspace import WorkspaceError, create_workspace, init_git


def make_service(tmp_path):
    repo = tmp_path / "repo"
    service = repo / "svc"
    (service / "src" / "main" / "target").mkdir(parents=True)
    (service / "pom.xml").write_text("<project/>")
    (service / "target" / "classes").mkdir(parents=True)
    (service / "target" / "app.jar").write_text("built jar")
    return repo, service


def git(workspace, *args):
    return subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True, check=True).stdout.strip()


def test_copy_excludes_top_level_target_only(tmp_path):
    repo, service = make_service(tmp_path)

    workspace = create_workspace(service, tmp_path / "ws" / "SEC-1", repo)

    assert (workspace / "pom.xml").is_file()
    assert not (workspace / "target").exists()
    assert (workspace / "src" / "main" / "target").is_dir()


def test_existing_workspace_is_rejected(tmp_path):
    repo, service = make_service(tmp_path)
    (tmp_path / "ws" / "SEC-1").mkdir(parents=True)

    with pytest.raises(WorkspaceError, match="already exists"):
        create_workspace(service, tmp_path / "ws" / "SEC-1", repo)


def test_workspace_inside_repo_is_rejected(tmp_path):
    repo, service = make_service(tmp_path)

    with pytest.raises(WorkspaceError, match="outside the repository"):
        create_workspace(service, repo / "ws" / "SEC-1", repo)


def test_service_without_pom_is_rejected(tmp_path):
    repo, service = make_service(tmp_path)
    (service / "pom.xml").unlink()

    with pytest.raises(WorkspaceError, match="no pom.xml"):
        create_workspace(service, tmp_path / "ws" / "SEC-1", repo)


def test_git_has_committed_baseline_on_fix_branch(tmp_path):
    repo, service = make_service(tmp_path)
    workspace = create_workspace(service, tmp_path / "ws" / "SEC-1", repo)

    init_git(workspace, "SEC-1")

    assert git(workspace, "rev-parse", "--abbrev-ref", "HEAD") == "fix/SEC-1"
    assert git(workspace, "log", "--format=%s") == "SEC-1: baseline before remediation"
    assert git(workspace, "status", "--porcelain") == ""


def test_maven_build_output_is_not_part_of_the_diff(tmp_path):
    repo, service = make_service(tmp_path)
    workspace = create_workspace(service, tmp_path / "ws" / "SEC-1", repo)
    init_git(workspace, "SEC-1")

    (workspace / "target" / "classes").mkdir(parents=True)
    (workspace / "target" / "classes" / "App.class").write_text("bytes")

    assert git(workspace, "status", "--porcelain") == ""
