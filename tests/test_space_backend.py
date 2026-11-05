"""Tests of the Space: its backend and its pages, on toy workspaces.

Most tests read and write a toy folder in local mode. The Hub store is tested
against a local git repository standing in for the workspace on the Hub, with
a fake HfApi that records commits. Nothing calls the network.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import DEBRIEF, conjecture, result
from human import parse_debrief

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "space"))

import backend as sb  # noqa: E402


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def local(toy, user: str | None = "alice") -> sb.Backend:
    return sb.Backend(sb.LocalStore(toy.root), local_user=user)


NOTE = r"""\documentclass{article}
\title{Walks stop at the first eigenvalue}
\begin{document}
\maketitle
\begin{abstract}Walk-on-spheres works below $\lambda_1$ only. Nothing else was found.\end{abstract}
\section{The barrier}
\begin{result}[Barrier]
The mean is finite only for $k^2<\lambda_1$.\card{CL-S1-1}
\end{result}
\end{document}
"""


def project(toy):
    """A workspace after one session: a reviewed claim, a paper, a note and an open debrief."""
    toy.card("CL-S1-1", statement="The mean is finite only below the first eigenvalue.")
    toy.card("CL-S1-2", statement="An unreviewed claim.")
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    toy.write("literature/P-1512.07725.md", {"id": "P-1512.07725", "kind": "paper", "title": "Walk on spheres for Helmholtz",
                                             "authors": ["Yang, Lei", "Other, A."], "year": 2015, "arxiv": "1512.07725",
                                             "why": "It gives the per-ball weights.", "topic": "Helmholtz by walks",
                                             "rating": "high", "session": "S1"}, "## Main result\nWeights.\n")
    (toy.root / "literature/overview.md").write_text("# Overview\n\n## Helmholtz by walks\n\nIt stops at $\\lambda_1$.\n")
    (toy.root / "literature/seeds.md").write_text("# Seed papers\n")
    (toy.root / "sessions/S1").mkdir(parents=True, exist_ok=True)
    (toy.root / "sessions/S1/note.tex").write_text(NOTE)
    (toy.root / "sessions/S1/log.md").write_text("# Log\n\n## Handoff\n\nNothing.\n")
    toy.write("sessions/S1/brief.md", {"session": "S1", "goal": "Survey the field", "budget": 20}, "## Goal\n")
    toy.debrief("S1", DEBRIEF.format(s="S1"))
    toy.git_init()
    toy.received("S1", git(toy.root, "rev-parse", "HEAD"), "2026-10-20T09:00:00Z", {})
    toy.commit("[S1] the session")


# ----- reading -----


def test_latest_shows_open_debriefs(toy):
    project(toy)
    b = local(toy)
    [d] = b.debriefs()
    assert d["id"] == "S1" and d["open"] and d["summary"] == "Summary of what the session found."
    # Once S2 has started and read it, it is closed, and the line says so.
    toy.received("S2", git(toy.root, "rev-parse", "HEAD"), "2026-10-22T09:00:00Z",
                 {"S1": {"note": ""}})
    b.refresh()
    [d] = b.debriefs()
    assert not d["open"] and d["read_by"] == "S2" and d["read_on"] == "2026-10-22"


def test_draft_notes_and_literature(toy):
    project(toy)
    toy.draft(result("CL-S1-1"), conjecture("CL-S1-2"), "See \\cite{yang2015}.")
    b = local(toy)
    draft = b.draft()
    assert draft["results"] == 1 and draft["conjectures"] == 1 and draft["flags"] == []
    assert '/card/CL-S1-1' in draft["html"].body
    toy.card("DE-S2-1", kind="dead-end", refutes=["CL-S1-1"])
    b.refresh()
    draft = b.draft()
    assert any("refuted by DE-S2-1" in f for f in draft["flags"])
    assert "refuted by DE-S2-1" in draft["html"].body  # the result is marked on the page

    [row] = b.sessions()
    assert row["title"] == "Walks stop at the first eigenvalue" and row["abstract"].startswith("Walk-on-spheres works")
    note = b.note("S1")
    assert "/card/CL-S1-1" in note["html"].body
    with pytest.raises(sb.SpaceError):
        b.note("S9")

    lit = b.literature()
    [(topic, [paper])] = lit["groups"]
    assert topic == "Helmholtz by walks" and paper["why"] == "It gives the per-ball weights."
    assert paper["by"] == "Yang et al." and paper["mine"] is None and paper["agent"] == "high"


def test_the_record_pages(toy):
    project(toy)
    b = local(toy)
    card = b.card("CL-S1-1")
    assert card["evidence"][0]["title"].startswith("D-S1-1") and card["row"]["status"] == "working"
    session = b.session("S1")
    assert [r["id"] for r in session["cards"]] == ["CL-S1-1", "CL-S1-2"] and session["log"] == "sessions/S1/log.md"
    assert b.file("sessions/S1/log.md")["body"].startswith("# Log")
    for bad in ("../etc/passwd", "/etc/passwd", ".git/config"):
        assert b.file_path(bad) is None


def test_the_method_comes_from_the_workspace_copy(toy):
    project(toy)
    copy = toy.root / ".physics-hive" / "scripts"
    copy.mkdir(parents=True)
    for name in sb.METHOD_MODULES:
        (copy / f"{name}.py").write_text((REPO / "scripts" / f"{name}.py").read_text())
    (copy / "regen.py").write_text((copy / "regen.py").read_text().replace(
        "def status_text(ws: Workspace, card_id: str) -> str:\n",
        "def status_text(ws: Workspace, card_id: str) -> str:\n    return 'from the copy'\n"))
    b = local(toy)
    assert b.row("CL-S1-1")["status_text"] == "from the copy"
    assert "cards" not in sys.modules or Path(sys.modules["cards"].__file__).parent == REPO / "scripts"


def test_an_unreachable_workspace_is_a_message():
    b = sb.Backend.from_env({"PHYSICS_HIVE_WORKSPACE": "org/x"})
    with pytest.raises(sb.SpaceError, match="HF_TOKEN"):
        b.current()
    assert "PHYSICS_HIVE_WORKSPACE" in sb.Backend.from_env({}).error


# ----- writing -----


def test_answering_a_debrief(toy):
    project(toy)
    b = local(toy)
    [d] = b.debriefs()
    with pytest.raises(sb.SpaceError, match="Sign in"):
        local(toy, None).save_debrief(None, "S1", {}, set(), "")
    message = b.save_debrief("alice", "S1", {1: "Walks only first.", 2: ""}, {0, 2}, "Start on the disk.", d["text"])
    assert "next session reads them" in message
    saved = parse_debrief((toy.root / "sessions/S1/debrief.md").read_text())
    assert [q.answer for q in saved.questions] == ["Walks only first.", ""]
    assert [t.checked for t in saved.ticks] == [True, False, True] and saved.note == "Start on the disk."
    # A form opened before that save is refused rather than overwriting it.
    with pytest.raises(sb.SpaceError, match="changed since you opened it"):
        b.save_debrief("alice", "S1", {1: "Other."}, set(), "", d["text"])


def test_saving_the_researchers_files(toy):
    project(toy)
    b = local(toy)
    text = (toy.root / "project.md").read_text()
    assert b.save_file("alice", "project.md", text + "2. A new step.\n", text) == "Saved project.md."
    with pytest.raises(sb.SpaceError, match="not one of the files"):
        b.save_file("alice", "claims/CL-S1-1.md", "x", None)
    with pytest.raises(sb.SpaceError, match="changed since"):
        b.save_file("alice", "project.md", "# Other\n", text)
    draft = (toy.root / "draft.tex").read_text()
    with pytest.raises(sb.SpaceError, match="CL-S1-2 has no supporting artefact"):
        b.save_file("alice", "draft.tex", draft.replace("\\end{document}", result("CL-S1-2") + "\\end{document}"), draft)
    b.save_file("alice", "draft.tex", draft.replace("\\end{document}", result("CL-S1-1") + "\\end{document}"), draft)
    b.refresh()
    assert b.row("CL-S1-1")["status"] == "established"
    edited = (toy.root / "sessions/S1/debrief.md").read_text() + "\nA remark at the end.\n"
    b.save_file("alice", "sessions/S1/debrief.md", edited, None)


def test_rating_papers(toy):
    project(toy)
    b = local(toy)
    assert "high" in b.rate("alice", "P-1512.07725", "high")
    assert (toy.root / "literature/ratings.yaml").read_text().endswith("P-1512.07725: high\n")
    assert b.literature()["groups"][0][1][0]["mine"] == "high"
    assert b.rate("alice", "P-1512.07725", "high") == "Nothing changed."
    with pytest.raises(sb.SpaceError, match="one of"):
        b.rate("alice", "P-1512.07725", "great")
    with pytest.raises(sb.SpaceError, match="no paper card"):
        b.rate("alice", "P-0000.00000", "low")
    b.rate("alice", "P-1512.07725", "not relevant")
    b.rate("alice", "P-1512.07725", "")
    assert "P-1512.07725" not in (toy.root / "literature/ratings.yaml").read_text()


# ----- the Hub -----


class FakeApi:
    """Records commits, and applies them to the stand-in remote, as the Hub would."""

    def __init__(self, remote: Path):
        self.remote, self.commits = remote, []

    def create_commit(self, repo_id, operations, commit_message, repo_type, parent_commit=None):
        head = git(self.remote, "rev-parse", "HEAD")
        if parent_commit and parent_commit != head:
            raise RuntimeError("A commit has happened since. Please refresh and try again.")
        self.commits.append({"message": commit_message, "parent": parent_commit,
                             "files": {op.path_in_repo: op.path_or_fileobj.decode() for op in operations}})
        for op in operations:
            path = self.remote / op.path_in_repo
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(op.path_or_fileobj)
        git(self.remote, "add", "-A")
        git(self.remote, "commit", "-q", "-m", commit_message)

    def get_repo_discussions(self, repo_id, repo_type, discussion_type):
        return [SimpleNamespace(num=4, title="[S4] Compute X", status="draft", author="bob", created_at=None,
                                url="https://hf.co/x/discussions/4")]


def test_the_hub_store_reads_a_clone_and_commits_through_the_api(toy, tmp_path):
    project(toy)
    git(toy.root, "branch", "-M", "main")
    api = FakeApi(toy.root)
    store = sb.HubStore("org/toy", "token", api=api, remote=str(toy.root), cache=tmp_path / "cache")
    b = sb.Backend(store)
    b.refresh()
    root, revision = b.snap.root, b.snap.revision
    assert revision == git(toy.root, "rev-parse", "HEAD") and (root / "project.md").is_file()
    assert [r["id"] for r in b.running()] == ["S4"]

    [d] = b.debriefs()
    b.save_debrief("alice", "S1", {1: "Yes."}, {1}, "", d["text"])
    [commit] = api.commits
    assert commit["parent"] == revision and commit["message"] == "Answer the S1 debrief (alice, from the Space)"
    assert b.snap.revision != revision and parse_debrief(b.read("sessions/S1/debrief.md")).questions[0].answer == "Yes."
    for _ in range(4):  # old worktrees are removed
        b.rate("alice", "P-1512.07725", "low" if _ % 2 else "high")
    assert len([p for p in (tmp_path / "cache" / "org--toy").iterdir() if p.name != "clone"]) <= sb.KEEP_WORKTREES


# ----- the pages -----


@pytest.fixture
def client(toy, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    project(toy)
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL", str(toy.root))
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL_USER", "alice")
    sys.modules.pop("app", None)
    import app

    return TestClient(app.app), toy


def csrf_of(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def test_the_pages_and_the_forms(client):
    c, toy = client
    for url in ("/", "/project", "/draft", "/draft/edit", "/sessions", "/note/S1", "/note/S1?source=1", "/literature",
                "/paper/P-1512.07725", "/card/CL-S1-1", "/session/S1", "/file/sessions/S1/log.md", "/edit/project.md",
                "/edit/sessions/S1/debrief.md"):
        r = c.get(url)
        assert r.status_code == 200, (url, r.text[:500])
    assert c.get("/card/CL-S9-9").status_code == 404
    assert c.get("/edit/claims/CL-S1-1.md").status_code == 404

    page = c.get("/").text
    assert "Must the method use walks only?" in page and "What the next session will receive" not in page
    assert "sessions/*/debrief.md" not in page and 'class="brand"' not in page and 'target="_top"' not in page
    assert "Latest session debrief</h1>" in page and '<span class="chip open">active</span>' in page
    assert "Toy question?" not in page  # the question is on the Project page, not here
    assert '<span class="count">1</span>' in page
    token = csrf_of(page)
    base = (toy.root / "sessions/S1/debrief.md").read_text()
    r = c.post("/debrief/S1", data={"answer-1": "Walks only.", "tick-2": "on", "note": "Disk.", "base": base,
                                    "csrf": token})
    assert r.status_code == 200 and "Saved your answers" in r.text
    saved = parse_debrief((toy.root / "sessions/S1/debrief.md").read_text())
    assert saved.questions[0].answer == "Walks only." and [t.checked for t in saved.ticks] == [False, False, True]
    assert "out of date" in c.post("/debrief/S1", data={"note": "x", "base": base, "csrf": "forged"}).text

    r = c.post("/rate", data={"paper_id": "P-1512.07725", "rating": "medium", "csrf": token})
    assert r.status_code == 200 and (toy.root / "literature/ratings.yaml").read_text().endswith("medium\n")

    text = (toy.root / "project.md").read_text()
    r = c.post("/edit/project.md", data={"text": text + "2. More.\n", "base": text, "csrf": token})
    assert r.status_code == 200 and "Saved project.md" in r.text

    r = c.post("/preview", data={"text": NOTE, "csrf": token})
    assert r.status_code == 200 and "Walks stop at the first eigenvalue" in r.text

    draft = (toy.root / "draft.tex").read_text()
    bad = draft.replace("\\end{document}", result("CL-S1-2") + "\\end{document}")
    r = c.post("/edit/draft.tex", data={"text": bad, "base": draft, "csrf": token})
    assert "was not saved" in r.text and (toy.root / "draft.tex").read_text() == draft


def test_discarding_an_edit_goes_back(client):
    c, _ = client
    for url, back in (("/edit/project.md", "/project"), ("/edit/sessions/S1/debrief.md", "/#S1"),
                      ("/edit/literature/seeds.md", "/literature"), ("/draft/edit", "/draft")):
        assert f'<a href="{back}" class="small">Discard my changes</a>' in c.get(url).text, url


def test_signing_in_from_a_new_tab(client):
    c, _ = client
    assert c.get("/whoami").json() == {"user": "alice"}
    page = c.get("/signed-in", params={"back": "/project"}).text
    assert "You are signed in as alice." in page and '<a href="/project">Work in this tab</a>' in page
    assert '<a href="/">Work in this tab</a>' in c.get("/signed-in", params={"back": "//elsewhere.com"}).text
