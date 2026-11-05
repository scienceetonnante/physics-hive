"""End-to-end test of a local workspace: init, then three sessions in which the researcher acts only by
editing debriefs and project.md in a text editor (the acceptance test of phase A of the design).

The scripts are run as a coordinator would run them; the agents' work is simulated by writing the files
they would write. Each decision is applied by the session after it; a result copied into the draft shows as
established in INDEX.md; a result without a confirming review is refused by check.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from human import parse_debrief, set_answer, set_note, set_ticks  # noqa: E402


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


def card(ws: Path, card_id: str, statement: str, session: str) -> None:
    write(ws / f"claims/{card_id}.md", {"id": card_id, "kind": "claim", "statement": statement, "depends_on": [],
                                        "produced_by": {"kind": "agent", "model": "m1", "operator": "tester"},
                                        "session": session, "supersedes": [], "refutes": []}, "Body.\n")


RESULT = "\\begin{{{kind}}}[{title}]\n{text}\\card{{{card}}}\n\\end{{{kind}}}\n"


def debrief(session: str, questions: list[str], ticks: list[str]) -> str:
    out = ["Summary of the session, in a few sentences.", "", f"Read the full note: `sessions/{session}/note.tex`.", ""]
    for i, q in enumerate(questions, 1):
        out += [f"**Question {i}.** {q}", "", "> **Answer:**", ""]
    out += ["**Tick what you accept.** The next session applies the ticked lines.", ""]
    out += [f"- [ ] {t}" for t in ticks]
    out += ["", "#### Anything else for the next session", "", "> **Note:**", ""]
    return "\n".join(out)


def end_session(ws: Path, scripts: Path, session: str, note: str, deb: str) -> subprocess.CompletedProcess:
    (ws / f"sessions/{session}/note.tex").write_text(note)
    (ws / f"sessions/{session}/debrief.md").write_text(deb)
    with open(ws / f"sessions/{session}/log.md", "a") as log:
        log.write(f"\n## Handoff\n\nOpen thread from {session}.\n")
    commit(ws, f"[{session}] note, debrief and handoff")
    return run(scripts / "session.py", "end", cwd=ws)


def test_three_local_sessions_driven_by_debriefs(tmp_path):
    ws = tmp_path / "ws"
    r = run(REPO / "scripts/init.py", "--mode", "local", "--harness", "claude,opencode", "--dir", ws, "--yes", cwd=tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    git(ws, "config", "user.email", "t@example.com")
    git(ws, "config", "user.name", "tester")

    # Method copy and project files are committed; harness files and generated files are not.
    assert (ws / ".physics-intern/scripts/regen.py").is_file()
    assert (ws / ".physics-intern/VERSION").read_text().strip() == (REPO / "VERSION").read_text().strip()
    assert (ws / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    agents_md = (ws / "AGENTS.md").read_text()
    assert "### Claude Code" in agents_md and "### OpenCode" in agents_md and "### Codex CLI" not in agents_md
    tracked = git(ws, "ls-files").split()
    assert {"project.toml", "project.md", "conventions.md", "draft.tex", "literature/seeds.md"} <= set(tracked)
    assert not [p for p in tracked if p.startswith((".claude/", ".opencode/", "AGENTS.md", "CLAUDE.md", "INDEX.md",
                                                     "references.bib"))]
    assert git(ws, "status", "--porcelain") == ""

    # Adding a harness keeps the others.
    r = run(REPO / "scripts/init.py", "--harness", "codex", "--dir", ws, "--yes", cwd=tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "### Codex CLI" in (ws / "AGENTS.md").read_text() and (ws / ".claude/agents/writer.md").is_file()
    assert git(ws, "status", "--porcelain") == ""

    scripts = ws / ".physics-intern/scripts"
    r = run(scripts / "session.py", "start", "--harness", "claude", "--model", "m1", cwd=ws)
    assert r.returncode != 0 and "project.md has no title or goal yet" in r.stderr
    assert not (ws / "sessions/S1").exists() and not (ws / ".active-session").exists()

    # The researcher writes the title and the goal in an editor, and does not commit.
    project = (ws / "project.md").read_text().replace("# <the question in one line>", "# What is X?")
    (ws / "project.md").write_text(project.replace("## Goal\n", "## Goal\n\nFind the leading correction to X.\n"))

    # ---- Session 1: a reviewed claim and an unreviewed one; a debrief with a question and three tick lines.
    r = run(scripts / "session.py", "start", "--harness", "claude", "--model", "m1", cwd=ws)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "Committed your edits of project.md as yours." in r.stdout
    assert "Session S1 started" in r.stdout and "From you since the project began" in r.stdout
    # The templates committed by init are not the researcher's edits; only the title and the goal are.
    assert "project.md       +3 −1 lines" in r.stdout and "conventions.md   unchanged" in r.stdout
    assert "draft.tex        unchanged" in r.stdout and "Initialize PhysicsIntern" not in r.stdout
    assert "already active" in run(scripts / "session.py", "start", cwd=ws).stderr

    def next_id(*what):
        out = run(scripts / "session.py", "next", *what, cwd=ws)
        assert out.returncode == 0, out.stderr
        return out.stdout.strip()

    assert next_id("D") == "D-S1-1" and next_id("CL") == "CL-S1-1"
    (ws / "derivations/.briefs/D-S1-1.md").write_text("Target: X. Reserved card: CL-S1-1.\n")
    assert next_id("CL") == "CL-S1-2"  # the reservation in the brief counts

    write(ws / "sessions/S1/brief.md", {"session": "S1", "goal": "Derive X", "budget": 20, "starts_from": []}, "## Goal\n")
    r = run(scripts / "session.py", "brief", cwd=ws)
    assert r.returncode == 0, r.stderr
    assert "[S1] brief: Derive X" in git(ws, "log", "-1", "--format=%s")
    assert "sessions/S1/received.md" in git(ws, "ls-files")

    write(ws / "derivations/D-S1-1.summary.md", {"id": "D-S1-1", "kind": "derivation", "supports": ["CL-S1-1"]}, "## Summary\n")
    (ws / "derivations/D-S1-1.tex").write_text("\\documentclass{article}\n")
    card(ws, "CL-S1-1", "X = \\alpha/2", "S1")
    card(ws, "CL-S1-2", "Y vanishes at one loop", "S1")
    commit(ws, "[S1] derive(D-S1-1): X")
    write(ws / next_id("review", "D-S1-1"), {"id": "D-S1-1_R-S1-1", "kind": "review", "target": "D-S1-1",
                                             "supports": ["CL-S1-1"], "claim": "X", "verdict": "confirmed",
                                             "by": {"kind": "agent"}, "session": "S1", "date": "2026-10-05"}, "## Tests\n")
    commit(ws, "[S1] review(D-S1-1_R-S1-1): confirmed")

    r = run(scripts / "session.py", "end", cwd=ws)
    assert r.returncode != 0 and "note.tex and debrief.md" in r.stderr
    note1 = ("\\documentclass{article}\\begin{document}\n"
             + RESULT.format(kind="result", title="X", text="$X=\\alpha/2$.", card="CL-S1-1")
             + RESULT.format(kind="conjecture", title="Y", text="$Y=0$.", card="CL-S1-2") + "\\end{document}\n")
    deb1 = debrief("S1", ["Must the method use walks only?"],
                   ["Copy Result 1 of note S1 (CL-S1-1, one derivation confirmed by a blind review) into the draft, as a result.",
                    "Copy Conjecture 1 of note S1 (CL-S1-2, not reviewed) into the draft, as a result.",
                    "Next step: compute X numerically."])
    r = end_session(ws, scripts, "S1", note1, deb1)
    assert r.returncode == 0, r.stderr + r.stdout
    assert not (ws / ".active-session").exists()
    changed = parse_debrief((ws / "sessions/S1/debrief.md").read_text()).changed
    assert "- `project.md`: unchanged." in changed and "- `draft.tex`: unchanged." in changed
    assert "**S1**" in (ws / "INDEX.md").read_text() and "debrief open" in (ws / "INDEX.md").read_text()

    # ---- The researcher answers S1 in an editor: answer, all three ticks, a note; and adds a step to project.md.
    path = ws / "sessions/S1/debrief.md"
    path.write_text(set_note(set_ticks(set_answer(path.read_text(), 1, "Walks only first."), {0: True, 1: True, 2: True}),
                             "Start on the disk."))
    (ws / "project.md").write_text((ws / "project.md").read_text().replace(
        "## Next steps\n", "## Next steps\n\n1. Derive X to second order.\n"))

    # ---- Session 2: receives all of it, applies the ticks, and check refuses the unreviewed result.
    r = run(scripts / "session.py", "start", "--harness", "claude", "--model", "m1", cwd=ws)
    assert r.returncode == 0, r.stderr + r.stdout
    out = r.stdout
    assert "From you since S1 started" in out and "Debrief S1 (sessions/S1/debrief.md)" in out
    assert "Answer: Walks only first." in out and "Your note: Start on the disk." in out
    assert "✓ Copy Result 1 of note S1" in out and "✓ Next step: compute X numerically." in out
    assert "project.md       +2 −0 lines" in out and "Handoff from S1" in out and "Open thread from S1." in out
    assert "First next step in project.md:\n  Derive X to second order." in out

    draft = (ws / "draft.tex").read_text()
    copy = "% Copied from note S1 by session S2, as ticked in the S1 debrief.\n"
    bad = draft.replace("\\bibliographystyle", copy + RESULT.format(kind="result", title="X", text="X.", card="CL-S1-1")
                        + RESULT.format(kind="result", title="Y", text="Y.", card="CL-S1-2") + "\\bibliographystyle")
    (ws / "draft.tex").write_text(bad)
    r = run(scripts / "check.py", cwd=ws)
    assert r.returncode != 0 and "CL-S1-2 has no supporting artefact" in r.stdout and "copy it as a conjecture" in r.stdout
    good = draft.replace("\\bibliographystyle", copy + RESULT.format(kind="result", title="X", text="X.", card="CL-S1-1")
                         + "\\bibliographystyle")
    (ws / "draft.tex").write_text(good)
    (ws / "project.md").write_text((ws / "project.md").read_text().replace(
        "1. Derive X to second order.\n", "1. Derive X to second order.\n2. Compute X numerically.\n"))
    commit(ws, "[S2] apply the lines ticked in the S1 debrief")
    assert run(scripts / "check.py", cwd=ws).returncode == 0

    write(ws / "sessions/S2/brief.md", {"session": "S2", "goal": "Derive X to second order", "budget": 20}, "## Goal\n")
    assert run(scripts / "session.py", "brief", cwd=ws).returncode == 0
    (ws / "project.md").write_text((ws / "project.md").read_text().replace(
        "1. Derive X to second order.\n2. Compute X numerically.\n", "1. Compute X numerically.\n"))
    commit(ws, "[S2] project.md: remove the finished step")
    deb2 = debrief("S2", ["Is the disk a fair first domain?"],
                   ["Copy Conjecture 1 of note S1 (CL-S1-2) into the draft, as a conjecture."])
    r = end_session(ws, scripts, "S2", "\\documentclass{article}\\begin{document}Nothing new.\\end{document}\n", deb2)
    assert r.returncode == 0, r.stderr + r.stdout
    changed = parse_debrief((ws / "sessions/S2/debrief.md").read_text()).changed
    assert "- `draft.tex` (+" in changed and "as you ticked in S1" in changed
    assert "- `project.md` (+" in changed and "project.md: remove the finished step" in changed
    index = (ws / "INDEX.md").read_text()
    assert "**CL-S1-1** · established" in index and "**CL-S1-2** · working" in index
    assert "debrief read by S2" in index

    # ---- The researcher ticks the S2 line but leaves its question; S3 asks it, and records the answer as theirs.
    path = ws / "sessions/S2/debrief.md"
    path.write_text(set_ticks(path.read_text(), {0: True}))
    r = run(scripts / "session.py", "start", "--harness", "claude", "--model", "m1", cwd=ws)
    assert r.returncode == 0, r.stderr + r.stdout
    out = r.stdout
    assert "Debrief S2" in out and "✓ Copy Conjecture 1 of note S1" in out
    assert "Debrief S1" not in out  # nothing new in S1: its ticks are not applied twice
    assert "S2 question 1: Is the disk a fair first domain?" in out
    r = run(scripts / "session.py", "answer", "S2", "1", "Yes,", "for", "now.", cwd=ws)
    assert r.returncode == 0, r.stderr
    assert parse_debrief(path.read_text()).questions[0].answer == "Yes, for now."
    assert git(ws, "log", "-1", "--format=%s").startswith("Researcher's answer to question 1 of the S2 debrief")
    received = yaml.safe_load((ws / "sessions/S3/received.md").read_text().split("---")[1])
    assert received["debriefs"]["S2"]["answers"] == {1: "Yes, for now."}

    (ws / "draft.tex").write_text((ws / "draft.tex").read_text().replace(
        "\\bibliographystyle", RESULT.format(kind="conjecture", title="Y", text="Y.", card="CL-S1-2") + "\\bibliographystyle"))
    commit(ws, "[S3] apply the lines ticked in the S2 debrief")
    write(ws / "sessions/S3/brief.md", {"session": "S3", "goal": "Compute X numerically", "budget": 5}, "## Goal\n")
    assert run(scripts / "session.py", "brief", cwd=ws).returncode == 0

    # Editing a card of an earlier session is refused at the end.
    card(ws, "CL-S1-1", "X = alpha/3", "S1")
    r = end_session(ws, scripts, "S3", "\\documentclass{article}\\begin{document}x\\end{document}\n",
                    debrief("S3", [], ["Next step: none."]))
    assert r.returncode != 0
    assert "claims/CL-S1-1.md" in r.stdout and "edited after creation" in r.stdout
    assert (ws / ".active-session").exists()
