"""Tests of the example workspace in examples/pendulum.

The example is a real workspace after one session, published for readers and
for the demonstration Space. These tests keep it valid for the current scripts
and Space: it passes the method's check, its generated files are up to date,
it contains nothing private, and every page of the Space renders on it. They
work on a copy, so that nothing is written into examples/.
"""

from __future__ import annotations

import re
import shutil
import sys
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
PRIVATE = re.compile(r"/Users/|/home/|/private/|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|[\w.+-]+@[\w-]+\.[\w.]+")


@pytest.fixture
def example(tmp_path) -> Path:
    root = tmp_path / "pendulum"
    shutil.copytree(EXAMPLE, root)
    return root


def test_the_example_passes_the_check(example):
    ws = Workspace(example)
    report = run_checks(ws)
    assert not report.problems, "\n".join(map(str, report.problems))
    assert sorted(ws.cards) == ["CL-S1-1", "CL-S1-2"] and sorted(ws.sessions) == ["S1"]


def test_the_generated_files_are_up_to_date(example):
    ws = Workspace(example)
    hint = "regenerate with: uv run scripts/regen.py --root examples/pendulum"
    assert (example / "INDEX.md").read_text(encoding="utf-8") == render_index(ws), hint
    assert (example / "references.bib").read_text(encoding="utf-8") == render_bib(ws), hint
    pdf, tex = example / "sessions/S1/note.pdf", example / "sessions/S1/note.tex"
    assert pdf.read_bytes().startswith(b"%PDF") and tex.is_file()


def test_the_example_publishes_nothing_local_or_private():
    assert not [name for name in LOCAL_ONLY if (EXAMPLE / name).exists()]
    for path in EXAMPLE.rglob("*"):
        if path.is_file() and path.suffix != ".pdf":
            found = PRIVATE.search(path.read_text(encoding="utf-8"))
            assert not found, (path.relative_to(EXAMPLE), found.group(0))


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
    urls = ["/", "/project", "/draft", "/sessions", "/literature", "/session/S1", "/session/S1?note=whole",
            *(f"/card/{card}" for card in ws.cards),
            *(f"/file/{artefact.path}" for artefact in ws.artefacts.values()),
            *(f"/file/{path.relative_to(example)}" for folder in ("sessions/S1", "computations", "derivations",
                                                                   "critiques") for path in (example / folder).iterdir()
              if path.is_file() and path.suffix in (".md", ".tex", ".py", ".out", ".csv"))]
    for url in urls:
        r = c.get(url)
        assert r.status_code == 200, (url, r.text[:500])
        assert 'class="error"' not in r.text, url

    # The demonstration opens on the session waiting for the lead's response.
    page = c.get("/").text
    assert '<span class="chip open">Awaiting your response</span>' in page
    assert "The amplitude correction to the pendulum’s period" in page

    if shutil.which("latexmk"):
        r = c.get("/note/S1/pdf")
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
