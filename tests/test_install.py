"""The installer, install.sh: it finds the latest release (the highest tag v*), downloads the method at that
tag and runs its init script. A local git repository stands in for GitHub. Needs uv, which runs the init
script (its dependencies come from uv's cache or PyPI)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
METHOD = ("commons", "hosts", "scripts", "space", "VERSION", "install.sh")

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="the installer runs the init script with uv")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=tester", *args],
                          cwd=cwd, capture_output=True, text=True, check=True).stdout


def release(origin: Path, version: str, tag: bool = True) -> None:
    (origin / "VERSION").write_text(version + "\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", f"Method {version}")
    if tag:
        git(origin, "tag", f"v{version}")


def fake_github(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    origin.mkdir()
    for part in METHOD:
        src = REPO / part
        if src.is_dir():
            shutil.copytree(src, origin / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, origin / part)
    git(origin, "init", "-q", "-b", "master")
    return origin


def install(tmp_path: Path, origin: Path, ws: Path, version: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PHYSICS_HIVE_REPO": str(origin), "PHYSICS_HIVE_NO_WARMUP": "1"}
    env.pop("PHYSICS_HIVE_VERSION", None)
    if version:
        env["PHYSICS_HIVE_VERSION"] = version
    return subprocess.run(["sh", str(REPO / "install.sh"), "--mode", "local", "--harness", "claude", "--dir", str(ws),
                           "--question", "Is it?", "--goal", "Say whether it is.", "--yes"],
                          cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)


def test_installs_the_latest_release_or_a_branch(tmp_path):
    origin = fake_github(tmp_path)
    release(origin, "0.9.0")
    release(origin, "0.10.0")
    release(origin, "0.11.0-dev", tag=False)  # master is ahead of the latest release

    r = install(tmp_path, origin, tmp_path / "ws")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "PhysicsHive v0.10.0" in r.stdout  # version order, not alphabetical (v0.9.0 > v0.10.0 as text)
    assert (tmp_path / "ws/.physics-hive/VERSION").read_text().strip() == "0.10.0"
    assert 'physics_hive_version = "0.10.0"' in (tmp_path / "ws/project.toml").read_text()
    assert (tmp_path / "ws/project.md").read_text().startswith("# Is it?\n")

    r = install(tmp_path, origin, tmp_path / "ws-dev", version="master")
    assert r.returncode == 0, r.stderr + r.stdout
    assert (tmp_path / "ws-dev/.physics-hive/VERSION").read_text().strip() == "0.11.0-dev"


def test_refuses_when_there_is_no_release(tmp_path):
    origin = fake_github(tmp_path)
    release(origin, "0.5.0", tag=False)
    r = install(tmp_path, origin, tmp_path / "ws")
    assert r.returncode != 0 and "found no release" in r.stderr
    assert not (tmp_path / "ws").exists()


def test_help_names_the_installer(tmp_path):
    origin = fake_github(tmp_path)
    release(origin, "0.9.0")
    env = {**os.environ, "PHYSICS_HIVE_REPO": str(origin)}
    env.pop("PHYSICS_HIVE_VERSION", None)
    r = subprocess.run(["sh", str(REPO / "install.sh"), "--help"], cwd=tmp_path, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Downloaded PhysicsHive v0.9.0." in r.stdout and "usage: install.sh " in r.stdout


def test_reports_an_unreachable_repository(tmp_path):
    env = {**os.environ, "PHYSICS_HIVE_REPO": str(tmp_path / "nowhere")}
    env.pop("PHYSICS_HIVE_VERSION", None)
    r = subprocess.run(["sh", str(REPO / "install.sh"), "--mode", "local", "--yes"], cwd=tmp_path, env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert r.returncode != 0 and "could not list the releases" in r.stderr
