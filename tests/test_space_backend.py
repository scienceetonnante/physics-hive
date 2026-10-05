"""Tests of the Space's backend and of the explainer's tools, on toy workspaces.

Most tests read and write a toy folder in local mode. Where a test needs the
Hub (pull requests, commits naming the user), a fake HfApi stands in for it;
the chat loop runs against a fake inference client. Nothing calls the network.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import shutil
import sys
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

    def __init__(self, root: Path, prs=()):
        self.root, self.prs = root, list(prs)
        self.commits: list[dict] = []
        self.merged: list[tuple] = []

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

    def list_repo_commits(self, repo_id, repo_type=None):
        return [SimpleNamespace(title=c["message"], authors=["space"], created_at=None) for c in reversed(self.commits)]

    def merge_pull_request(self, repo_id, num, repo_type=None, comment=None):
        self.merged.append((num, comment))


def hub_backend(toy, monkeypatch, prs=()) -> tuple[sb.Backend, FakeHub]:
    fake = FakeHub(toy.root, prs)
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
    assert "key ×1" in b.papers_markdown()
    assert "**key** — carol" in b.paper_markdown("P-2301.01234")
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
    assert "**Q-alice-20261005T140000** · open" in b.questions_markdown()

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
    assert "promoted by lead on" in b.card_markdown("CL-S1-1")

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
    assert [p["num"] for p in b.proposal_prs()] == [12]
    assert "#12 Proposal: plan.md (by alice) — open" in b.proposals_markdown()
    assert "#3 [S3] Derive X — draft" in b.overview_markdown()
    assert "Edit conventions.md (lead, from the Space)" in b.overview_markdown()  # recent changes

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
        b.overview_markdown()
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
    b.react("alice", "CL-S1-2", "doubtful", "eq. 2?")

    text = b.card_markdown("CL-S1-2")
    assert "**claim** · **established**" in text
    assert "**Needs re-check:** this card depends, directly or not, on CL-S1-1 (refuted)." in text
    assert "**Depends on**\n- CL-S1-1 · refuted — $E = mc^2$ in the rest frame" in text
    assert "**Cards that depend on it**\n- CL-S2-1 · working" in text
    assert "**Evidence:** D-S1-2 [R-S1-1 confirmed]" in text
    assert "- promoted by lead on 2026-10-06" in text
    assert '- **doubtful** — alice: "eq. 2?" (2026-10-05)' in text
    assert "refuted by DE-S2-1" in b.card_markdown("CL-S1-1")
    assert b.card_markdown("CL-S9-9").startswith("*There is no card")

    [item] = b.evidence_items("CL-S1-2")
    assert item == {"title": "D-S1-2 (derivation)", "summary": "Summary.",
                    "files": [{"path": "derivations/D-S1-2.tex", "text": "\\documentclass{article}\n", "language": "latex"}],
                    "reviews": [{"title": "Review R-S1-1: confirmed", "body": "Review."}]}
    assert b.artefact_choices("CL-S1-2") == ["D-S1-2"]
    assert dict(b.related("CL-S1-1"))["Refuted by"] == ["DE-S2-1"]

    assert [c.id for c in b.matching_cards("Needing a re-check")] == ["CL-S1-2", "CL-S2-1"]
    assert [c.id for c in b.matching_cards("Refuted claims")] == ["CL-S1-1"]
    assert [c.id for c in b.matching_cards("Dead ends")] == ["DE-S2-1"]
    assert [c.id for c in b.matching_cards("All cards", "rest FRAME")] == ["CL-S1-1"]
    assert "**CL-S1-2** · established · needs re-check (CL-S1-1 refuted)" in b.index_markdown("Established claims")
    assert b.card_choices("Refuted claims") == [("CL-S1-1 — $E = mc^2$ in the rest frame", "CL-S1-1")]


def test_sessions_questions_and_overview(toy):
    toy.card("CL-S1-1")
    toy.card("Q-S1-1", kind="question")
    toy.write("sessions/S1/brief.md", {"session": "S1", "goal": "Derive X", "budget": 20, "starts_from": ["Q-S1-1"]},
              "## Goal\n")
    toy.write("sessions/S1/report.md", {"session": "S1", "stop_reason": "goal reached", "dispatches": 7},
              "## Found\n- CL-S1-1\n\n## Proposed plan changes\n- Add a computation.\n\n"
              "## Proposed promotions\n- CL-S1-1: D-S1-1 with a confirming review\n")
    toy.write("sessions/S2/brief.md", {"session": "S2", "goal": "Check the limit"}, "")
    b = local(toy)

    s2, s1 = b.session_views()
    assert s2["title"] == "S2 — Check the limit (no report yet)" and s2["proposals"] == []
    assert s1["proposals"] == [{"card": "CL-S1-1", "reason": "CL-S1-1: D-S1-1 with a confirming review",
                                "status": "working", "statement": "statement of CL-S1-1"}]
    assert "Brief: budget of 20 dispatches; starts from Q-S1-1." in s1["markdown"]
    assert "**Stopped:** goal reached, after 7 dispatches." in s1["markdown"]
    assert "#### Proposed plan changes\n\n- Add a computation." in s1["markdown"]
    assert "#### Proposed promotions" in s1["markdown"]

    assert "**Q-S1-1** · open" in b.questions_markdown()
    overview = b.overview_markdown()
    assert "### Problem\n\nToy question." in overview  # problem.md, with its headings under the page's own
    assert "*plan.md is still empty.*" in overview
    assert "1 claims (1 working), 1 open questions" in overview


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


def test_the_app_builds_without_a_server(toy, monkeypatch):
    gr = pytest.importorskip("gradio")
    explainer_toy(toy)
    monkeypatch.setenv("PHYSICS_INTERN_LOCAL", str(toy.root))
    monkeypatch.setenv("PHYSICS_INTERN_LOCAL_USER", "lead")
    sys.modules.pop("app", None)
    import app

    assert isinstance(app.demo, gr.Blocks)
    assert app.backend.local and app.backend.snap is None  # nothing is read before the first page view
    # The Hub version (with the sign-in button) is not built here: outside a Space, Gradio replaces
    # sign-in by the local Hugging Face login, which needs the network.

    # The page-load event computes every view.
    [load] = [f for f in app.demo.fns.values() if getattr(f.fn, "__name__", "") == "on_load"]
    out = load.fn("All cards", "", "CL-S1-1", "P-2301.01234", 0, "problem.md", None)
    texts = [v for v in out.values() if isinstance(v, str)]
    assert any("Toy question." in t for t in texts)
    assert any("**CL-S1-1** · working" in t for t in texts)
    assert any("Signed in as **lead**, a lead." in t for t in texts)
