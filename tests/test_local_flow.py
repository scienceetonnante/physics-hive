"""End-to-end test of a local workspace: init, two sessions, a promotion, a refusal.

The scripts are run as a coordinator would run them, with the agents' work
simulated by writing the files they would write.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def run(*args, cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PHYSICS_INTERN_NO_WARMUP": "1"}  # no dependency installs in tests
    return subprocess.run([sys.executable, *map(str, args)], cwd=cwd, capture_output=True, text=True, env=env)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def write(path: Path, meta: dict | None, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"---\n{yaml.safe_dump(meta, sort_keys=False).strip()}\n---\n" if meta is not None else ""
    path.write_text(head + body)


def commit(ws: Path, message: str) -> None:
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", message)


def test_local_workspace_lifecycle(tmp_path):
    ws = tmp_path / "ws"
    r = run(REPO / "scripts/init.py", "--mode", "local", "--harness", "claude,opencode", "--dir", ws, "--yes", cwd=tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    git(ws, "config", "user.email", "t@example.com")
    git(ws, "config", "user.name", "tester")

    # Method copy and project file are committed; harness files and views are not.
    assert (ws / ".physics-intern/scripts/regen.py").is_file()
    assert (ws / ".physics-intern/VERSION").read_text().strip() == (REPO / "VERSION").read_text().strip()
    assert (ws / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    agents_md = (ws / "AGENTS.md").read_text()
    assert "### Claude Code" in agents_md and "### OpenCode" in agents_md and "### Codex CLI" not in agents_md
    tracked = git(ws, "ls-files").split()
    assert "project.toml" in tracked and "literature/seeds.md" in tracked
    assert not [p for p in tracked if p.startswith((".claude/", ".opencode/", "AGENTS.md", "CLAUDE.md", "INDEX.md"))]
    assert git(ws, "status", "--porcelain") == ""
    assert (ws / "INDEX.md").is_file()

    # Adding a harness keeps the others.
    r = run(REPO / "scripts/init.py", "--harness", "codex", "--dir", ws, "--yes", cwd=tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    agents_md = (ws / "AGENTS.md").read_text()
    assert "### Codex CLI" in agents_md and "### Claude Code" in agents_md
    assert (ws / ".codex/agents/deriver.toml").is_file() and (ws / ".claude/agents/deriver.md").is_file()
    assert git(ws, "status", "--porcelain") == ""

    scripts = ws / ".physics-intern/scripts"
    r = run(scripts / "session.py", "start", "--harness", "claude", "--model", "m1", cwd=ws)
    assert r.returncode != 0 and "problem.md is still the empty template" in r.stderr
    assert not (ws / "sessions/S1").exists() and not (ws / ".active-session").exists()

    (ws / "problem.md").write_text("# Problem\n\nFind the leading correction to X.\n")
    commit(ws, "Write the problem")

    # ---- Session 1: a derivation, a confirming review, a promotion.
    r = run(scripts / "session.py", "start", "--harness", "claude", "--model", "m1", cwd=ws)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "Session S1 started" in r.stdout and "problem.md states a question" in r.stdout
    assert "already active" in run(scripts / "session.py", "start", cwd=ws).stderr

    def next_id(*what):
        out = run(scripts / "session.py", "next", *what, cwd=ws)
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    assert next_id("D") == "D-S1-1"
    assert next_id("CL") == "CL-S1-1"
    (ws / "derivations/.briefs/D-S1-1.md").write_text("Target: X. Reserved card: CL-S1-1.\n")
    assert next_id("CL") == "CL-S1-2"  # the reservation in the brief counts

    write(ws / "sessions/S1/brief.md", {"session": "S1", "goal": "Derive X", "budget": 20, "merge": "auto", "starts_from": []}, "## Goal\nDerive X.\n")
    r = run(scripts / "session.py", "brief", cwd=ws)
    assert r.returncode == 0, r.stderr
    assert "[S1] brief: Derive X" in git(ws, "log", "-1", "--format=%s")

    write(ws / "derivations/D-S1-1.summary.md", {"id": "D-S1-1", "kind": "derivation", "supports": ["CL-S1-1"]}, "## Summary\n")
    (ws / "derivations/D-S1-1.tex").write_text("\\documentclass{article}\n")
    card = {"id": "CL-S1-1", "kind": "claim", "statement": "X = \\alpha/2", "depends_on": [],
            "produced_by": {"kind": "agent", "model": "m1", "operator": "tester"}, "session": "S1",
            "supersedes": [], "refutes": [], "answers": []}
    write(ws / "claims/CL-S1-1.md", card, "From D-S1-1.\n")
    commit(ws, "[S1] derive(D-S1-1): X")

    review_path = next_id("review", "D-S1-1")
    assert review_path == "derivations/D-S1-1_R-S1-1.md"
    write(ws / review_path, {"id": "D-S1-1_R-S1-1", "kind": "review", "target": "D-S1-1", "supports": ["CL-S1-1"],
                             "claim": "X", "verdict": "confirmed", "by": {"kind": "agent"}, "session": "S1",
                             "date": "2026-10-05"}, "## Tests\n")
    commit(ws, "[S1] review(D-S1-1_R-S1-1): confirmed")

    r = run(scripts / "promote.py", "CL-S1-1", "--by-agent", "--reason", "one derivation, one review", cwd=ws)
    assert r.returncode == 0, r.stderr
    write(ws / "sessions/S1/report.md", {"session": "S1", "stop_reason": "goal reached", "dispatches": 2},
          "## Found\n- CL-S1-1\n\n## Proposed plan changes\n- Add a computation.\n")
    commit(ws, "[S1] report")
    r = run(scripts / "session.py", "end", cwd=ws)
    assert r.returncode == 0, r.stderr + r.stdout
    assert not (ws / ".active-session").exists()
    index = (ws / "INDEX.md").read_text()
    assert "**CL-S1-1** · established" in index

    # ---- Session 2: the plan-change proposal is waiting; editing an old card is refused.
    r = run(scripts / "session.py", "start", "--harness", "claude", "--model", "m1", cwd=ws)
    assert r.returncode == 0, r.stderr
    assert "Session S2 started" in r.stdout and "from S1: - Add a computation." in r.stdout
    card["statement"] = "X = alpha/3"
    write(ws / "claims/CL-S1-1.md", card, "Edited afterwards.\n")
    write(ws / "sessions/S2/report.md", {"session": "S2", "stop_reason": "no progress", "dispatches": 4}, "## Found\n")
    commit(ws, "[S2] tamper")
    r = run(scripts / "session.py", "end", cwd=ws)
    assert r.returncode != 0
    assert "claims/CL-S1-1.md" in r.stdout and "edited after creation" in r.stdout
    assert (ws / ".active-session").exists()
