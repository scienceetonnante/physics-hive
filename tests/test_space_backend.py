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
from human import parse_debrief, set_changed

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
    review = b.review()
    assert review["view"]["id"] == "S1" and review["also"] == [] and review["latest"] is None
    assert b.review_session() == "S1"
    # Once S2 has started and read it, it is closed, and the Review page only points to it.
    toy.received("S2", git(toy.root, "rev-parse", "HEAD"), "2026-10-22T09:00:00Z",
                 {"S1": {"note": ""}})
    b.refresh()
    [d] = b.debriefs()
    assert not d["open"] and d["read_by"] == "S2" and d["read_on"] == "2026-10-22"
    review = b.review()
    assert review["view"] is None and review["latest"]["id"] == "S1" and b.review_session() is None


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
    view = b.session_page("S1", card_footer=lambda c: f"<b>{c}</b>")
    assert "/card/CL-S1-1" in view["note"].body and "<b>CL-S1-1</b>" in view["note"].body
    assert view["state"] == "Awaiting your response" and view["debrief"]["open"]
    assert view["record"]["log"] == "sessions/S1/log.md" and view["record"]["debrief"] == "sessions/S1/debrief.md"
    with pytest.raises(sb.SpaceError):
        b.session_page("S9")

    lit = b.literature()
    [(topic, [paper])] = lit["groups"]
    assert topic == "Helmholtz by walks" and paper["why"] == "It gives the per-ball weights."
    assert paper["by"] == "Yang et al." and paper["mine"] is None and paper["agent"] == "high"


def test_the_record_pages(toy):
    project(toy)
    b = local(toy)
    card = b.card("CL-S1-1")
    assert card["evidence"][0]["label"] == "Derivation D-S1-1" and card["row"]["status"] == "working"
    assert card["evidence"][0]["tex"] == ["derivations/D-S1-1.tex"] and card["evidence"][0]["tone"] == "ok"
    session = b.session_page("S1")
    assert [r["id"] for r in session["other_cards"]] == ["CL-S1-2"] and session["record"]["log"] == "sessions/S1/log.md"
    assert [a.id for a in session["record"]["artefacts"]] == ["D-S1-1"]
    assert b.file("sessions/S1/log.md")["body"].startswith("# Log")
    for bad in ("../etc/passwd", "/etc/passwd", ".git/config"):
        assert b.file_path(bad) is None


def test_what_the_pages_say_about_a_claim(toy):
    project(toy)
    toy.computation("C-S1-1", ["CL-S1-1"])
    toy.review("C-S1-1_R-S1-1", "confirmed", ["CL-S1-1"], human="alice")
    toy.card("CL-S1-3", statement="Two derivations support it.")
    for art in ("D-S1-2", "D-S1-3"):
        toy.derivation(art, ["CL-S1-3"])
        toy.review(f"{art}_R-S1-1", "confirmed", ["CL-S1-3"])
    toy.card("CL-S1-4", statement="A refuted claim.")
    toy.derivation("D-S1-4", ["CL-S1-4"])
    toy.review("D-S1-4_R-S1-1", "refuted", ["CL-S1-4"])
    toy.card("DE-S1-1", kind="dead-end", statement="It fails.", refutes=["CL-S1-4"])
    b = local(toy)
    row = b.row("CL-S1-1")
    assert row["evidence_text"] == "A derivation, confirmed by a blind review (agent); a computation, checked by alice"
    assert row["tone"] == "ok" and row["place"] == "Not in the draft" and row["warning"] is None
    assert b.row("CL-S1-2")["evidence_text"].startswith("No evidence yet") and b.row("CL-S1-2")["tone"] == "open"
    assert b.row("CL-S1-3")["evidence_text"] == "Two derivations, each confirmed by a blind review (agent)"
    # The link to a card's page names what the page shows.
    assert row["material"] == "Derivation, computation and reviews"
    assert b.row("CL-S1-3")["material"] == "Two derivations and reviews" and b.row("CL-S1-2")["material"] is None
    refuted = b.row("CL-S1-4")
    assert refuted["evidence_text"] == "A derivation, refuted by a review" and refuted["tone"] == "bad"
    assert refuted["warning"] == "Refuted by DE-S1-1."
    assert b.row("DE-S1-1")["evidence_text"] is None and b.row("DE-S1-1")["refutes"] == ["CL-S1-4"]
    # The session page shows the note's results, then the session's cards that no result names.
    view = b.session_page("S1")
    assert [(blk.kind, blk.cards) for blk in view["note"].blocks] == [("result", ["CL-S1-1"])]
    assert [r["id"] for r in view["other_cards"]] == ["CL-S1-2", "CL-S1-3", "CL-S1-4", "DE-S1-1"]


