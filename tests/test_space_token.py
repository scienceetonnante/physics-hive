"""The token a new Space holds: PHYSICS_INTERN_SPACE_TOKEN when it is set, else the creator's login token."""

from __future__ import annotations

import sys

import httpx
import pytest
from huggingface_hub.utils import HfHubHTTPError

import hub
import init
from common import ScriptError

LOGIN, SPACE = "hf_login", "hf_space"
REPOS = {"workspace": "lab/x", "space": "lab/x-space"}


def refused(status: int) -> HfHubHTTPError:
    request = httpx.Request("GET", "https://huggingface.co/api")
    return HfHubHTTPError(f"{status} refused", response=httpx.Response(status, request=request))


class FakeHub:
    """Records what deploy_space sends; `valid` and `readable` are the tokens the Hub accepts."""

    calls: list = []
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

    def create_repo(self, *args, **kwargs):
        pass

    def upload_folder(self, **kwargs):
        pass

    def add_space_variable(self, *args):
        pass

    def add_space_secret(self, repo_id, key, value, description=None):
        FakeHub.calls.append((repo_id, key, value))


@pytest.fixture
def fake_hub(monkeypatch, tmp_path):
    FakeHub.calls = []
    FakeHub.valid = {LOGIN, SPACE}
    FakeHub.readable = {LOGIN, SPACE}
    monkeypatch.setattr(hub, "HfApi", FakeHub)
    monkeypatch.setattr(hub, "api", lambda: FakeHub())
    monkeypatch.setattr(hub, "get_token", lambda: LOGIN)
    monkeypatch.delenv(hub.SPACE_TOKEN_ENV, raising=False)
    app = tmp_path / ".physics-intern" / "space"
    app.mkdir(parents=True)
    (app / "app.py").write_text("")
    return tmp_path


def test_the_space_gets_the_token_of_the_environment_variable(fake_hub, monkeypatch, capsys):
    monkeypatch.setenv(hub.SPACE_TOKEN_ENV, SPACE)
    hub.deploy_space(fake_hub, REPOS, hub.space_secret("env"))
    assert FakeHub.calls == [("lab/x-space", "HF_TOKEN", SPACE)]
    out = capsys.readouterr()
    assert "'space-writer' of bot" in out.out and SPACE not in out.out + out.err
    assert "warning" not in out.err


def test_without_the_variable_the_space_gets_the_login_token(fake_hub):
    hub.deploy_space(fake_hub, REPOS, hub.space_secret("mine"))
    assert FakeHub.calls == [("lab/x-space", "HF_TOKEN", LOGIN)]


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
    assert FakeHub.calls == [("lab/x-space", "HF_TOKEN", SPACE)]
    assert "cannot read lab/x" in capsys.readouterr().err


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
    dotenv.write_text('OTHER=1\nPHYSICS_INTERN_SPACE_TOKEN = "hf_from_file"\n')
    monkeypatch.setattr(init, "DOTENV", dotenv)
    workspace = tmp_path / "ws"
    monkeypatch.setattr(sys, "argv", ["init.py", "--mode", "create", "--org", "lab", "--name", "x",
                                      "--harness", "claude", "--dir", str(workspace), "--yes"])
    assert init.main() == 0
    assert seen["choice"] == "env"
    assert init.os.environ[hub.SPACE_TOKEN_ENV] == "hf_from_file"
