"""Tests of the Space's backend, its pages, and the explainer's tools, on toy workspaces.

Most tests read and write a toy folder in local mode. Where a test needs the
Hub (pull requests, commits naming the user), a fake HfApi stands in for it;
the chat loop runs against a fake inference client. Nothing calls the network.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import re
import shutil
import sys
import tempfile
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest

import cards as repo_cards
from cards import Workspace, split_front_matter
from check import run_checks
from promote import promotion_record

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "space"))

import backend as sb  # noqa: E402
import chat  # noqa: E402


@pytest.fixture
def times(monkeypatch):
    """Successive times one second apart, so that the records of one test get distinct names."""
    start = dt.datetime(2026, 10, 5, 14, 0, 0, tzinfo=dt.timezone.utc)
    ticks = itertools.count()
    monkeypatch.setattr(sb, "now_utc", lambda: start + dt.timedelta(seconds=next(ticks)))


def local(toy, user: str | None = None) -> sb.Backend:
    return sb.Backend(sb.LocalStore(toy.root), local_user=user)


def front(path: Path) -> tuple[dict, str]:
    return split_front_matter(path.read_text())


def all_files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


def paper(toy, paper_id: str = "P-2301.01234", title: str = "Weak-field corrections") -> None:
    toy.write(f"literature/{paper_id}.md", {"id": paper_id, "kind": "paper", "title": title, "year": 2023,
                                            "arxiv": paper_id[2:]}, "## Main result\nA table of X.\n")


class FakeHub:
    """Stands in for HfApi: a commit to main writes into the toy folder; pull requests are recorded."""

    def __init__(self, root: Path, prs=(), pr_files=None):
        self.root, self.prs = root, list(prs)
        self.pr_files = pr_files or {}  # number -> {path: text}, the files a pull request changes
        self.commits: list[dict] = []
        self.merged: list[tuple] = []
        self.closed: list[tuple] = []

    def repo_info(self, repo_id, repo_type=None):
        return SimpleNamespace(sha=f"sha{len(self.commits)}")

    def create_commit(self, repo_id, operations, *, commit_message, repo_type=None, create_pr=None,
                      parent_commit=None, commit_description=None, run_as_future=False):
        files = {}
        for op in operations:
            with op.as_file() as handle:
                files[op.path_in_repo] = handle.read().decode()
        self.commits.append({"repo": repo_id, "message": commit_message, "create_pr": bool(create_pr),
                             "parent": parent_commit, "files": files})
        if create_pr:
            num = 10 + len(self.prs)
            self.prs.append(SimpleNamespace(num=num, title=commit_message, status="open", author="space",
                                            created_at=None, url=f"https://hub.example/pr/{num}"))
            return SimpleNamespace(pr_num=num, pr_url=f"https://hub.example/pr/{num}")
        if repo_id == "org/toy":
            for rel, text in files.items():
                (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.root / rel).write_text(text)
        info = SimpleNamespace(pr_num=None, pr_url=None)
        if run_as_future:
            future = Future()
            future.set_result(info)
            return future
        return info

    def get_repo_discussions(self, repo_id, repo_type=None, discussion_type=None):
        return iter(self.prs)

    def list_repo_commits(self, repo_id, repo_type=None, revision=None):
        if revision:  # a pull request: one commit on top of the first commit of main
            return [SimpleNamespace(commit_id=revision), SimpleNamespace(commit_id="first")]
        return [SimpleNamespace(commit_id=f"c{i}", title=c["message"], authors=["space"], created_at=None)
                for i, c in reversed(list(enumerate(self.commits)))] + [
                    SimpleNamespace(commit_id="first", title="Initialize", authors=["lead"], created_at=None)]

    def list_repo_tree(self, repo_id, repo_type=None, revision=None, recursive=False):
        changed = self.pr_files.get(int(revision.rsplit("/", 1)[1]), {}) if revision.startswith("refs/pr/") else {}
        return [SimpleNamespace(path="problem.md", blob_id="same"), SimpleNamespace(path="claims", tree_id="t")] + [
            SimpleNamespace(path=rel, blob_id=f"new {rel}") for rel in changed]

    def merge_pull_request(self, repo_id, num, repo_type=None, comment=None):
        self.merged.append((num, comment))

    def change_discussion_status(self, repo_id, num, status, comment=None, repo_type=None):
        self.closed.append((num, comment))

    def get_discussion_details(self, repo_id, num, repo_type=None):
        return SimpleNamespace(events=[SimpleNamespace(type="comment", content=f"Description of #{num}.")], diff="")

    def hf_hub_download(self, repo_id, filename, repo_type=None, revision=None):
        path = Path(tempfile.mkdtemp()) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.pr_files[int(revision.rsplit("/", 1)[1])][filename])
        return str(path)


def hub_backend(toy, monkeypatch, prs=(), pr_files=None) -> tuple[sb.Backend, FakeHub]:
    fake = FakeHub(toy.root, prs, pr_files)
    monkeypatch.setattr(sb, "snapshot_download", lambda repo_id, **kwargs: str(toy.root))
    return sb.Backend(sb.HubStore("org/toy", "space-token", api=fake)), fake


def pr(num: int, title: str, status: str = "open") -> SimpleNamespace:
    return SimpleNamespace(num=num, title=title, status=status, author="op", created_at=None, url=f"https://hub.example/pr/{num}")


class FakeClient:
    """An inference client that asks for one tool call, then answers. Records what it was sent."""

    def __init__(self):
        self.sent: list[list[dict]] = []

    def chat_completion(self, messages, tools=None, tool_choice=None, max_tokens=None):
        self.sent.append([dict(m) for m in messages])
        if len(self.sent) == 1:
            call = SimpleNamespace(id="call-1", function=SimpleNamespace(
                name="open_artefact", arguments='{"artefact_id": "D-S1-1", "part": "full"}'))
            message = SimpleNamespace(content="", tool_calls=[call])
        else:
            message = SimpleNamespace(content="The project does not contain the small-mass limit (CL-S1-1).",
                                      tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


# ----- writes -----


def test_reactions_keep_one_current_per_person(toy, times):
    toy.card("CL-S1-1")
    paper(toy)
    b = local(toy)
    assert "doubtful" in b.react("alice", "CL-S1-1", "doubtful", "  not sure\n about eq. (3) ")
    b.react("bob", "CL-S1-1", "convinced")
    b.react("alice", "CL-S1-1", "convinced", "checked it")

    first = toy.root / "feedback/reaction-CL-S1-1-alice-20261005T140000.md"
    meta, body = front(first)
    assert meta == {"kind": "reaction", "target": "CL-S1-1", "value": "doubtful",
                    "by": {"kind": "human", "user": "alice"}, "date": "2026-10-05T14:00:00Z"}
    assert body == "not sure about eq. (3)\n"
    ws = Workspace(toy.root)
    assert [(r.user, r.value, r.comment) for r in ws.current_reactions("CL-S1-1")] == [
        ("alice", "convinced", "checked it"), ("bob", "convinced", "")]
    assert ws.evidence("CL-S1-1") == []  # reactions carry no evidential weight

    b.react("carol", "P-2301.01234", "key")
    assert [(r.user, r.value) for r in Workspace(toy.root).current_reactions("P-2301.01234")] == [("carol", "key")]
    with pytest.raises(sb.SpaceError, match="one of: key, useful, irrelevant"):
        b.react("alice", "P-2301.01234", "convinced")
    with pytest.raises(sb.SpaceError, match="Sign in"):
        b.react(None, "CL-S1-1", "wrong")
    with pytest.raises(sb.SpaceError, match="no card or paper card"):
        b.react("alice", "CL-S9-9", "wrong")
    assert not run_checks(Workspace(toy.root)).errors


def test_cards_are_written_from_a_form(toy, times):
    toy.card("CL-S1-1")
    b = local(toy)
    statement = r"Does $X$ reduce to the textbook value when $m \to 0$?"
    assert "Q-alice-20261005T140000" in b.write_card("alice", "question", statement, "Asked after reading D-S1-1.",
                                                    depends_on=["CL-S1-1"])
    meta, body = front(toy.root / "claims/Q-alice-20261005T140000.md")
    assert meta == {"id": "Q-alice-20261005T140000", "kind": "question", "statement": statement,
                    "depends_on": ["CL-S1-1"], "produced_by": {"kind": "human", "user": "alice"}, "session": None,
                    "supersedes": [], "refutes": [], "answers": []}
    assert body == "Asked after reading D-S1-1.\n"
    assert [row["id"] for row in b.results()["questions"]] == ["Q-alice-20261005T140000"]

    b.write_card("lead", "claim", "X reduces to the textbook value.", "By hand: expand to first order.",
                 depends_on=["CL-S1-1"], answers=["Q-alice-20261005T140000"], supersedes=["CL-S1-1"])
    ws = Workspace(toy.root)
    assert ws.cards["CL-lead-20261005T140001"].produced_by == {"kind": "human", "user": "lead"}
    assert ws.status("Q-alice-20261005T140000") == "answered"
    assert ws.status("CL-S1-1") == "revised"
    assert not run_checks(ws).errors

    before = all_files(toy.root)
    with pytest.raises(sb.SpaceError, match="CL-S9-9, which does not exist"):
        b.write_card("alice", "claim", "S", depends_on=["CL-S9-9"])
    with pytest.raises(sb.SpaceError, match=r"a claim card \(expected a question\)"):
        b.write_card("alice", "claim", "S", answers=["CL-S1-1"])
    with pytest.raises(sb.SpaceError, match="Write a statement"):
        b.write_card("alice", "question", "   ")
    with pytest.raises(sb.SpaceError, match="Sign in"):
        b.write_card(None, "question", "S")
    assert all_files(toy.root) == before  # a refused card leaves nothing behind


def test_a_verification_is_evidence(toy, times):
    toy.card("CL-S1-1")
    toy.derivation("D-S1-1", ["CL-S1-1"])
    b = local(toy)
    b.verify("alice", "CL-S1-1", "confirmed", "Checked eq. (3) and the small-mass limit.", target="D-S1-1")
    b.verify("bob", "CL-S1-1", "inconclusive", "Could not follow step 4.")

    meta, body = front(toy.root / "feedback/review-CL-S1-1-alice-20261005T140000.md")
    assert meta == {"id": "R-alice-20261005T140000", "kind": "review", "target": "D-S1-1", "supports": ["CL-S1-1"],
                    "claim": "statement of CL-S1-1", "verdict": "confirmed", "by": {"kind": "human", "user": "alice"},
                    "date": "2026-10-05T14:00:00Z"}
    assert body == "Checked eq. (3) and the small-mass limit.\n"
    ws = Workspace(toy.root)
    first, second = ws.evidence("CL-S1-1")
    assert first.artefact == "D-S1-1" and [r.verdict for r in first.reviews] == ["confirmed"]
    assert second.verification.by == {"kind": "human", "user": "bob"} and second.verification.verdict == "inconclusive"
    assert not run_checks(ws).errors

    with pytest.raises(sb.SpaceError, match="not among the evidence"):
        b.verify("alice", "CL-S1-1", "confirmed", "x", target="D-S9-9")
    with pytest.raises(sb.SpaceError, match="Say what you checked"):
        b.verify("alice", "CL-S1-1", "confirmed", "  ")
    with pytest.raises(sb.SpaceError, match="verdict is one of"):
        b.verify("alice", "CL-S1-1", "maybe", "x")


def test_promotion_follows_the_workspace_rule(shared_toy, times):
    t = shared_toy
    t.card("CL-S1-1")
    b = local(t)
    with pytest.raises(sb.SpaceError, match="neither a supporting artefact with a confirming review"):
        b.promote("lead", "CL-S1-1")
    t.derivation("D-S1-1", ["CL-S1-1"])
    t.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    with pytest.raises(sb.SpaceError, match=r"alice is not in \[people\] leads"):
        b.promote("alice", "CL-S1-1")
    assert not list((t.root / "feedback").glob("promotion-*"))

    assert "Promoted **CL-S1-1**" in b.promote("lead", "CL-S1-1", "one derivation, one confirming review")
    [record] = (t.root / "feedback").glob("promotion-CL-S1-1-lead-*.md")
    meta, body = front(record)
    expected, _ = split_front_matter(promotion_record("CL-S1-1", {"kind": "human", "user": "lead"}, None, "x")[1])
    assert list(meta) == list(expected)  # the same record as promote.py writes
    assert meta["by"] == {"kind": "human", "user": "lead"} and meta["session"] is None
    assert body == "one derivation, one confirming review\n"
    assert Workspace(t.root).status("CL-S1-1") == "established"
    [shown] = b.card("CL-S1-1")["promotions"]
    assert (shown["by"], shown["counted"], shown["reason"]) == ("lead", True, "one derivation, one confirming review")

    t.card("DE-S2-1", kind="dead-end", refutes=["CL-S1-1"])
    with pytest.raises(sb.SpaceError, match="CL-S1-1 is refuted"):
        b.promote("lead", "CL-S1-1")


def test_promotion_needs_a_lead_in_local_mode_too(toy):
    toy.card("CL-S1-1")
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    b = local(toy)
    with pytest.raises(sb.SpaceError, match=r"alice is not in \[people\] leads"):
        b.promote("alice", "CL-S1-1")
    b.promote("lead", "CL-S1-1")
    assert Workspace(toy.root).status("CL-S1-1") == "established"


def test_lead_files_in_local_mode(toy):
    b = local(toy)
    assert b.lead_file("plan.md") == "# Plan\n"
    assert b.save_lead_file("lead", "plan.md", "# Plan\r\n\r\nTry the perturbative route first.", base="# Plan\n") == \
        "Saved plan.md on main."
    assert (toy.root / "plan.md").read_text() == "# Plan\n\nTry the perturbative route first.\n"
    with pytest.raises(sb.SpaceError, match="changed on main since you opened it"):
        b.save_lead_file("lead", "plan.md", "# Plan\n\nOther.\n", base="# Plan\n")
    with pytest.raises(sb.SpaceError, match="Nothing to save"):
        b.save_lead_file("lead", "plan.md", "# Plan\n\nTry the perturbative route first.\n")
    with pytest.raises(sb.SpaceError, match="no pull requests"):
        b.save_lead_file("alice", "plan.md", "# Plan\n\nMine.\n")
    with pytest.raises(sb.SpaceError, match="not one of the lead's files"):
        b.save_lead_file("lead", "claims/CL-S1-1.md", "x")


def test_lead_files_and_proposals_on_the_hub(shared_toy, monkeypatch):
    b, fake = hub_backend(shared_toy, monkeypatch, [pr(3, "[S3] Derive X", "draft"), pr(2, "Proposal: plan.md", "merged")])
    assert b.save_lead_file("lead", "conventions.md", "# Conventions\n\nSignature (-,+,+,+).\n") == \
        "Saved conventions.md on main."
    assert fake.commits[-1] == {"repo": "org/toy", "message": "Edit conventions.md (lead, from the Space)",
                                "create_pr": False, "parent": None,
                                "files": {"conventions.md": "# Conventions\n\nSignature (-,+,+,+).\n"}}

    message = b.save_lead_file("alice", "plan.md", "# Plan\n\nAlice's idea.\n", base="# Plan\n")
    assert fake.commits[-1]["create_pr"] and fake.commits[-1]["message"] == "Proposal: plan.md (by alice)"
    assert "[#12](https://hub.example/pr/12)" in message
    assert (shared_toy.root / "plan.md").read_text() == "# Plan\n"  # main is unchanged until a lead merges

    assert [p["num"] for p in b.open_sessions()] == [3]
    assert [p["num"] for p in b.attention()["proposals"]] == [12]
    assert "Edit conventions.md (lead, from the Space)" in [c["title"] for c in b.commits]  # recent changes

    with pytest.raises(sb.SpaceError, match="Only a lead"):
        b.merge_proposal("alice", 12)
    with pytest.raises(sb.SpaceError, match="not an open proposal"):
        b.merge_proposal("lead", 3)
    assert b.merge_proposal("lead", "12") == "Merged pull request #12."
    assert fake.merged == [(12, "Merged from the Space by lead.")]


def test_hub_writes_are_commits_that_name_the_user(shared_toy, monkeypatch, times):
    shared_toy.card("CL-S1-1")
    shared_toy.derivation("D-S1-1", ["CL-S1-1"])
    shared_toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    b, fake = hub_backend(shared_toy, monkeypatch)
    b.react("alice", "CL-S1-1", "convinced")
    assert fake.commits[-1]["message"] == "Reaction convinced on CL-S1-1 (alice, from the Space)"
    assert list(fake.commits[-1]["files"]) == ["feedback/reaction-CL-S1-1-alice-20261005T140000.md"]
    b.promote("lead", "CL-S1-1")
    assert fake.commits[-1]["message"] == "Promote CL-S1-1 (lead)"
    assert fake.commits[-1]["parent"] == "sha1"  # checked and committed against the same main
    assert b.current().ws.status("CL-S1-1") == "established"  # refreshed after the write


def test_an_unreachable_workspace_is_a_message():
    class Down:
        def repo_info(self, *args, **kwargs):
            raise ConnectionError("no route to host")

    b = sb.Backend(sb.HubStore("org/x", "token", api=Down()))
    b.refresh()
    assert "could not read the workspace org/x" in b.error
    assert "could not read" in b.status_markdown()
    with pytest.raises(sb.SpaceError, match="could not read the workspace"):
        b.attention()
    assert "HF_TOKEN is not set" in sb.Backend.from_env({"PHYSICS_INTERN_WORKSPACE": "org/x"}).error
    assert "PHYSICS_INTERN_WORKSPACE" in sb.Backend.from_env({}).error
    with pytest.raises(sb.SpaceError, match="PHYSICS_INTERN_WORKSPACE"):
        sb.Backend.from_env({}).current()


def test_the_method_comes_from_the_workspace_copy(toy):
    copy = toy.root / ".physics-intern/scripts"
    shutil.copytree(REPO / "scripts", copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (copy / "cards.py").write_text((copy / "cards.py").read_text() + "\nMETHOD_MARK = 'workspace copy'\n")
    snap = local(toy).current()
    assert snap.m.cards.METHOD_MARK == "workspace copy"
    assert snap.m.regen.Workspace is snap.m.cards.Workspace  # regen runs on the same copy
    assert isinstance(snap.ws, snap.m.cards.Workspace)
    assert sys.modules["cards"] is repo_cards  # the rest of the process does not see the copy
    assert not list(copy.rglob("__pycache__"))


# ----- views -----


def test_card_view(toy, times):
    toy.card("CL-S1-1", statement="$E = mc^2$ in the rest frame")
    toy.card("CL-S1-2", depends_on=["CL-S1-1"])
    toy.card("CL-S2-1", depends_on=["CL-S1-2"])
    toy.derivation("D-S1-2", ["CL-S1-2"])
    toy.review("D-S1-2_R-S1-1", "confirmed", ["CL-S1-2"])
    toy.promotion("CL-S1-2")
    toy.card("DE-S2-1", kind="dead-end", refutes=["CL-S1-1"])
    b = local(toy)

    view = b.card("CL-S1-2")
    assert view["row"] == {"id": "CL-S1-2", "kind": "claim", "status": "established", "status_text": "established",
                           "recheck": [("CL-S1-1", "refuted")], "statement": "statement of CL-S1-2",
                           "evidence": ["D-S1-2 [R-S1-1 confirmed]"], "author": None}
    assert [(label, [row["id"] for row in rows]) for label, rows in view["related"]] == [
        ("Depends on", ["CL-S1-1"]), ("Cards that depend on it", ["CL-S2-1"])]
    assert view["origin"] == "agent (m), operator op, session S1"
    assert view["promotions"] == [{"by": "lead", "date": "2026-10-06", "counted": True, "reason": ""}]
    assert view["proposed"] == [] and view["trace"] is None  # established; local mode
    [item] = view["evidence"]
    assert item == {"title": "D-S1-2 (derivation)", "summary": "Summary.",
                    "files": [{"path": "derivations/D-S1-2.tex", "text": "\\documentclass{article}\n", "language": "latex"}],
                    "reviews": [{"title": "Review R-S1-1: confirmed", "body": "Review."}]}
    refuted = b.row("CL-S1-1")
    assert refuted["status_text"] == "refuted by DE-S2-1" and refuted["recheck"] == []  # nothing to re-check on it
    assert dict(b.related("CL-S1-1"))["Refuted by"] == ["DE-S2-1"]
    assert b.row("CL-S9-9")["status"] == "missing"
    with pytest.raises(sb.SpaceError, match="There is no card CL-S9-9"):
        b.card("CL-S9-9")

    results = b.results()
    assert [row["id"] for row in results["claims"]] == ["CL-S1-2", "CL-S2-1"]  # established first, then working
    assert [row["id"] for row in results["past_claims"]] == ["CL-S1-1"]
    assert [row["id"] for row in results["dead_ends"]] == ["DE-S2-1"]
    assert b.counts() == {"established claims": 1, "working claims": 1, "open questions": 0, "cards to re-check": 2,
                          "dead ends": 1, "papers": 0}


def test_sessions_and_what_needs_attention(toy):
    toy.card("CL-S1-1")
    toy.card("Q-S1-1", kind="question")
    toy.write("sessions/S1/brief.md", {"session": "S1", "goal": "Derive X", "budget": 20, "starts_from": ["Q-S1-1"]},
              "## Goal\n\nDerive X.\n")
    toy.write("sessions/S1/report.md", {"session": "S1", "stop_reason": "goal reached", "dispatches": 7},
              "## Found\n- CL-S1-1\n\n## Refuted\n(none)\n\n## Proposed plan changes\n- Add a computation.\n\n"
              "## Proposed promotions\n- CL-S1-1: D-S1-1 with a confirming review\n\n"
              "## Needs a human decision\n- Q-S1-1: which sign convention?\n")
    toy.write("sessions/S2/brief.md", {"session": "S2", "goal": "Check the limit"}, "")
    b = local(toy)

    assert [s.id for s in b.sessions()] == ["S2", "S1"]
    s1 = b.session("S1")
    assert s1["brief"] == "## Goal\n\nDerive X."
    assert list(s1["sections"]) == ["Found", "Proposed plan changes", "Proposed promotions", "Needs a human decision"]
    assert s1["pr"] is None and s1["trace"] is None and s1["log"] is None  # local mode, no log written
    with pytest.raises(sb.SpaceError, match="no session S9"):
        b.session("S9")

    attention = b.attention()
    assert attention["decisions"] == ("S1", "- Q-S1-1: which sign convention?")  # from the latest report
    assert [(row["id"], sessions) for row, sessions in attention["promotions"]] == [("CL-S1-1", ["S1"])]
    assert attention["proposals"] == []
    assert b.lead_text("problem.md") == "### Problem\n\nToy question."  # under the page's own headings
    assert b.lead_text("plan.md") is None  # only the template's heading
    assert b.file("sessions/S1/report.md")["header"] == "session: S1\nstop_reason: goal reached\ndispatches: 7"
    assert b.file_path("../outside") is None and b.file_path("/etc/hosts") is None


def test_writing_to_the_agents_and_answering(toy, times):
    toy.card("CL-S1-1")
    toy.card("Q-S1-1", kind="question")
    paper(toy)
    b = local(toy)
    assert sb.split_text("  Is $X$ right?\r\n\r\nI doubt eq. (3).\n\nAnd (4).  ") == (
        "Is $X$ right?", "I doubt eq. (3).\n\nAnd (4).")

    assert "next session" in b.ask("alice", "Is X right?\n\nI doubt eq. (3).", about="CL-S1-1")
    asked = Workspace(toy.root).cards["Q-alice-20261005T140000"]
    assert (asked.kind, asked.statement, asked.depends_on, asked.body.strip()) == (
        "question", "Is X right?", ["CL-S1-1"], "I doubt eq. (3).")
    b.ask("alice", "Read its table 2.", about="P-2301.01234")  # a paper is named in the body, not in depends_on
    about_paper = Workspace(toy.root).cards["Q-alice-20261005T140001"]
    assert about_paper.depends_on == [] and about_paper.body.strip() == "About P-2301.01234."

    assert b.answer("lead", "Q-S1-1", "The plus sign.\n\nAs in P1.") == "Wrote **CL-lead-20261005T140002**. It answers Q-S1-1."
    ws = Workspace(toy.root)
    assert ws.status("Q-S1-1") == "answered" and ws.cards["CL-lead-20261005T140002"].body.strip() == "As in P1."
    with pytest.raises(sb.SpaceError, match="Write something"):
        b.ask("alice", "  \n ")
    with pytest.raises(sb.SpaceError, match=r"expected a question"):
        b.answer("lead", "CL-S1-1", "Yes.")
    with pytest.raises(sb.SpaceError, match="Sign in"):
        b.ask(None, "Hello?")
    assert not run_checks(ws).errors


def test_proposals_on_the_hub(shared_toy, monkeypatch):
    prs = [pr(3, "[S3] Derive X", "draft"), pr(2, "[S1] Plan proposal: X first"), pr(1, "[S1] Survey", "merged")]
    b, fake = hub_backend(shared_toy, monkeypatch, prs, {2: {"plan.md": "# Plan\n\nX first.\n"}})
    b.current()
    assert [p["num"] for p in b.open_sessions()] == [3]
    assert [p["num"] for p in b.proposal_prs()] == [2]  # drafted by S1, but not S1's own pull request
    proposal = b.proposal("2")
    assert proposal["description"] == "Description of #2."
    assert proposal["files"] == [{"path": "plan.md", "text": "# Plan\n\nX first.\n"}]
    with pytest.raises(sb.SpaceError, match="#3 is not a proposal"):
        b.proposal(3)
    assert b.hub_url("workspace", "discussions", "3") == f"{sb.HUB}/datasets/org/toy/discussions/3"

    with pytest.raises(sb.SpaceError, match="Only a lead can close"):
        b.close_proposal("alice", 2)
    assert b.close_proposal("lead", 2) == "Closed pull request #2."
    assert fake.closed == [(2, "Closed from the Space by lead.")] and fake.merged == []


# ----- the explainer -----


def explainer_toy(toy) -> None:
    toy.card("CL-S1-1", statement=r"The correction is $\alpha^2/4$")
    toy.card("CL-S1-2", depends_on=["CL-S1-1"])
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    paper(toy)


def test_chat_tools_read_and_never_write(toy):
    explainer_toy(toy)
    before = all_files(toy.root)
    tools = chat.Tools(local(toy))

    card = tools.open_card("CL-S1-1")
    assert card.startswith("Card CL-S1-1 (claim), status: working.")
    assert r"Statement: The correction is $\alpha^2/4$" in card
    assert "Cards that depend on it: CL-S1-2 (working)" in card
    assert "Evidence: D-S1-1 [R-S1-1 confirmed]" in card
    summary = tools.open_artefact("D-S1-1")
    assert "Supports: CL-S1-1. Full material: derivations/D-S1-1.tex. Reviews: R-S1-1 confirmed." in summary
    assert summary.endswith("Summary.")
    assert "=== derivations/D-S1-1.tex ===\n\\documentclass{article}" in tools.open_artefact("D-S1-1", "full")
    assert "=== Review R-S1-1: confirmed; it concerns CL-S1-1 ===\nReview." in tools.open_artefact("D-S1-1", "reviews")
    assert "A table of X." in tools.open_paper("P-2301.01234")
    assert tools.search_index("weak-field corrections").startswith("- **P-2301.01234**")
    assert tools.search_index("correction alpha").startswith("- **CL-S1-1**")
    assert "Nothing in the index matches" in tools.search_index("graviton")
    assert "There is no card" in tools.call("open_card", {"card_id": "CL-S9-9"})
    assert "There is no artefact" in tools.call("open_artefact", {"artefact_id": "D-S9-9"})
    assert "There is no tool" in tools.call("delete_card", {"card_id": "CL-S1-1"})
    opening = tools.opening("CL-S1-1")
    assert opening.startswith("Card CL-S1-1") and "D-S1-1 (derivation)." in opening
    assert {t["function"]["name"] for t in chat.TOOLS} == {"open_card", "open_artefact", "open_paper", "search_index"}
    assert all_files(toy.root) == before


def test_chat_answer_runs_the_tool_loop(toy):
    explainer_toy(toy)
    client = FakeClient()
    history = [{"role": "user", "content": [{"text": "Why the cross term?", "type": "text"}]},
               {"role": "assistant", "content": "Because of eq. (12)."}]
    reply, note = chat.respond(local(toy, "alice"), "alice", None, "CL-S1-1", history, "And when m -> 0?",
                               "Step by step", client=client)
    assert reply.startswith("The project does not contain")
    assert note == "Read for this answer: D-S1-1 (full)."
    first = client.sent[0]
    assert first[0]["role"] == "system" and "Card CL-S1-1" in first[0]["content"]
    assert "go step by step" in first[0]["content"].lower()
    assert [(m["role"], m["content"]) for m in first[1:]] == [
        ("user", "Why the cross term?"), ("assistant", "Because of eq. (12)."), ("user", "And when m -> 0?")]
    tool_message = client.sent[1][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "call-1"
    assert "\\documentclass" in tool_message["content"]

    hub = sb.Backend(sb.HubStore("org/toy", "space-token", api=FakeHub(toy.root)))
    reply, _ = chat.respond(hub, None, None, "CL-S1-1", [], "Why?", "Terse and technical", client=FakeClient())
    assert reply.startswith("Sign in")  # on the Hub, the chat runs on the reader's own token


def test_chat_logs_only_in_debug_mode(toy, tmp_path_factory, monkeypatch):
    explainer_toy(toy)
    log = tmp_path_factory.mktemp("logs") / "chat.jsonl"
    monkeypatch.setenv("PHYSICS_INTERN_CHAT_LOG", str(log))
    quiet = local(toy, "alice")
    chat.respond(quiet, "alice", None, "CL-S1-1", [], "Why?", "Terse and technical", client=FakeClient())
    assert not log.exists() and quiet.chat_banner() == ""

    loud = sb.Backend(sb.LocalStore(toy.root), local_user="alice", chat_debug=True)
    loud.current()
    assert "chat conversations are logged" in loud.chat_banner() and str(log) in loud.chat_banner()
    chat.respond(loud, "alice", None, "CL-S1-1", [], "Why?", "Terse and technical", client=FakeClient())
    [line] = log.read_text().splitlines()
    record = json.loads(line)
    assert record["user"] == "alice" and record["card"] == "CL-S1-1" and record["question"] == "Why?"
    assert record["answer"].startswith("The project does not contain")
    assert record["tool_calls"] == [{"name": "open_artefact", "arguments": {"artefact_id": "D-S1-1", "part": "full"}}]


def test_hub_chat_log_goes_to_the_chat_debug_dataset(shared_toy, monkeypatch):
    explainer_toy(shared_toy)
    toml = shared_toy.root / "project.toml"
    toml.write_text(toml.read_text().replace('traces = "org/toy-traces"\n',
                                             'traces = "org/toy-traces"\nchat_debug = "org/toy-chat-debug"\n'))
    b, fake = hub_backend(shared_toy, monkeypatch)
    b.chat_debug = True
    b.current()
    assert "org/toy-chat-debug" in b.chat_banner()
    chat.respond(b, "alice", "alice-token", "CL-S1-1", [], "Why?", "Terse and technical", client=FakeClient())
    [commit] = fake.commits
    assert commit["repo"] == "org/toy-chat-debug" and commit["message"] == "Chat exchange (alice)"
    [(name, text)] = commit["files"].items()
    assert name.startswith("exchanges/") and json.loads(text)["question"] == "Why?"


def test_question_card_from_the_chat():
    history = [{"role": "user", "content": "Why the cross term?"}, {"role": "assistant", "content": "Because…"},
               {"role": "user", "content": [{"text": "And for m -> 0?", "type": "text"}]},
               {"role": "assistant", "content": "The project does not contain it.\nSecond line."}]
    asked, replied = chat.last_exchange(history)
    assert (asked, replied) == ("And for m -> 0?", "The project does not contain it.\nSecond line.")
    body = chat.question_card_body("CL-S3-2", asked, replied)
    assert body.startswith("Asked in the explainer chat about CL-S3-2:\n\n> And for m -> 0?")
    assert "> The project does not contain it.\n> Second line.\n" in body
    assert chat.last_exchange([]) == ("", "")


# ----- the page -----


def test_the_pages_and_the_forms(toy, monkeypatch, times):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    explainer_toy(toy)
    toy.card("Q-S1-1", kind="question", statement="Which sign for $X$?")
    toy.write("sessions/S1/report.md", {"session": "S1", "stop_reason": "goal reached", "dispatches": 3},
              "## Found\n- CL-S1-1, from `derivations/D-S1-1.summary.md`\n\n## Needs a human decision\n- Q-S1-1\n")
    monkeypatch.setenv("PHYSICS_INTERN_LOCAL", str(toy.root))
    monkeypatch.setenv("PHYSICS_INTERN_LOCAL_USER", "lead")
    sys.modules.pop("app", None)
    import app

    assert app.backend.local and app.backend.snap is None  # nothing is read before the first page view
    client = TestClient(app.app)

    status = client.get("/").text
    assert "Toy question." in status and "Decisions asked by the" in status
    assert '<a href="/card/Q-S1-1">Q-S1-1</a>' in status  # every existing card ID links to its card
    assert '<a href="/file/derivations/D-S1-1.summary.md"><code>derivations/D-S1-1.summary.md</code></a>' in status
    assert '<span class="math inline">X</span>' in client.get("/results").text  # equations are left to KaTeX
    card = client.get("/card/CL-S1-1").text
    assert '<a href="/file/derivations/D-S1-1.summary.md">D-S1-1</a> (derivation)' in card  # its evidence
    assert "Promote to established" in card and "Write to the agents" in card
    for url in ("/paper/P-2301.01234", "/session/S1", "/file/derivations/D-S1-1.tex", "/edit/plan.md"):
        assert client.get(url).status_code == 200, url
    assert client.get("/card/CL-S9-9").status_code == 404

    csrf = re.search(r'name="csrf" value="([^"]+)"', card).group(1)
    sent = client.post("/ask", data={"text": "Why $\\alpha^2$?", "about": "CL-S1-1", "csrf": csrf}, follow_redirects=False)
    assert sent.status_code == 303 and sent.headers["location"] == "/card/CL-S1-1"
    assert "Wrote <strong>" in client.get("/card/CL-S1-1").text  # the message after the write
    assert Workspace(toy.root).cards["Q-lead-20261005T140000"].depends_on == ["CL-S1-1"]
    forged = client.post("/ask", data={"text": "Lost?", "csrf": "forged"})
    assert "This page was out of date" in forged.text and "Lost?" in forged.text  # refused, and the text is kept
    answered = client.post("/card/Q-S1-1/answer", data={"text": "The plus sign.", "csrf": csrf}, follow_redirects=False)
    assert answered.status_code == 303 and Workspace(toy.root).status("Q-S1-1") == "answered"

    form = {"text": "# Plan\n\nTry $X$.", "base": "# Plan\n", "csrf": csrf}
    preview = client.post("/edit/plan.md", data={**form, "action": "preview"})
    assert "Preview (not saved)" in preview.text and (toy.root / "plan.md").read_text() == "# Plan\n"
    saved = client.post("/edit/plan.md", data={**form, "action": "save"}, follow_redirects=False)
    assert saved.status_code == 303 and (toy.root / "plan.md").read_text() == "# Plan\n\nTry $X$.\n"
