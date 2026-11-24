"""The public demonstration Space (examples/deploy_demo.py): the folder it builds, the app running from that
folder as the Dockerfile runs it (read-only, on the bundled example), and the upload, with a fake Hub client.
Nothing calls the network. The app listens on a port from 8807 to 8809, and stops with the tests."""

from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "pendulum"


def load_deploy():
    spec = importlib.util.spec_from_file_location("deploy_demo", REPO / "examples" / "deploy_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy = load_deploy()


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    return deploy.build(tmp_path_factory.mktemp("demo") / "space-repo")


def files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_the_folder_holds_the_app_the_method_modules_and_the_example(built):
    names = files(built)
    # The whole example, and nothing else under pendulum/.
    assert {n.removeprefix("pendulum/") for n in names if n.startswith("pendulum/")} == files(EXAMPLE) - {
        n for n in files(EXAMPLE) if any(part.startswith(".") or part == "__pycache__" for part in n.split("/"))}
    assert "pendulum/sessions/S1/note.pdf" in names and "pendulum/project.toml" in names
    # Exactly the modules the app imports for a workspace without a method copy.
    sys.path.insert(0, str(REPO / "space"))
    import backend

    assert deploy.METHOD_MODULES == backend.METHOD_MODULES
    assert {n for n in names if n.startswith("scripts/")} == {f"scripts/{m}.py" for m in backend.METHOD_MODULES}
    assert {"space/app.py", "space/backend.py", "space/latex.py", "space/latex.css", "space/requirements.txt",
            "space/templates/help.html", "Dockerfile", "README.md"} <= names
    assert "space/README.md" not in names and "space/Dockerfile" not in names  # the workspace Space's card is not used
    # No hidden file (.env, harness folders), no cache.
    assert not [n for n in names if any(part.startswith(".") or part == "__pycache__" for part in n.split("/"))]


def test_the_dockerfile_runs_the_app_read_only_on_the_example(built):
    text = (built / "Dockerfile").read_text()
    assert "ENV PHYSICS_HIVE_LOCAL=/home/user/app/pendulum PHYSICS_HIVE_READONLY=1" in text
    assert "COPY --chown=user space/requirements.txt ." in text and "WORKDIR $HOME/app/space" in text
    assert text.index("COPY --chown=user . .") < text.index("WORKDIR $HOME/app/space") < text.index("CMD [")
    assert '"--port", "7860"' in text and "latexmk" in text
    # The Space on the Hub is reached under its own host name: the host check of serve.py must stay off.
    assert "PHYSICS_HIVE_ALLOWED_HOSTS" not in text


def test_the_card_is_a_public_docker_space_without_sign_in(built):
    _, meta, body = (built / "README.md").read_text().split("---\n", 2)
    meta = yaml.safe_load(meta)
    assert meta["sdk"] == "docker" and meta["app_port"] == 7860 and meta["tags"] == ["physics-hive"]
    assert "hf_oauth" not in meta and meta["title"] == "PhysicsHive demo"
    assert 0 < len(meta["short_description"]) <= 60
    assert meta["colorFrom"] in {"red", "yellow", "green", "blue", "indigo", "purple", "pink", "gray"}
    assert "https://github.com/scienceetonnante/physics-hive" in body and "read-only" in body


def test_a_folder_that_is_not_empty_is_refused(tmp_path):
    (tmp_path / "x").write_text("")
    with pytest.raises(SystemExit, match="not empty"):
        deploy.build(tmp_path)


def free_port() -> int:
    for port in range(8807, 8810):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    pytest.skip("ports 8807 to 8809 are all taken")


@pytest.fixture(scope="module")
def running(built):
    """The app, started from the built folder with the environment the Dockerfile sets (paths of this machine)."""
    pytest.importorskip("uvicorn")
    httpx = pytest.importorskip("httpx")
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PHYSICS_HIVE_")}
    env.update(PHYSICS_HIVE_LOCAL=str(built / "pendulum"), PHYSICS_HIVE_READONLY="1", PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--port", str(port), "--log-level", "warning"],
                            cwd=built / "space", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail("the app stopped: " + proc.stdout.read())
            try:
                httpx.get(url + "/help", timeout=2)
                break
            except httpx.TransportError:
                time.sleep(0.2)
        else:
            pytest.fail("the app did not answer within 20 s")
        yield httpx.Client(base_url=url, timeout=30)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_the_built_app_shows_the_example_read_only(running, built):
    for path in ("/", "/project", "/draft", "/sessions", "/session/S1", "/literature", "/help", "/card/CL-S1-1",
                 "/file/derivations/D-S1-1.tex?rendered=1", "/edit/project.md"):
        r = running.get(path)
        assert r.status_code == 200, path
        assert "This is a read-only demonstration of" in r.text, path
        assert "Load the latest version" not in r.text and str(built) not in r.text, path
    page = running.get("/").text
    assert "The amplitude correction to the pendulum" in page and "Awaiting your response" in page
    assert "An example workspace, <strong>pendulum</strong>" in page
    # The note's PDF is the one in the example, served without a compile.
    r = running.get("/note/S1/pdf")
    assert r.status_code == 200 and r.content == (built / "pendulum/sessions/S1/note.pdf").read_bytes()
    # A save is refused, and the example is unchanged.
    before = (built / "pendulum/sessions/S1/debrief.md").read_text()
    token = page.split('name="csrf" value="', 1)[1].split('"', 1)[0]
    r = running.post("/debrief/S1", data={"answer-1": "Yes.", "note": "x", "base": before, "csrf": token})
    assert "Nothing was saved: this is a read-only demonstration." in r.text
    assert (built / "pendulum/sessions/S1/debrief.md").read_text() == before


class FakeHub:
    def __init__(self):
        self.calls = []

    def create_repo(self, repo_id, **kwargs):
        self.calls.append(("create_repo", repo_id, kwargs))

    def upload_folder(self, **kwargs):
        self.calls.append(("upload_folder", kwargs["repo_id"], kwargs))


def test_push_creates_a_public_docker_space_and_uploads_the_folder(tmp_path, capsys):
    hf = FakeHub()
    assert deploy.main(["--dir", str(tmp_path / "out"), "--push", "--repo", "me/physics-hive-demo"], hf=hf) == 0
    (create, repo, kwargs), (upload, repo2, up) = hf.calls
    assert create == "create_repo" and repo == "me/physics-hive-demo"
    assert kwargs == {"repo_type": "space", "space_sdk": "docker", "private": False, "exist_ok": True}
    assert upload == "upload_folder" and repo2 == repo and up["repo_type"] == "space"
    assert Path(up["folder_path"]) == (tmp_path / "out").resolve() and "README.md" in files(Path(up["folder_path"]))
    assert "huggingface.co/spaces/me/physics-hive-demo" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        deploy.main(["--push"], hf=hf)  # --push needs --repo
    assert len(hf.calls) == 2


def test_without_push_nothing_is_sent(tmp_path, capsys):
    hf = FakeHub()
    assert deploy.main(["--dir", str(tmp_path / "out")], hf=hf) == 0
    assert hf.calls == [] and "uvicorn app:app" in capsys.readouterr().out


def test_symbolic_links_in_the_example_are_not_bundled(tmp_path, monkeypatch, capsys):
    secret = tmp_path / "secret"
    secret.write_text("HF_TOKEN=hf_secret_value\n")
    example = tmp_path / "pendulum"
    deploy.shutil.copytree(EXAMPLE, example)
    (example / "literature/x.md").symlink_to(secret)
    (example / "linked-folder").symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(deploy, "EXAMPLE", example)
    built = deploy.build(tmp_path / "out")
    assert not (built / "pendulum/literature/x.md").exists() and not (built / "pendulum/linked-folder").exists()
    assert "hf_secret_value" not in "".join(p.read_text(errors="ignore") for p in built.rglob("*") if p.is_file())
    out = capsys.readouterr().out
    assert "Skipped the symbolic link" in out and "x.md" in out and "linked-folder" in out


def test_push_lists_the_workspace_files_it_uploads(tmp_path, capsys):
    deploy.main(["--dir", str(tmp_path / "out"), "--push", "--repo", "me/demo"], hf=FakeHub())
    out = capsys.readouterr().out
    listing = out[out.index("The example workspace to upload"):]
    assert "  sessions/S1/debrief.md" in listing and "  claims/CL-S1-1.md" in listing