def test_two_sessions_waiting_and_a_session_without_a_note(client):
    c, toy = client
    toy.card("CL-S2-1", statement="A claim of the second session.")
    toy.debrief("S2", DEBRIEF.format(s="S2").replace("Summary of what the session found.", "Little was found."))
    toy.commit("[S2] the session")
    page = c.get("/refresh", follow_redirects=True).text
    # The Review page shows the newest session waiting and points to the other one.
    assert 'Also waiting for your response: <a href="/session/S1">session 1</a> (Walks stop at the first eigenvalue).' in page
    assert '<section class="review" id="S2">' in page and '<span class="count">2</span>' in page
    # Without a note, the page shows the debrief's summary and all the session's cards.
    assert "<p>Little was found.</p>" in page and "This session wrote no note." in page
    assert page.index("Cards from this session") < page.index("A claim of the second session.")


def test_tick_lines_are_grouped_by_the_file_they_change():
    lines = ["Set the approach in the project: correlation matrices.", "Copy Result 1 of note S1 into `draft.tex`.",
             'Add to *Next steps* in `project.md`: "Write the abstract of `draft.tex`."',
             "Fix the sign of k in `conventions.md`.", "Run more walks."]
    groups = sb.tick_groups([SimpleNamespace(text=t) for t in lines])
    assert [(label, [i for i, _ in items]) for label, items in groups] == [
        ("Draft (draft.tex)", [1]), ("Research plan (project.md)", [0, 2]), ("Conventions (conventions.md)", [3]),
        ("Other", [4])]


CHANGED = """- `project.md`: unchanged.
- `conventions.md` (+2 −1 lines): derive(D-S1-1): c = 1/16 from the period; as you ticked in S1.

```diff
+- θ is the angle.
-- An older line.
```

- `draft.tex`: unchanged."""


def test_the_changes_of_a_session_are_summed_up():
    changes = sb.parse_changed(CHANGED)
    [f] = changes["files"]
    assert f["name"] == "Notation and conventions" and f["path"] == "conventions.md" and f["ticked"] == ["S1"]
    assert f["counts"] == "2 lines added and 1 line removed" and [kind for kind, _ in f["diff"]] == ["add", "del"]
    assert changes["unchanged"] == "Research plan and draft: unchanged."
    assert sb.parse_changed("(Written by session.py end, from git.)") is None  # shown as it is


