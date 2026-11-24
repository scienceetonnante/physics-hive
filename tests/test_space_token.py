"""The Space of a shared space: the token it holds (PHYSICS_HIVE_SPACE_TOKEN when it is set, else the
creator's login token), and its card on the Hub (title and question)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml
from huggingface_hub.errors import EntryNotFoundError
from huggingface_hub.utils import HfHubHTTPError

import hub
import init
from common import ScriptError

LOGIN, SPACE = "hf_login", "hf_space"
REPOS = {"workspace": "lab/physics-hive-x", "space": "lab/physics-hive-x"}
README = Path(__file__).resolve().parents[1] / "space" / "README.md"
PENDULUM = "What is the period of a pendulum to second order in the amplitude?"


def refused(status: int) -> HfHubHTTPError:
    request = httpx.Request("GET", "https://huggingface.co/api")
    return HfHubHTTPError(f"{status} refused", response=httpx.Response(status, request=request))


class FakeHub:
    """Records what deploy_space sends; `valid` and `readable` are the tokens the Hub accepts."""

    calls: list = []
    uploads: list = []  # (path in the repository, text) of each README.md sent
    space_readme = ""
    stamp = None  # the METHOD file of the Space, None while it has none
    valid = {LOGIN, SPACE}
    readable = {LOGIN, SPACE}

    def __init__(self, token=None):
        self.token = token or LOGIN

    def whoami(self):
        if self.token not in self.valid:
            raise refused(401)
        return {"name": "bot", "auth": {"accessToken": {"displayName": "space-writer"}}}

    def repo_info(self, repo_id, repo_type=None):
        if self.token not in self.readable:
            raise refused(404)

    def space_info(self, repo_id):
        return SimpleNamespace(host="https://lab-physics-hive-x.hf.space")

    def create_repo(self, *args, **kwargs):
        pass

    def upload_folder(self, folder_path, **kwargs):
        FakeHub.uploads.append(("README.md", (Path(folder_path) / "README.md").read_text()))
        FakeHub.stamp = (Path(folder_path) / hub.SPACE_STAMP).read_text()

    def hf_hub_download(self, repo_id, filename, repo_type=None):
        if filename == hub.SPACE_STAMP and FakeHub.stamp is None:
            raise EntryNotFoundError(f"{filename} not found")
        path = Path(FakeHub.tmp) / f"downloaded-{filename}"
        path.write_text(FakeHub.stamp if filename == hub.SPACE_STAMP else FakeHub.space_readme)
        return str(path)

    def upload_file(self, path_or_fileobj, path_in_repo, **kwargs):
        FakeHub.uploads.append((path_in_repo, path_or_fileobj.decode()))

    def add_space_variable(self, *args):
        pass

    def add_space_secret(self, repo_id, key, value, description=None):
        FakeHub.calls.append((repo_id, key, value))


@pytest.fixture
def fake_hub(monkeypatch, tmp_path):
    FakeHub.calls, FakeHub.uploads, FakeHub.tmp, FakeHub.stamp = [], [], tmp_path, None
    FakeHub.valid = {LOGIN, SPACE}
    FakeHub.readable = {LOGIN, SPACE}
    monkeypatch.setattr(hub, "HfApi", FakeHub)
    monkeypatch.setattr(hub, "api", lambda: FakeHub())
    monkeypatch.setattr(hub, "get_token", lambda: LOGIN)
    monkeypatch.delenv(hub.SPACE_TOKEN_ENV, raising=False)
    app = tmp_path / ".physics-hive" / "space"
    app.mkdir(parents=True)
    (app / "app.py").write_text("")
    (app / "README.md").write_text(README.read_text())
    return tmp_path


def test_the_space_gets_the_token_of_the_environment_variable(fake_hub, monkeypatch, capsys):
    monkeypatch.setenv(hub.SPACE_TOKEN_ENV, SPACE)
    hub.deploy_space(fake_hub, REPOS, hub.space_secret("env"))
    assert FakeHub.calls == [("lab/physics-hive-x", "HF_TOKEN", SPACE)]
    out = capsys.readouterr()
    assert "'space-writer' of bot" in out.out and SPACE not in out.out + out.err
    assert "warning" not in out.err


def test_without_the_variable_the_space_gets_the_login_token(fake_hub):
    hub.deploy_space(fake_hub, REPOS, hub.space_secret("mine"))
    assert FakeHub.calls == [("lab/physics-hive-x", "HF_TOKEN", LOGIN)]


def test_none_leaves_the_secret_unset(fake_hub):
    hub.deploy_space(fake_hub, REPOS, hub.space_secret("none"))
    assert FakeHub.calls == []


def test_an_invalid_token_stops_before_anything_is_created(fake_hub, monkeypatch):
    monkeypatch.setenv(hub.SPACE_TOKEN_ENV, "hf_revoked")
    with pytest.raises(ScriptError, match="refused the token"):
        hub.space_secret("env")


def test_a_token_that_cannot_read_the_workspace_is_reported(fake_hub, monkeypatch, capsys):
    monkeypatch.setenv(hub.SPACE_TOKEN_ENV, SPACE)
    FakeHub.readable = {LOGIN}
    hub.deploy_space(fake_hub, REPOS, hub.space_secret("env"))
    assert FakeHub.calls == [("lab/physics-hive-x", "HF_TOKEN", SPACE)]
    assert "cannot read lab/physics-hive-x" in capsys.readouterr().err


def test_the_repositories_are_named_after_the_project():
    assert hub.repo_names("lab", "x") == {
        "workspace": "lab/physics-hive-x", "traces": "lab/physics-hive-x-traces",
        "sources": "lab/physics-hive-x-sources", "chat_debug": "lab/physics-hive-x-chat-debug",
        "space": "lab/physics-hive-x"}
    assert hub.repo_names("lab", "physics-hive-x") == hub.repo_names("lab", "x")
    assert hub.project_name("lab/physics-hive-x") == "x" and hub.project_name("lab/old-name") == "old-name"


def test_your_own_account_can_own_a_project(monkeypatch):
    monkeypatch.setattr(hub, "whoami", lambda: {"name": "dlouapre", "orgs": [{"name": "lab-b"}, {"name": "lab-a"}]})
    assert hub.owners() == ["lab-a", "lab-b", "dlouapre"]
    monkeypatch.setattr(hub, "whoami", lambda: {"name": "dlouapre"})
    assert hub.owners() == ["dlouapre"]


def card(readme: str) -> dict:
    return yaml.safe_load(readme.split("---\n")[1])


def test_the_card_names_the_project_and_shows_its_question(fake_hub):
    hub.deploy_space(fake_hub, REPOS, None)  # project.md not written yet: no description
    [(_, readme)] = FakeHub.uploads
    meta = card(readme)
    assert meta["title"] == "[PhysicsHive] x" and "short_description" not in meta
    assert meta["sdk"] == "docker" and meta["hf_oauth"] is True and "# PhysicsHive Space" in readme

    (fake_hub / "project.md").write_text(f"# {PENDULUM}\n\n## Goal\n\nFind T.\n")
    FakeHub.uploads = []
    hub.deploy_space(fake_hub, REPOS, None)
    [(_, readme)] = FakeHub.uploads
    description = card(readme)["short_description"]
    assert len(description) <= hub.CARD_DESCRIPTION_LIMIT and description.endswith("…")
    assert PENDULUM.startswith(description[:-1]) and PENDULUM[len(description) - 1] == " "  # cut between words
    assert hub.card_line("Short question?") == "Short question?"


def test_a_session_start_updates_the_card_only_when_the_question_changed(fake_hub):
    FakeHub.space_readme = README.read_text()
    hub.update_space_card(REPOS, None)  # no question yet: nothing to show
    assert FakeHub.uploads == []
    hub.update_space_card(REPOS, "Is X finite?")
    [(path, readme)] = FakeHub.uploads
    assert path == "README.md" and card(readme)["short_description"] == "Is X finite?"
    FakeHub.space_readme = readme
    hub.update_space_card(REPOS, "Is X finite?")
    assert len(FakeHub.uploads) == 1


def test_a_session_start_gives_the_space_the_app_of_the_method_copy(fake_hub, capsys):
    (fake_hub / ".physics-hive" / "VERSION").write_text("0.5.4\n")
    hub.sync_space(fake_hub, REPOS)  # a Space deployed before stamps existed gets the app once
    assert len(FakeHub.uploads) == 1 and FakeHub.stamp.startswith("0.5.4 ")
    assert "now runs the app of method 0.5.4" in capsys.readouterr().out
    hub.sync_space(fake_hub, REPOS)  # the same app: nothing to do
    assert len(FakeHub.uploads) == 1
    (fake_hub / ".physics-hive" / "space" / "app.py").write_text("# changed\n")
    (fake_hub / ".physics-hive" / "space" / "__pycache__").mkdir()
    (fake_hub / ".physics-hive" / "space" / "__pycache__" / "app.pyc").write_bytes(b"x")  # not part of the app
    hub.sync_space(fake_hub, REPOS)
    assert len(FakeHub.uploads) == 2 and FakeHub.stamp.strip() == hub.space_app_stamp(fake_hub / ".physics-hive" / "space")
    hub.deploy_space(fake_hub, REPOS, None)  # a new Space is deployed with its stamp
    hub.sync_space(fake_hub, REPOS)
    assert len(FakeHub.uploads) == 3


@pytest.mark.parametrize("env, flag, expected", [
    (SPACE, None, "env"),
    (None, None, "mine"),
    (SPACE, "mine", "mine"),
    (SPACE, "none", "none"),
])
def test_init_uses_the_variable_by_default(monkeypatch, tmp_path, env, flag, expected):
    seen = {}
    monkeypatch.setattr(hub, "create_shared", lambda *args, **kwargs: seen.setdefault("choice", args[5]))
    monkeypatch.setattr(init, "DOTENV", tmp_path / "absent.env")
    if env:
        monkeypatch.setenv(hub.SPACE_TOKEN_ENV, env)
    else:
        monkeypatch.delenv(hub.SPACE_TOKEN_ENV, raising=False)
    argv = ["init.py", "--mode", "create", "--org", "lab", "--name", "x", "--harness", "claude",
            "--dir", str(tmp_path), "--yes"] + (["--space-token", flag] if flag else [])
    monkeypatch.setattr(sys, "argv", argv)
    assert init.main() == 0
    assert seen["choice"] == expected


def test_init_reads_the_token_from_the_dotenv_of_the_method_repository(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(hub, "create_shared", lambda *args, **kwargs: seen.setdefault("choice", args[5]))
    monkeypatch.delenv(hub.SPACE_TOKEN_ENV, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text('OTHER=1\nPHYSICS_HIVE_SPACE_TOKEN = "hf_from_file"\n')
    monkeypatch.setattr(init, "DOTENV", dotenv)
    workspace = tmp_path / "ws"
    monkeypatch.setattr(sys, "argv", ["init.py", "--mode", "create", "--org", "lab", "--name", "x",
                                      "--harness", "claude", "--dir", str(workspace), "--yes"])
    assert init.main() == 0
    assert seen["choice"] == "env"
    assert init.os.environ[hub.SPACE_TOKEN_ENV] == "hf_from_file"
