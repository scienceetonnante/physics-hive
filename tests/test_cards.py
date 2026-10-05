"""Tests for computed status, evidence, propagation, the generated views and check."""

from __future__ import annotations

from cards import Workspace, promotion_problems
from check import run_checks
from regen import regenerate


def build_chain(toy):
    """CL-S1-1 <- CL-S1-2 <- CL-S2-1 (each depends on the previous one)."""
    toy.card("CL-S1-1")
    toy.card("CL-S1-2", depends_on=["CL-S1-1"])
    toy.card("CL-S2-1", depends_on=["CL-S1-2"])
    toy.card("CL-S2-2")  # independent


def test_refutation_marks_all_dependents(toy):
    build_chain(toy)
    toy.card("DE-S3-1", kind="dead-end", refutes=["CL-S1-1"])
    ws = Workspace(toy.root)
    assert ws.status("CL-S1-1") == "refuted"
    assert ws.needs_recheck("CL-S1-2") == ["CL-S1-1"]
    assert ws.needs_recheck("CL-S2-1") == ["CL-S1-1"]
    assert ws.needs_recheck("CL-S2-2") == []
    assert ws.needs_recheck("CL-S1-1") == []

    regenerate(toy.root)
    index = (toy.root / "INDEX.md").read_text()
    line = next(l for l in index.splitlines() if "**CL-S2-1**" in l)
    assert "needs re-check (CL-S1-1 refuted)" in line
    line = next(l for l in index.splitlines() if "**CL-S2-2**" in l)
    assert "needs re-check" not in line


def test_regeneration_is_deterministic(toy):
    build_chain(toy)
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    toy.card("Q-S1-1", kind="question")
    regenerate(toy.root)
    first = {name: (toy.root / name).read_text() for name in ("INDEX.md", "research_log.md")}
    for name in first:
        (toy.root / name).unlink()
    regenerate(toy.root)
    second = {name: (toy.root / name).read_text() for name in ("INDEX.md", "research_log.md")}
    assert first == second
    regenerate(toy.root)
    assert first == {name: (toy.root / name).read_text() for name in first}


def test_status_precedence(toy):
    toy.card("CL-S1-1")
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    toy.promotion("CL-S1-1", kind="agent", user="agent")
    ws = Workspace(toy.root)
    assert ws.status("CL-S1-1") == "established"
    toy.card("CL-S2-1", supersedes=["CL-S1-1"])
    ws = Workspace(toy.root)
    assert ws.status("CL-S1-1") == "revised"
    toy.card("DE-S2-1", kind="dead-end", refutes=["CL-S1-1"])
    assert Workspace(toy.root).status("CL-S1-1") == "refuted"


def test_questions_are_answered_by_cards(toy):
    toy.card("Q-S1-1", kind="question")
    assert Workspace(toy.root).status("Q-S1-1") == "open"
    toy.card("CL-lead-20261005T101010", produced_by={"kind": "human", "user": "lead"}, session=None, answers=["Q-S1-1"])
    assert Workspace(toy.root).status("Q-S1-1") == "answered"


def test_evidence_from_artefacts_reviews_and_humans(toy):
    toy.card("CL-S3-2")
    toy.card("CL-S7-1")
    toy.derivation("D-S3-2", ["CL-S3-2"])
    toy.review("D-S3-2_R-S3-1", "confirmed", ["CL-S3-2"])
    # A later review attaches the same derivation to a card created after it.
    toy.review("D-S3-2_R-S7-1", "confirmed", ["CL-S7-1"])
    toy.computation("C-S5-1", ["CL-S3-2"])
    toy.verification("lead", "20261006T101500", ["CL-S7-1"])
    ws = Workspace(toy.root)

    ev = ws.evidence("CL-S3-2")
    assert [e.artefact for e in ev] == ["C-S5-1", "D-S3-2"]
    assert [r.id for r in ev[1].reviews] == ["D-S3-2_R-S3-1"]
    assert not ev[0].confirmed and ev[1].confirmed

    ev = ws.evidence("CL-S7-1")
    assert ev[0].artefact == "D-S3-2" and ev[0].attached_by == "D-S3-2_R-S7-1"
    assert [r.id for r in ev[0].reviews] == ["D-S3-2_R-S7-1"]
    assert ev[1].verification is not None and ev[1].confirmed


