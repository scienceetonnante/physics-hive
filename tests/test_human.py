"""Tests of the human view: project.md, debriefs, the draft, and what a new session receives."""

from __future__ import annotations

import subprocess

from cards import Workspace
from conftest import DEBRIEF
from human import (
    History,
    changed_by_session,
    debrief_problems,
    format_received,
    parse_debrief,
    parse_draft,
    parse_project,
    received,
    received_record,
    set_answer,
    set_changed,
    set_note,
    set_ticks,
)


def test_project_md():
    template = (__import__("pathlib").Path(__file__).resolve().parents[1] / "commons/templates/project.md").read_text()
    assert parse_project(template).is_template
    project = parse_project("# Can walks find eigenvalues?\n\n## Goal\n\nDecide.\n\n## Next steps\n\n"
                            "1. Reference spectra\n   on three domains.\n2. Weights.\n")
    assert not project.is_template and project.title == "Can walks find eigenvalues?"
    assert project.next_steps == ["Reference spectra on three domains.", "Weights."]


def test_debrief_parse_and_write_back():
    text = DEBRIEF.format(s="S1")
    d = parse_debrief(text)
    assert d.summary.startswith("Summary of what the session found.")
    assert [q.number for q in d.questions] == [1, 2] and all(not q.answer for q in d.questions)
    assert [t.checked for t in d.ticks] == [False, False, False] and d.has_note and d.note == ""
    assert debrief_problems(text) == []

    text = set_answer(text, 1, "Walks only first.\n\nKeep the eigensolver as a fallback.")
    text = set_ticks(text, {0: True, 2: True})
    text = set_note(text, "Start on the disk.")
    d = parse_debrief(text)
    assert d.questions[0].answer == "Walks only first.\n\nKeep the eigensolver as a fallback."
    assert d.questions[1].answer == ""
    assert [t.checked for t in d.ticks] == [True, False, True]
    assert d.note == "Start on the disk."
    # Writing again replaces rather than duplicates.
    text = set_answer(text, 1, "Walks only.")
    text = set_note(text, "Disk first.")
    d = parse_debrief(text)
    assert d.questions[0].answer == "Walks only." and d.note == "Disk first." and text.count("**Note:**") == 1
    text = set_changed(text, "- `project.md`: unchanged.")
    text = set_changed(text, "- `draft.tex` (+3 −0 lines): as you ticked in S1.")
    d = parse_debrief(text)
    assert d.changed == "- `draft.tex` (+3 −0 lines): as you ticked in S1." and text.count("Changed by this") == 1
    assert d.questions[0].answer == "Walks only."


def test_parse_draft():
    tex = ("\\begin{result}[Weights]\nA.\\footnote{x}\\card{CL-S2-1}\n\\end{result}\n"
           "% \\begin{result}\\card{CL-S9-9}\\end{result}\n"
           "\\begin{conjecture}\nB.\\card{CL-S3-1, CL-S3-2}\n\\end{conjecture}\n")
    blocks = parse_draft(tex)
    assert [(b.kind, b.title, b.cards, b.line) for b in blocks] == [
        ("result", "Weights", ["CL-S2-1"], 1), ("conjecture", "", ["CL-S3-1", "CL-S3-2"], 5)]


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def test_received_counts_what_no_session_received(toy):
    toy.git_init()
    toy.debrief("S1", DEBRIEF.format(s="S1"))
    toy.commit("[S1] debrief")
    toy.received("S1", git(toy.root, "rev-parse", "HEAD~1"), "2026-10-01T10:00:00Z", {})

    # The researcher answers S1, ticks two lines, writes a note, and edits project.md.
    path = toy.root / "sessions/S1/debrief.md"
    path.write_text(set_note(set_ticks(set_answer(path.read_text(), 1, "Walks only."), {0: True, 2: True}), "Disk."))
    (toy.root / "project.md").write_text((toy.root / "project.md").read_text() + "2. A second step.\n")
    toy.commit("Edit from the Space")
    ws = Workspace(toy.root)
    news = received(ws, History(toy.root, ws.sessions["S1"].received["base"]))
    [d] = news.debriefs
    assert d.full and d.ticked == ["Set the approach in the project: correlation matrices.",
                                   "Copy Result 1 of note S1 into the draft, as a result."]
    assert d.unticked == ["Next step: check the weights by sampling exit times."]
    assert [(n, a) for n, _, a in d.answers] == [(1, "Walks only."), (2, "")] and d.note == "Disk."
    assert news.unanswered == [("S1", 2, "I assumed Dirichlet walls; no answer means you agree.")]
    assert news.edits == {"project.md": (1, 0)} and news.next_step == "Derive X."
    text = format_received(news)
    assert "Debrief S1 (sessions/S1/debrief.md)" in text and "      Answer: Walks only." in text
    assert "      No answer yet." in text and "✓ Copy Result 1 of note S1" in text and "Your note: Disk." in text
    assert "project.md       +1 −0 lines" in text and "conventions.md   unchanged" in text

    # S2 starts and records what it received; then the researcher answers question 2 and ticks one more line.
    base2 = toy.commit("[S2] apply the lines ticked in the S1 debrief")
    toy.received("S2", base2, "2026-10-02T10:00:00Z", received_record(news))
    path.write_text(set_ticks(set_answer(path.read_text(), 2, "Agreed."), {1: True}))
    toy.commit("Edit from the Space")
    ws = Workspace(toy.root)
    news = received(ws, History(toy.root, ws.sessions["S2"].received["base"]))
    assert news.previous == "S2"
    [d] = news.debriefs
    assert not d.full and [(n, a) for n, _, a in d.answers] == [(2, "Agreed.")]
    assert d.ticked == ["Next step: check the weights by sampling exit times."] and not d.note_changed
    assert news.edits == {}


