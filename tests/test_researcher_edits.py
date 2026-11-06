"""The researcher's edits reach main on the Hub through `session.py` (save, and start), not through the agent.
Also: the git side of starting and abandoning a session never writes the repository's config.

A bare local repository stands in for the workspace repository on the Hub; `hub.git_env` (the Hub token) is
replaced by an empty environment.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import hub
import session
from common import ScriptError

TEMPLATE = "# <the question in one line>\n\n## Goal\n\n## Next steps\n"
GOAL = "# What is X?\n\n## Goal\n\nFind the leading correction to X.\n\n## Next steps\n"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def clone(origin: Path, path: Path) -> Path:
    git(origin.parent, "clone", "-q", str(origin), str(path))
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "tester")
    return path


@pytest.fixture
def hub_repo(tmp_path, monkeypatch):
    """A bare 'Hub' repository whose main has project.md (template), conventions.md and code.py; a clone of it."""
    monkeypatch.setattr(hub, "git_env", lambda: {})
    origin = tmp_path / "hub.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = clone(origin, tmp_path / "seed")
    git(seed, "checkout", "-q", "-b", "main")
    (seed / "project.md").write_text(TEMPLATE)
    (seed / "conventions.md").write_text("Units: c = 1.\n")
    (seed / "code.py").write_text("x = 1\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "initial")
    git(seed, "push", "-q", "origin", "main")
    return origin, clone(origin, tmp_path / "a")


def hub_main(origin: Path, path: str) -> str:
    return git(origin, "show", f"main:{path}")


def test_a_dictated_goal_is_committed_as_the_researchers_and_pushed(hub_repo):
    origin, a = hub_repo
    (a / "project.md").write_text(GOAL)
    assert session.commit_researcher_edits(a, "before a session") == ["project.md"]
    assert git(a, "log", "-1", "--format=%s") == "Researcher's edits (before a session)"
    assert hub.push_researcher_edits(a, session.researcher_path) == ["project.md"]
    assert hub_main(origin, "project.md") == GOAL.strip()
    assert session.project_is_template(a, "origin/main") is False
    assert hub.push_researcher_edits(a, session.researcher_path) == []  # nothing left to push


def test_edits_are_rebased_on_a_change_made_meanwhile_on_the_hub(hub_repo, tmp_path):
    origin, a = hub_repo
    space = clone(origin, tmp_path / "space")  # stands for an edit saved in the Space
    (space / "conventions.md").write_text("Units: c = hbar = 1.\n")
    git(space, "commit", "-qam", "Edit conventions in the Space")
    git(space, "push", "-q", "origin", "main")

    (a / "project.md").write_text(GOAL)
    session.commit_researcher_edits(a, "before a session")
    assert hub.push_researcher_edits(a, session.researcher_path) == ["project.md"]
    assert hub_main(origin, "project.md") == GOAL.strip()
    assert hub_main(origin, "conventions.md") == "Units: c = hbar = 1."


def test_a_conflict_pushes_nothing_and_leaves_the_checkout_unchanged(hub_repo, tmp_path):
    origin, a = hub_repo
    space = clone(origin, tmp_path / "space")
    (space / "project.md").write_text(GOAL.replace("What is X?", "What is Y?"))
    git(space, "commit", "-qam", "Write the question in the Space")
    git(space, "push", "-q", "origin", "main")
    on_hub = git(origin, "rev-parse", "main")

    (a / "project.md").write_text(GOAL)
    session.commit_researcher_edits(a, "before a session")
    head = git(a, "rev-parse", "HEAD")
    with pytest.raises(ScriptError, match="conflict with changes made on the Hub"):
        hub.push_researcher_edits(a, session.researcher_path)
    assert git(origin, "rev-parse", "main") == on_hub
    assert git(a, "rev-parse", "HEAD") == head
    assert git(a, "status", "--porcelain") == ""


def test_commits_to_other_files_on_main_are_not_pushed(hub_repo):
    origin, a = hub_repo
    (a / "code.py").write_text("x = 2\n")
    git(a, "commit", "-qam", "change code on main")
    with pytest.raises(ScriptError, match=r"other than the researcher's \(code\.py\)"):
        hub.push_researcher_edits(a, session.researcher_path)
    assert hub_main(origin, "code.py") == "x = 1"


def test_uncommitted_changes_to_other_files_are_refused(hub_repo):
    _, a = hub_repo
    (a / "project.md").write_text(GOAL)
    (a / "code.py").write_text("x = 2\n")
    with pytest.raises(ScriptError, match="uncommitted changes \\(code.py\\)"):
        session.commit_researcher_edits(a, "before a session")


def test_a_checkout_behind_main_has_nothing_to_push(hub_repo, tmp_path):
    origin, a = hub_repo
    space = clone(origin, tmp_path / "space")
    (space / "project.md").write_text(GOAL)
    git(space, "commit", "-qam", "Write the question in the Space")
    git(space, "push", "-q", "origin", "main")
    assert hub.push_researcher_edits(a, session.researcher_path) == []
    # The local project.md is still the template, but the session starts from main on the Hub.
    assert session.project_is_template(a) is True
    assert session.project_is_template(a, "origin/main") is False


class FakeApi:
    """The Hub calls of opening and abandoning a session; the session's pull request is number 1."""

    def create_pull_request(self, repo_id, **kwargs):
        return SimpleNamespace(num=1)

    def rename_discussion(self, *args, **kwargs):
        pass

    def change_discussion_status(self, *args, **kwargs):
        pass


def test_starting_and_abandoning_a_session_never_writes_the_git_config(hub_repo, monkeypatch):
    # Claude Code's sandbox refuses writes to .git/config, so the session commands must not need any.
    _, a = hub_repo
    monkeypatch.setattr(hub, "hub_repos", lambda ws: {"workspace": "org/physics-hive-x"})
    monkeypatch.setattr(hub, "username", lambda: "tester")
    monkeypatch.setattr(hub, "api", FakeApi)
    monkeypatch.setattr(hub, "update_space_card", lambda repos, question: None)
    config = (a / ".git" / "config").read_bytes()
    info = hub.open_session(None, a, "claude", "model-id")
    assert git(a, "branch", "--show-current") == "session/S1"
    assert (a / ".git" / "config").read_bytes() == config
    hub.abort_session(a, info)
    assert git(a, "branch", "--show-current") == "main"
    assert (a / ".git" / "config").read_bytes() == config