def test_a_file_changed_then_restored_shows_the_tick_it_applied(client):
    # The usual second session: it added the next step the lead ticked, then removed it as finished.
    c, toy = client
    path = toy.root / "sessions/S1/debrief.md"
    path.write_text(set_changed(path.read_text(), (
        "- `project.md`: unchanged in the end (as you ticked in S1; remove the finished step).\n"
        "- `conventions.md`: unchanged.\n"
        "- `draft.tex` (+14 −0 lines): as you ticked in S1.")))
    page = c.get("/session/S1").text
    changes = page[page.index('<ul class="changes">'):]
    changes = changes[:changes.index("</ul>")]
    assert "<li><b>Research plan</b> (<code>project.md</code>): unchanged in the end, as you ticked in S1." in changes
    assert "<li><b>Draft</b> (<code>draft.tex</code>): 14 lines added, as you ticked in S1." in changes
    assert '<li class="muted">Notation and conventions: unchanged.</li>' in changes


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
        sha = git(self.remote, "rev-parse", "HEAD")
        return SimpleNamespace(oid=sha, commit_url=f"https://huggingface.co/datasets/{repo_id}/commit/{sha}")

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
    message = b.save_debrief("alice", "S1", {1: "Yes."}, {1}, "", d["text"])
    [commit] = api.commits
    sha = git(toy.root, "rev-parse", "HEAD")
    assert f"debrief (commit [{sha[:7]}](https://huggingface.co/datasets/org/toy/commit/{sha}))." in message
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
    assert "sessions/*/debrief.md" not in page and 'target="_top"' not in page
    # The Review page is the page of the session waiting for a response, titled by its note.
    assert "Walks stop at the first eigenvalue</h1>" in page and '<span class="chip open">Awaiting your response</span>' in page
    assert "Session 1 · 20 October 2026" in page
    assert "Toy question?" not in page  # the question is on the Project page, not here
    assert '<span class="count">1</span>' in page
    # The note's abstract and results, each result with its card's evidence; the session's other cards; the
    # record, folded; the response beside them. The debrief's summary is not shown: the abstract replaces it.
    assert page.index('<label for="whole-S1">Whole note</label>') < page.index("Walk-on-spheres works below") \
        < page.index("Result 1 (Barrier).") < page.index('<a href="/card/CL-S1-1">Derivation and review ↗</a>') \
        < page.index("Other cards from this session") < page.index("An unreviewed claim.") \
        < page.index('<details class="record" id="record">') < page.index('<form class="response"')
    assert "A derivation, confirmed by a blind review" not in page  # under a result, only the link to the card
    assert "<p>Summary of what the session found.</p>" not in page
    assert 'id="cut-S1" checked>' in page and 'id="whole-S1" >' in page
    assert ">Tick what you accept</h3>" not in page and '<h2 class="response-title">' not in page
    assert ">Save my response</button>" in page and "Saving does not start a session." in page
    assert '<input type="hidden" name="back" value="/">' in page
    assert page.index("Draft (draft.tex)") < page.index("Copy Result 1") < page.index("Research plan (project.md)") \
        < page.index("Set the approach")
    sessions = c.get("/sessions").text
    assert "Session 1 · 20 October 2026 · Awaiting your response" in sessions and "Survey the field" not in sessions
    assert 'href="/session/S1"' in sessions
    # The session page is the same view; the old note address opens it with the whole note.
    session = c.get("/session/S1").text
    assert "Walks stop at the first eigenvalue</h1>" in session and '<input type="hidden" name="back" value="/session/S1">' in session
    r = c.get("/note/S1")
    assert str(r.url).endswith("/session/S1?note=whole") and 'id="whole-S1" checked>' in r.text
    assert str(c.get("/note/S1?source=1").url).endswith("/file/sessions/S1/note.tex")
    assert "<dt>Evidence</dt><dd class=\"tone-ok\">A derivation, confirmed by a blind review (agent)</dd>" in c.get("/card/CL-S1-1").text
    assert "Nothing is in the draft yet." in c.get("/draft").text
    token = csrf_of(page)
    base = (toy.root / "sessions/S1/debrief.md").read_text()
    r = c.post("/debrief/S1", data={"answer-1": "Walks only.", "tick-2": "on", "note": "Disk.", "base": base,
                                    "csrf": token})
    assert r.status_code == 200 and "Saved your answers" in r.text
    # Answered: the debrief waits for the next session, and the Review tab no longer counts it.
    assert "Answered, waiting for the next session" in r.text and 'class="count"' not in r.text
    saved = parse_debrief((toy.root / "sessions/S1/debrief.md").read_text())
    assert saved.questions[0].answer == "Walks only." and [t.checked for t in saved.ticks] == [False, False, True]
    assert "out of date" in c.post("/debrief/S1", data={"note": "x", "base": base, "csrf": "forged"}).text
    # A save from the session page comes back to it.
    base = (toy.root / "sessions/S1/debrief.md").read_text()
    r = c.post("/debrief/S1", data={"answer-1": "Walks only.", "note": "Disk, then the square.", "base": base,
                                    "back": "/session/S1", "csrf": token})
    assert str(r.url).endswith("/session/S1") and "Saved your answers" in r.text

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
    assert "data-save data-unsaved" in r.text  # the refused text shows as unsaved


