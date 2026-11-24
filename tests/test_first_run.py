"""What a new user sees from init.py: the questions in the terminal, the final message, --help, and the errors
for a folder that is not empty or options that are missing. The terminal is simulated by replacing input()."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import init  # noqa: E402
from common import ScriptError  # noqa: E402


def run_init(monkeypatch, capsys, argv: list[str], answers: list[str] | None = None) -> str:
    """Run init.main() in the current folder; with `answers`, as if typed in a terminal. Returns what it printed."""
    monkeypatch.setenv("PHYSICS_HIVE_NO_WARMUP", "1")
    monkeypatch.setattr(sys, "argv", ["init.py", *argv])
    if answers is not None:
        replies = iter(answers)

        def typed(prompt: str = "") -> str:
            print(prompt)
            return next(replies)

        monkeypatch.setattr(init, "interactive", lambda: True)
        monkeypatch.setattr("builtins.input", typed)
    assert init.main() == 0
    return capsys.readouterr().out


def test_interactive_local_workspace(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "thesis.pdf").write_text("")
    # Local mode, the default harnesses, a folder that is not empty and then a new one, the question, no goal.
    out = run_init(monkeypatch, capsys, [], ["3", "", "full", "ws", "What is X?", ""])
    ws = tmp_path / "ws"
    # The folder is checked, and asked again, before the question and the goal are asked.
    assert "full is not empty (thesis.pdf)" in out
    assert out.index("is not empty") < out.index("The question of the project")
    assert (ws / "project.md").read_text().startswith("# What is X?\n")
    # The final message: what is missing, where to launch the harness, how to run a session and read its result.
    assert "Write the goal under Goal in project.md" in out.replace("\n     ", " ")
    assert "cd ws\n" in out and "/session-run" in out
    assert "uv run .physics-hive/scripts/serve.py" in out
    assert "docs/harness-setup.md" in out

    # Run again in the workspace with a mode: nothing is created, the harness files are rendered again.
    out = run_init(monkeypatch, capsys, ["--mode", "local", "--dir", "ws", "--yes"])
    assert "is already a PhysicsHive workspace; nothing new was created" in out
    assert "Rendered the harness files" in out


def test_says_when_a_harness_is_not_installed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    which = init.shutil.which
    monkeypatch.setattr(init.shutil, "which", lambda cmd: None if cmd == "pi" else which(cmd))
    out = run_init(monkeypatch, capsys, ["--mode", "local", "--harness", "pi", "--question", "Q?", "--goal", "G.",
                                         "--yes"])
    assert "Launch a harness in this folder" in out and "Pi is not installed on this machine yet" in out
    assert "Write the" not in out  # the question and the goal are written


def test_refuses_a_folder_that_is_not_empty_before_anything_else(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("")
    monkeypatch.setattr(sys, "argv", ["init.py", "--mode", "create", "--org", "lab", "--name", "x", "--yes"])
    with pytest.raises(ScriptError, match="is not empty \\(notes.txt\\).*--dir"):
        init.main()  # before any call to the Hub


def test_create_without_an_owner_names_the_options(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init, "ensure_hub_login", lambda asking: None)
    monkeypatch.setattr(sys, "argv", ["init.py", "--harness", "claude", "--yes"])
    with pytest.raises(ScriptError, match="create needs --org and --name.*--mode local"):
        init.main()


def test_help_lists_the_modes_and_the_options():
    env = {**os.environ, "PHYSICS_HIVE_PROG": "install.sh"}
    r = subprocess.run([sys.executable, str(REPO / "scripts/init.py"), "--help"], capture_output=True, text=True,
                       env=env)
    assert r.returncode == 0
    assert r.stdout.startswith("usage: install.sh ")
    for word in ("create", "join", "local", "--harness", "--dir", "--org", "--name", "--repo", "--question", "--goal",
                 "--space-token", "--yes", "--upgrade", "examples:"):
        assert word in r.stdout, word
    assert "--chat-model" not in r.stdout  # for the Space's assistant, which does not exist yet
