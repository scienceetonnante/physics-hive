"""serve.py, the command that runs the Space on a workspace folder: it finds the workspace and the app to
serve (the workspace's method copy, else the app next to the script), refuses a folder that is not a
workspace, and serves pages until it is interrupted. The server listens on a port from 8821 to 8829."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVE = REPO / "scripts" / "serve.py"
EXAMPLE = REPO / "examples" / "pendulum"


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f"serve_{abs(hash(path))}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def environment() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PHYSICS_HIVE_")}
    return {**env, "PHYSICS_HIVE_NO_WARMUP": "1"}


def serve(*args, cwd: Path, **kwargs):
    return subprocess.Popen([sys.executable, str(SERVE), *map(str, args)], cwd=cwd, env=environment(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    """A new local workspace, made by init.py."""
    ws = tmp_path_factory.mktemp("serve") / "ws"
    r = subprocess.run([sys.executable, str(REPO / "scripts/init.py"), "--mode", "local", "--harness", "claude",
                        "--dir", str(ws), "--question", "Is it?", "--goal", "Say whether it is.", "--yes"],
                       capture_output=True, text=True, env=environment())
    assert r.returncode == 0, r.stderr + r.stdout
    assert "serve.py" in r.stdout  # the final message says how to open the Space
    return ws


def free_port() -> int:
    for port in range(8821, 8830):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    pytest.skip("no free port from 8821 to 8829")


def test_finds_the_app_in_both_layouts(workspace, tmp_path, monkeypatch):
    # From a clone of the method repository: the workspace's own method copy is served.
    clone = load(SERVE)
    assert clone.app_folder(workspace) == workspace / ".physics-hive" / "space"
    # From inside a workspace: its own copy of serve.py, found from a subfolder.
    inside = load(workspace / ".physics-hive" / "scripts" / "serve.py")
    monkeypatch.chdir(workspace / "sessions")
    assert inside.find_workspace(None) == workspace
    assert inside.app_folder(workspace) == workspace / ".physics-hive" / "space"
    # A workspace without a method copy (a toy one): the app next to the script.
    toy = tmp_path / "toy"
    toy.mkdir()
    (toy / "project.toml").write_text("[hub]\n")
    assert clone.app_folder(toy) == REPO / "space"


def test_the_dependencies_are_those_of_the_space():
    header = re.search(r"dependencies = \[(.*?)\]\n", SERVE.read_text(), re.S).group(1)
    declared = set(re.findall(r'"([^"]+)"', header))
    required = {line.strip() for line in (REPO / "space/requirements.txt").read_text().splitlines()
                if line.strip() and not line.startswith("#")}
    assert declared == required


def test_refuses_a_folder_that_is_not_a_workspace(tmp_path):
    proc = serve("--dir", tmp_path, cwd=tmp_path)
    _, err = proc.communicate(timeout=60)
    assert proc.returncode == 1 and "is not a PhysicsHive workspace" in err and "--dir" in err
    proc = serve(cwd=tmp_path)  # no --dir, and no workspace here or above
    _, err = proc.communicate(timeout=60)
    assert proc.returncode == 1 and "is not in a PhysicsHive workspace" in err


def test_refuses_a_port_in_use(workspace):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        proc = serve("--dir", workspace, "--port", busy.getsockname()[1], cwd=workspace)
        _, err = proc.communicate(timeout=60)
    assert proc.returncode == 1 and "cannot listen on port" in err


@pytest.mark.parametrize("which", ["new", "example"])
def test_serves_the_pages_and_stops_on_ctrl_c(which, workspace, tmp_path):
    httpx = pytest.importorskip("httpx")
    if which == "example":
        if not EXAMPLE.is_dir():
            pytest.skip("examples/pendulum is not in this clone")
        ws = tmp_path / "pendulum"
        shutil.copytree(EXAMPLE, ws, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        ws = workspace
    port = free_port()
    proc = serve("--dir", ws, "--port", port, "--user", "alice", cwd=tmp_path)
    try:
        status, deadline = None, time.time() + 60
        while time.time() < deadline and proc.poll() is None:
            try:
                status = httpx.get(f"http://127.0.0.1:{port}/", timeout=10).status_code
                break
            except httpx.TransportError:
                time.sleep(0.2)
        assert status == 200, proc.stderr.read() if proc.poll() is not None else "no answer"
        assert httpx.get(f"http://127.0.0.1:{port}/project", timeout=10).status_code == 200
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, err
    assert f"http://127.0.0.1:{port}/" in out and "alice" in out and "Stopped." in out
    assert "Traceback" not in err


def test_prefers_its_port_and_takes_another_when_it_is_busy(monkeypatch):
    serve_module = load(SERVE)
    monkeypatch.setattr(serve_module, "PREFERRED_PORT", free_port())
    with serve_module.open_socket(None) as first:
        assert first.getsockname()[1] == serve_module.PREFERRED_PORT
        with serve_module.open_socket(None) as second:
            assert second.getsockname()[1] != serve_module.PREFERRED_PORT


def test_the_help_says_there_is_no_sign_in_and_the_example_is_read_only():
    r = subprocess.run([sys.executable, str(SERVE), "--help"], capture_output=True, text=True, env=environment())
    assert r.returncode == 0
    assert "has no sign-in" in r.stdout and "listens on this machine only" in r.stdout
    assert "--dir examples/pendulum --read-only" in r.stdout


def test_refuses_a_request_for_another_host_name(tmp_path):
    """A page of another site that makes its name point to 127.0.0.1 (DNS rebinding) gets nothing."""
    httpx = pytest.importorskip("httpx")
    if not EXAMPLE.is_dir():
        pytest.skip("examples/pendulum is not in this clone")
    ws = tmp_path / "pendulum"
    shutil.copytree(EXAMPLE, ws, ignore=shutil.ignore_patterns("__pycache__"))
    port = free_port()
    proc = serve("--dir", ws, "--port", port, "--read-only", cwd=tmp_path)
    try:
        status, deadline = None, time.time() + 60
        while time.time() < deadline and proc.poll() is None:
            try:
                status = httpx.get(f"http://127.0.0.1:{port}/", timeout=10).status_code
                break
            except httpx.TransportError:
                time.sleep(0.2)
        assert status == 200, proc.stderr.read() if proc.poll() is not None else "no answer"
        assert httpx.get(f"http://localhost:{port}/help", timeout=10).status_code == 200
        r = httpx.get(f"http://127.0.0.1:{port}/", headers={"host": f"attacker.example:{port}"}, timeout=10)
        assert r.status_code == 400
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