def test_promotion_rule(shared_toy):
    toy = shared_toy
    toy.card("CL-S1-1")
    lead = {"kind": "human", "user": "lead"}
    assert any("neither" in r for r in promotion_problems(Workspace(toy.root), "CL-S1-1", lead))
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    ws = Workspace(toy.root)
    assert promotion_problems(ws, "CL-S1-1", lead) == []
    assert any("not in [people] leads" in r for r in promotion_problems(ws, "CL-S1-1", {"kind": "human", "user": "bob"}))
    assert promotion_problems(ws, "CL-S1-1", {"kind": "agent", "model": "m"})
    toy.card("DE-S2-1", kind="dead-end", refutes=["CL-S1-1"])
    assert any("refuted" in r for r in promotion_problems(Workspace(toy.root), "CL-S1-1", lead))


def test_promotion_by_non_lead_does_not_establish(shared_toy):
    toy = shared_toy
    toy.card("CL-S1-1")
    toy.promotion("CL-S1-1", user="bob")
    assert Workspace(toy.root).status("CL-S1-1") == "working"
    toy.promotion("CL-S1-1", user="lead", stamp="20261006T110000")
    assert Workspace(toy.root).status("CL-S1-1") == "established"


def test_check_accepts_a_clean_workspace(toy):
    build_chain(toy)
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    report = run_checks(Workspace(toy.root))
    assert report.errors == [], report.problems


def test_check_finds_header_and_reference_errors(toy):
    toy.card("CL-S1-1", depends_on=["CL-S9-9"])
    toy.card("CL-S1-2", kind="question")
    toy.card("DE-S1-1", kind="dead-end", supersedes=["CL-S1-1"])
    toy.derivation("D-S1-1", ["CL-S1-7"])
    report = run_checks(Workspace(toy.root))
    messages = [str(p) for p in report.problems]
    assert any("CL-S9-9, which does not exist" in m for m in messages)
    assert any("does not match the ID prefix" in m for m in messages)
    assert any("supersedes is only allowed on claim" in m for m in messages)
    assert any("reserved ID never written" in m and m.startswith("warning") for m in messages)


def test_check_finds_cycles(toy):
    toy.card("CL-S1-1", depends_on=["CL-S1-2"])
    toy.card("CL-S1-2", depends_on=["CL-S1-1"])
    assert any("cycle" in str(p) for p in run_checks(Workspace(toy.root)).errors)


def test_check_refuses_edits_after_creation(toy):
    toy.card("CL-S1-1")
    toy.git_init()
    base = toy.commit("base")
    toy.card("CL-S1-1", statement="changed afterwards")
    toy.card("CL-S2-1")
    report = run_checks(Workspace(toy.root), base=base, session="S2")
    messages = [str(e) for e in report.errors]
    assert any("claims/CL-S1-1.md" in m and "edited after creation" in m for m in messages)
    assert not any("CL-S2-1" in m for m in messages)


def test_check_refuses_lead_files_and_foreign_ids_in_shared_session(shared_toy):
    toy = shared_toy
    toy.git_init()
    base = toy.commit("base")
    (toy.root / "plan.md").write_text("# Plan\n\nRewritten by an agent.\n")
    toy.card("CL-S4-1")
    (toy.root / ".physics-intern").mkdir()
    (toy.root / ".physics-intern/VERSION").write_text("x\n")
    report = run_checks(Workspace(toy.root), base=base, session="S5")
    messages = [str(e) for e in report.errors]
    assert any("plan.md" in m and "lead's file" in m for m in messages)
    assert any("CL-S4-1" in m and "belongs to S4" in m for m in messages)
    assert any(".physics-intern/VERSION" in m for m in messages)


def test_check_refuses_promotions_in_shared_sessions(shared_toy):
    toy = shared_toy
    toy.card("CL-S1-1")
    toy.derivation("D-S1-1", ["CL-S1-1"])
    toy.review("D-S1-1_R-S1-1", "confirmed", ["CL-S1-1"])
    toy.git_init()
    base = toy.commit("base")
    toy.promotion("CL-S1-1", user="lead")
    report = run_checks(Workspace(toy.root), base=base, session="S2")
    assert any("not inside a session" in str(e) for e in report.errors)


def test_check_validates_new_local_promotions(toy):
    toy.card("CL-S1-1")
    toy.git_init()
    base = toy.commit("base")
    toy.promotion("CL-S1-1", kind="agent", user="agent")
    report = run_checks(Workspace(toy.root), base=base, session="S1")
    assert any("promotion refused" in str(e) for e in report.errors)