def test_the_save_forms_say_when_they_have_unsaved_changes(client):
    c, _ = client
    for url in ("/", "/session/S1", "/edit/project.md", "/draft/edit", "/literature"):
        page = c.get(url).text
        assert "data-save" in page and 'class="save-state' in page and "data-save data-unsaved" not in page, url
    assert "this.form.requestSubmit()" in c.get("/literature").text  # a rating shows that it is saving


def test_discarding_an_edit_goes_back(client):
    c, _ = client
    for url, back in (("/edit/project.md", "/project"), ("/edit/sessions/S1/debrief.md", "/"),
                      ("/edit/literature/seeds.md", "/literature"), ("/draft/edit", "/draft")):
        assert f'<a href="{back}" class="small" data-discard>Discard my changes</a>' in c.get(url).text, url


def test_signing_in_from_a_new_tab(client):
    c, _ = client
    assert c.get("/whoami").json() == {"user": "alice"}
    page = c.get("/signed-in", params={"back": "/project"}).text
    assert "You are signed in as alice." in page and '<a href="/project">Work in this tab</a>' in page
    assert '<a href="/">Work in this tab</a>' in c.get("/signed-in", params={"back": "//elsewhere.com"}).text


# ----- for a first-time visitor -----


def test_the_card_page_leads_with_the_material(client):
    c, toy = client
    toy.computation("C-S1-1", ["CL-S1-1"])
    (toy.root / "computations/C-S1-1.out").write_text("a = 0.0625\n")
    toy.review("C-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    page = c.get("/refresh?back=/card/CL-S1-1", follow_redirects=True).text
    # The derivation first, then the computation's output and code, each with its review; the summaries and the
    # card's own text folded below.
    assert page.index("Derivation D-S1-1</h2>") < page.index("Computation C-S1-1</h2>") \
        < page.index("Output · computations/C-S1-1.out") < page.index("Code · computations/C-S1-1.py") \
        < page.rindex("Review R-S1-1 (agent)") < page.index("The summary of C-S1-1, by the agent who wrote it") \
        < page.index("The card's own text")
    assert '<a class="btn primary" href="/file/derivations/D-S1-1.tex?rendered=1">Read the derivation</a>' in page
    # The derivation, rendered on its own page; without ?rendered=1, its source.
    rendered = c.get("/file/derivations/D-S1-1.tex?rendered=1").text
    assert 'class="paper"' in rendered and 'href="/file/derivations/D-S1-1.tex">LaTeX source</a>' in rendered
    assert "<pre>\\documentclass{article}" in c.get("/file/derivations/D-S1-1.tex").text
    # A claim that nothing supports keeps its text in view.
    assert "<p>Body.</p>" in c.get("/card/CL-S1-2").text


def test_the_help_page_titles_and_errors(client):
    c, _ = client
    page = c.get("/").text
    assert '<a href="/help">How this works</a>' in page and "<title>Review · " in page
    assert '<link rel="icon" href="data:image/svg+xml,' in page and '<meta name="description"' in page
    assert "read-only demonstration" not in page  # only in a demonstration
    help_page = c.get("/help").text
    assert "The cycle" in help_page and 'href="https://github.com/scienceetonnante/physics-hive"' in help_page
    assert "<title>Session 1 · " in c.get("/session/S1").text
    for url, said in (("/no/such/page", "There is no page at <code>/no/such/page</code>"),
                      ("/session/S9", "There is no session S9"), ("/card/CL-S9-9", "There is no card CL-S9-9")):
        r = c.get(url)
        assert r.status_code == 404 and said in r.text and '<a href="/">Back to the Review page</a>' in r.text, url
        assert "<title>Not found · " in r.text
    r = c.get("/debrief/S1")
    assert r.status_code == 405 and "it is not a page to open" in r.text


def test_a_new_space_says_what_each_page_will_show(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from conftest import ToyWorkspace

    toy = ToyWorkspace(tmp_path)
    (toy.root / "project.md").write_text("# <the question in one line>\n\n## Goal\n\n## Next steps\n")
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL", str(toy.root))
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL_USER", "alice")
    sys.modules.pop("app", None)
    import app

    c = TestClient(app.app)
    assert "No session has ended yet." in c.get("/").text and "<code>/session-run</code>" in c.get("/").text
    assert "Before the first session, write the question in one line" in c.get("/project").text
    assert "No session yet. A session starts when you run" in c.get("/sessions").text
    assert "Nothing is in the draft yet." in c.get("/draft").text
    assert "No paper yet." in c.get("/literature").text


# Every route that receives a form, and whether it writes to the workspace.
WRITING_ROUTES = {"/edit/{rel:path}", "/debrief/{session_id}", "/rate"}
READING_ROUTES = {"/preview"}  # renders the draft editor's preview; writes nothing


@pytest.fixture
def demo(toy, monkeypatch):
    """The Space as a public demonstration: read-only, on a local folder. A local user set by mistake is ignored."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    project(toy)
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL", str(toy.root))
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL_USER", "alice")
    monkeypatch.setenv("PHYSICS_HIVE_READONLY", "1")
    sys.modules.pop("app", None)
    import app

    return TestClient(app.app), toy, app


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}


def test_a_read_only_demonstration_shows_everything_and_saves_nothing(demo):
    c, toy, app = demo
    # Every page opens, without sign-in, with a banner that links to the repository.
    for url in ("/", "/project", "/draft", "/draft/edit", "/sessions", "/session/S1", "/literature", "/help",
                "/paper/P-1512.07725", "/card/CL-S1-1", "/file/sessions/S1/log.md", "/edit/project.md",
                "/edit/sessions/S1/debrief.md", "/edit/literature/seeds.md"):
        r = c.get(url)
        assert r.status_code == 200, url
        assert "This is a read-only demonstration of" in r.text and "https://github.com/scienceetonnante/physics-hive" in r.text
        assert "Sign in" not in r.text and "alice" not in r.text and "PHYSICS_HIVE_LOCAL_USER" not in r.text, url
    # The response form can be typed in; before its first question it says that nothing is saved, and what saving does.
    page = c.get("/").text
    form = page[page.index('<form class="response"'):page.index("</form>")]
    assert form.index("You can type") < form.index('name="answer-1"') and "commits them to the workspace" in form
    assert "disabled>" not in form.split("<button")[0] and "data-save" not in form
    assert '<button class="primary" type="button" disabled>Save my response</button>' in form
    assert "example workspace" in page and str(toy.root) not in page  # the footer does not show the folder
    # Every route that receives a form is known here, and every one that writes refuses on the server.
    posts = {r.path for r in app.app.routes if "POST" in getattr(r, "methods", set())}
    assert posts == WRITING_ROUTES | READING_ROUTES
    before = snapshot(toy.root)
    token = csrf_of(c.get("/edit/project.md").text)
    debrief = (toy.root / "sessions/S1/debrief.md").read_text()
    for url, data in (("/debrief/S1", {"answer-1": "Yes.", "tick-0": "on", "note": "N.", "base": debrief}),
                      ("/debrief/S1", {"answer-1": "Yes.", "base": debrief, "back": "/session/S1"}),
                      ("/edit/project.md", {"text": "# Changed\n", "base": (toy.root / "project.md").read_text()}),
                      ("/edit/conventions.md", {"text": "# Changed\n", "base": (toy.root / "conventions.md").read_text()}),
                      ("/edit/literature/seeds.md", {"text": "# Changed\n", "base": (toy.root / "literature/seeds.md").read_text()}),
                      ("/edit/draft.tex", {"text": "% changed\n", "base": (toy.root / "draft.tex").read_text()}),
                      ("/edit/sessions/S1/debrief.md", {"text": "Changed.\n", "base": debrief}),
                      ("/rate", {"paper_id": "P-1512.07725", "rating": "high"})):
        r = c.post(url, data={**data, "csrf": token})
        assert "Nothing was saved: this is a read-only demonstration." in r.text, url
    assert snapshot(toy.root) == before
    assert c.post("/preview", data={"text": NOTE, "csrf": token}).status_code == 200  # the preview still renders
    # The backend refuses on its own, whoever the user.
    b = sb.Backend(sb.LocalStore(toy.root), local_user="alice", readonly=True)
    for write in (lambda: b.save_file("alice", "project.md", "# X\n"), lambda: b.save_debrief("alice", "S1", {}, {0}, "x"),
                  lambda: b.rate("alice", "P-1512.07725", "high")):
        with pytest.raises(sb.SpaceError, match="read-only demonstration"):
            write()
    assert snapshot(toy.root) == before
    assert sb.Backend.from_env({"PHYSICS_HIVE_LOCAL": str(toy.root), "PHYSICS_HIVE_READONLY": "1"}).readonly
    assert not sb.Backend.from_env({"PHYSICS_HIVE_LOCAL": str(toy.root)}).readonly


def test_normal_mode_writes_through_every_writing_route(client):
    """The counterpart of the demonstration: outside it, the same posts save."""
    c, toy = client
    token = csrf_of(c.get("/edit/project.md").text)
    for rel in ("project.md", "conventions.md", "literature/seeds.md"):
        base = (toy.root / rel).read_text()
        assert "Saved" in c.post(f"/edit/{rel}", data={"text": base + "More.\n", "base": base, "csrf": token}).text
        assert (toy.root / rel).read_text().endswith("More.\n")
    page = c.get("/").text
    assert "data-save" in page and "read-only demonstration" not in page


# ----- what the Space opens -----


def test_inside_refuses_paths_that_leave_the_workspace_or_name_secrets(tmp_path):
    root = tmp_path / "ws"
    (root / "derivations/.briefs").mkdir(parents=True)
    (root / "derivations/.briefs/b.md").write_text("brief")
    (tmp_path / "secret").write_text("hf_secret")
    (root / "out.md").symlink_to(tmp_path / "secret")
    for bad in ("", "../secret", "/etc/passwd", ".git/config", "a/.git/x", ".env", "sessions/S1/.env",
                ".env.local", "out.md"):
        assert sb.inside(root, bad) is None, bad
    assert sb.inside(root, "derivations/.briefs/b.md") == (root / "derivations/.briefs/b.md").resolve()


def test_links_out_of_the_workspace_are_never_opened(client, tmp_path_factory):
    c, toy = client
    secret = tmp_path_factory.mktemp("outside") / "environ"
    secret.write_text("HF_TOKEN=hf_secret_value\n")
    (toy.root / "literature/x.md").symlink_to(secret)
    (toy.root / "derivations/D-S1-9.tex").symlink_to(secret)
    (toy.root / "literature/inner.md").symlink_to(toy.root / "project.md")  # a link that stays inside is followed
    (toy.root / ".env").write_text("HF_TOKEN=hf_secret_value\n")
    (toy.root / "sessions/S1/.env.local").write_text("HF_TOKEN=hf_secret_value\n")
    (toy.root / "derivations/.briefs").mkdir()
    (toy.root / "derivations/.briefs/D-S1-1.md").write_text("The brief of D-S1-1.\n")
    # The evidence of a claim: a computation whose output is a link out of the workspace.
    toy.computation("C-S1-1", ["CL-S1-1"])
    (toy.root / "computations/C-S1-1.out").symlink_to(secret)
    c.get("/refresh")
    for url in ("/file/literature/x.md", "/file/derivations/D-S1-9.tex?rendered=1", "/file/.env",
                "/file/sessions/S1/.env.local", "/file/literature/../../x"):
        r = c.get(url)
        assert r.status_code == 404 and "hf_secret_value" not in r.text, url
    assert "hf_secret_value" not in c.get("/card/CL-S1-1").text
    assert "Toy question?" in c.get("/file/literature/inner.md").text
    assert "<p>The brief of " in c.get("/file/derivations/.briefs/D-S1-1.md").text
    # One of the lead's files replaced by a link out of the workspace: nothing is written through it.
    target = tmp_path_factory.mktemp("outside2") / "victim"
    target.write_text("keep\n")
    (toy.root / "conventions.md").unlink()
    (toy.root / "conventions.md").symlink_to(target)
    with pytest.raises(sb.SpaceError, match="nothing was saved"):
        local(toy).save_file("alice", "conventions.md", "# Overwritten\n", "")
    assert target.read_text() == "keep\n"


def test_the_hub_store_checks_out_links_as_plain_files(toy, tmp_path):
    project(toy)
    (toy.root / "literature/x.md").symlink_to("/etc/hosts")
    toy.commit("a link")
    git(toy.root, "branch", "-M", "main")
    b = sb.Backend(sb.HubStore("org/toy", "token", api=FakeApi(toy.root), remote=str(toy.root), cache=tmp_path / "c"))
    b.refresh()
    path = b.snap.root / "literature/x.md"
    assert not path.is_symlink() and path.read_text() == "/etc/hosts"


def test_a_demonstration_compiles_each_source_once_and_one_at_a_time(toy, monkeypatch):
    import threading
    import time

    project(toy)
    b = sb.Backend(sb.LocalStore(toy.root), readonly=True)
    calls, active, peak = [], [0], [0]
    lock = threading.Lock()

    def build_pdf(tex, bib, name):
        with lock:
            calls.append(name)
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.2)
        with lock:
            active[0] -= 1
        return (None, "! Undefined control sequence.") if name == "note" else (b"%PDF-1.5 draft", "")

    monkeypatch.setattr(b.current().m.pdf, "build_pdf", build_pdf)
    results = []

    def fetch(rel):
        try:
            results.append(b.pdf(rel)[0])
        except sb.SpaceError as exc:
            results.append(str(exc))

    threads = [threading.Thread(target=fetch, args=(rel,)) for rel in ["draft.tex"] * 4 + ["sessions/S1/note.tex"] * 3]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # One compile per source, never two at once; the failure is kept too.
    assert sorted(calls) == ["draft", "note"] and peak[0] == 1
    assert results.count(b"%PDF-1.5 draft") == 4 and sum("did not compile" in str(r) for r in results) == 3
    # Outside a demonstration, every request compiles, as before.
    normal = local(toy)
    monkeypatch.setattr(normal.current().m.pdf, "build_pdf", build_pdf)
    normal.pdf("draft.tex")
    normal.pdf("draft.tex")
    assert calls.count("draft") == 3


def test_the_host_check_applies_only_when_serve_py_asks_for_it(toy, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    project(toy)
    monkeypatch.setenv("PHYSICS_HIVE_LOCAL", str(toy.root))
    monkeypatch.setenv("PHYSICS_HIVE_ALLOWED_HOSTS", "127.0.0.1,localhost")
    sys.modules.pop("app", None)
    import app

    assert TestClient(app.app, base_url="http://127.0.0.1:8000").get("/").status_code == 200
    assert TestClient(app.app, base_url="http://localhost:7860").get("/project").status_code == 200
    r = TestClient(app.app, base_url="http://127.0.0.1:8000").get("/", headers={"host": "attacker.example:8000"})
    assert r.status_code == 400
    monkeypatch.delenv("PHYSICS_HIVE_ALLOWED_HOSTS")
    sys.modules.pop("app", None)
    import app as unchecked  # noqa: F811  (the Space on the Hub: any host name)

    assert TestClient(unchecked.app, base_url="http://my-space.hf.space").get("/").status_code == 200


def test_review_before_the_first_session_asks_only_for_what_is_missing(toy, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("PHYSICS_HIVE_LOCAL", str(toy.root))
    sys.modules.pop("app", None)
    import app

    page = TestClient(app.app).get("/").text  # the toy's project.md has a question and a goal
    assert "No session has ended yet." in page and "To start the first session, run <code>/session-run</code>" in page
    assert "Before the first session, write the question" not in page
    assert "The session proposes a brief, by default the first next" in TestClient(app.app).get("/help").text
