"""Tests of the example workspace in examples/pendulum.

The example is a real workspace after two sessions, published for readers and
for the demonstration Space. These tests keep it valid for the current scripts
and Space: it passes the method's check, its generated files are up to date,
it contains nothing private, and every page of the Space renders on it. They
work on a copy, so that nothing is written into examples/.
"""

from __future__ import annotations

import re
import shutil
import sys
import zlib
from pathlib import Path

import pytest

from cards import Workspace
from check import run_checks
from regen import render_bib, render_index

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "pendulum"

# Files that a workspace renders or keeps locally, and that the example must not publish.
LOCAL_ONLY = (".physics-hive", ".git", "AGENTS.md", "CLAUDE.md", "opencode.json", ".mcp.json", ".claude", ".codex",
              ".agents", ".opencode", ".pi", ".active-session", "literature/sources")
PRIVATE = re.compile(r"/Users/|/home/|/private/|/var/folders/|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}"
                     r"|[\w.+-]+@[\w-]+\.[\w.]+")
# The PDFs: the draft and each session's note, compiled with scripts/pdf.py.
PDFS = ("draft.pdf", "sessions/S1/note.pdf", "sessions/S2/note.pdf")


@pytest.fixture
def example(tmp_path) -> Path:
    root = tmp_path / "pendulum"
    shutil.copytree(EXAMPLE, root)
    return root


def test_the_example_passes_the_check(example):
    ws = Workspace(example)
    report = run_checks(ws)
    assert not report.problems, "\n".join(map(str, report.problems))
    assert sorted(ws.cards) == ["CL-S1-1"] and sorted(ws.sessions) == ["S1", "S2"]
    assert sorted(ws.artefacts) == ["C-S1-2", "D-S1-1"] and sorted(ws.papers) == ["P-0707.1029", "P-physics_0510206"]
    # The lead ticked Result 1 of note S1 into the draft, so its claim is established.
    assert ws.in_draft("CL-S1-1") == "result" and ws.status("CL-S1-1") == "established"


def test_the_generated_files_are_up_to_date(example):
    ws = Workspace(example)
    hint = "regenerate with: uv run scripts/regen.py --root examples/pendulum"
    assert (example / "INDEX.md").read_text(encoding="utf-8") == render_index(ws), hint
    assert (example / "references.bib").read_text(encoding="utf-8") == render_bib(ws), hint
    for pdf in PDFS:
        assert (example / pdf).read_bytes().startswith(b"%PDF") and (example / pdf).with_suffix(".tex").is_file(), pdf


def test_the_example_publishes_nothing_local_or_private():
    assert not [name for name in LOCAL_ONLY if (EXAMPLE / name).exists()]
    for path in EXAMPLE.rglob("*"):
        if path.is_file() and path.suffix != ".pdf":
            found = PRIVATE.search(path.read_text(encoding="utf-8"))
            assert not found, (path.relative_to(EXAMPLE), found.group(0))
    # A PDF can hold the folder it was compiled in, in its metadata or in a compressed stream.
    paths = re.compile(rb"/Users/|/home/|/private/|/var/folders/|/tmp/")
    for pdf in PDFS:
        data = (EXAMPLE / pdf).read_bytes()
        streams = []
        for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
            try:
                streams.append(zlib.decompress(m.group(1)))
            except zlib.error:
                pass
        assert streams and not [s for s in (data, *streams) if paths.search(s)], pdf


def test_every_page_of_the_space_renders_on_the_example(example, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("PHYSICS_HIVE_LOCAL", str(example))
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL_USER", "demo")
    monkeypatch.syspath_prepend(str(REPO / "space"))
    sys.modules.pop("app", None)
    import app

    c = TestClient(app.app)
    ws = Workspace(example)
    urls = ["/", "/project", "/draft", "/sessions", "/literature",
            *(f"/session/{s}{view}" for s in ws.sessions for view in ("", "?note=whole")),
            *(f"/card/{card}" for card in ws.cards), *(f"/paper/{paper}" for paper in ws.papers),
            *(f"/file/{artefact.path}" for artefact in ws.artefacts.values()),
            *(f"/file/{path.relative_to(example)}" for folder in ("sessions/S1", "sessions/S2", "computations",
                                                                   "derivations", "critiques", "literature")
              for path in (example / folder).iterdir() if path.is_file() and path.suffix in (".md", ".tex", ".py",
                                                                                              ".out", ".csv"))]
    for url in urls:
        r = c.get(url)
        assert r.status_code == 200, (url, r.text[:500])
        assert 'class="error"' not in r.text, url

    # The demonstration opens on the session waiting for the lead's response: S2, whose debrief is not answered.
    page = c.get("/").text
    assert '<span class="chip open">Awaiting your response</span>' in page
    assert "A classical reference for the period of the pendulum to second order" in page
    # The lead answered S1, and the draft holds its result.
    assert "Read by S2 on 2026-11-24" in c.get("/session/S1").text
    assert '<a class="ltx-card" href="/card/CL-S1-1">' in c.get("/draft").text
    assert "<dt>Draft</dt><dd>In the draft, as a result</dd>" in c.get("/card/CL-S1-1").text

    if shutil.which("latexmk"):
        for url in ("/note/S1/pdf", "/note/S2/pdf", "/draft.pdf"):
            r = c.get(url)
            assert r.status_code == 200 and r.content.startswith(b"%PDF"), url