def test_changed_by_session(toy):
    toy.git_init()
    base = toy.commit("base")
    (toy.root / "conventions.md").write_text("# Conventions\n\n- Walkers have generator Δ.\n")
    toy.commit("[S3] compute(C-S3-1): fix the time convention")
    (toy.root / "draft.tex").write_text((toy.root / "draft.tex").read_text() + "% copied\n")
    toy.commit("[S3] apply the lines ticked in the S2 debrief")
    (toy.root / "project.md").write_text((toy.root / "project.md").read_text() + "Researcher's line.\n")
    toy.commit("Researcher's edits")
    text = changed_by_session(History(toy.root, None), "S3", base)
    assert "- `project.md`: unchanged." in text
    assert "- `draft.tex` (+1 −0 lines): as you ticked in S2." in text
    assert "- `conventions.md` (+2 −0 lines): compute(C-S3-1): fix the time convention." in text
    assert "+- Walkers have generator Δ." in text and "```diff" in text
    # What the session wrote in the draft in its own words is shown as a diff; what it copied as ticked is not.
    assert "own wording" not in text
    (toy.root / "draft.tex").write_text((toy.root / "draft.tex").read_text() + "Yang shows this~\\cite{yang2015}.\n")
    toy.commit("[S3] draft: cite Yang 2015, as the next step asks")
    text = changed_by_session(History(toy.root, None), "S3", base)
    assert "- `draft.tex` (+2 −0 lines): as you ticked in S2; draft: cite Yang 2015, as the next step asks." in text
    assert "The session's own wording in the draft:" in text
    assert "+Yang shows this~\\cite{yang2015}." in text and "+% copied" not in text
    (toy.root / "draft.tex").write_text((toy.root / "draft.tex").read_text() + "".join(f"Line {i}.\n" for i in range(70)))
    toy.commit("[S3] draft: write the introduction, as the next step asks")
    text = changed_by_session(History(toy.root, None), "S3", base)
    assert "+Line 58." in text and "+Line 59." not in text and "… 11 more changed lines: read them in draft.tex." in text


def test_the_templates_compile_to_pdf():
    import shutil
    from pathlib import Path

    import pytest

    if not shutil.which("latexmk"):
        pytest.skip("latexmk is not installed")
    from pdf import build_pdf

    templates = Path(__file__).resolve().parents[1] / "commons" / "templates"
    data, log = build_pdf((templates / "draft.tex").read_text(), "", "draft")
    assert data and data.startswith(b"%PDF"), log
    note = (templates / "note.tex").read_text().replace("<Statement.>", "As shown in \\cite{yang2015}.")
    bib = "@misc{yang2015,\n  author = {Yang, Lei},\n  title = {{Walks}},\n  year = {2015},\n}\n"
    data, log = build_pdf(note, bib, "note")
    assert data and data.startswith(b"%PDF"), log
