"""Tests for computed status, evidence, propagation, the generated files and check."""

from __future__ import annotations

from cards import Workspace, result_problems
from check import run_checks
from conftest import DEBRIEF, conjecture, result
from regen import bib_keys, regenerate


def build_chain(toy):
    """CL-S1-1 <- CL-S1-2 <- CL-S2-1 (each depends on the previous one)."""
    toy.card("CL-S1-1")
    toy.card("CL-S1-2", depends_on=["CL-S1-1"])
    toy.card("CL-S2-1", depends_on=["CL-S1-2"])
    toy.card("CL-S2-2")  # independent


def confirmed(toy, card_id: str, art: str = "D-S1-1") -> None:
    toy.derivation(art, [card_id])
    toy.review(f"{art}_R-S1-1", "confirmed", [card_id])


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
    confirmed(toy, "CL-S1-1")
    toy.write("literature/P-1512.07725.md", {"id": "P-1512.07725", "kind": "paper", "title": "Walks", "year": 2015,
                                             "authors": ["Yang, Lei"], "arxiv": "1512.07725", "session": "S1"})
    toy.draft(result("CL-S1-1"))
    names = ("INDEX.md", "references.bib")
    regenerate(toy.root)
    first = {name: (toy.root / name).read_text() for name in names}
    for name in names:
        (toy.root / name).unlink()
    regenerate(toy.root)
    assert first == {name: (toy.root / name).read_text() for name in names}
    assert "@misc{yang2015," in first["references.bib"] and "paperid = {P-1512.07725}" in first["references.bib"]


def test_established_means_a_result_of_the_draft(toy):
    toy.card("CL-S1-1")
    toy.card("CL-S1-2")
    confirmed(toy, "CL-S1-1")
    ws = Workspace(toy.root)
    assert ws.status("CL-S1-1") == "working"
    toy.draft(result("CL-S1-1"), conjecture("CL-S1-2"), "% \\begin{result}\\card{CL-S1-2}\\end{result}")
    ws = Workspace(toy.root)
    assert ws.status("CL-S1-1") == "established"
    assert ws.status("CL-S1-2") == "working" and ws.in_draft("CL-S1-2") == "conjecture"  # comments do not count
    toy.card("CL-S2-1", supersedes=["CL-S1-1"])
    assert Workspace(toy.root).status("CL-S1-1") == "revised"
    toy.card("DE-S2-1", kind="dead-end", refutes=["CL-S1-1"])
    ws = Workspace(toy.root)
    assert ws.status("CL-S1-1") == "refuted"
    assert any("CL-S1-1" in flag and "refuted by DE-S2-1" in flag for flag in ws.draft_flags())


def test_evidence_from_artefacts_reviews_and_human_verifications(toy):
    toy.card("CL-S3-2")
    toy.card("CL-S7-1")
    toy.derivation("D-S3-2", ["CL-S3-2"])
    toy.review("D-S3-2_R-S3-1", "confirmed", ["CL-S3-2"])
    toy.review("D-S3-2_R-S7-1", "confirmed", ["CL-S7-1"])  # attaches D-S3-2 to a later claim
    toy.computation("C-S5-1", ["CL-S3-2"])
    toy.review("C-S5-1_R-S8-1", "confirmed", ["CL-S3-2"], human="lead")  # the researcher checked it by hand
    ws = Workspace(toy.root)

    ev = ws.evidence("CL-S3-2")
    assert [e.artefact for e in ev] == ["C-S5-1", "D-S3-2"]
    assert [r.id for r in ev[0].reviews] == ["C-S5-1_R-S8-1"] and ev[0].confirmed
    assert [r.id for r in ev[1].reviews] == ["D-S3-2_R-S3-1"]

    ev = ws.evidence("CL-S7-1")
    assert ev[0].artefact == "D-S3-2" and ev[0].attached_by == "D-S3-2_R-S7-1"
    assert [r.id for r in ev[0].reviews] == ["D-S3-2_R-S7-1"]


def test_result_problems(toy):
    toy.card("CL-S1-1")
    toy.card("DE-S1-1", kind="dead-end")
    ws = Workspace(toy.root)
    assert any("no supporting artefact" in r for r in result_problems(ws, "CL-S1-1"))
    assert any("only claims" in r for r in result_problems(ws, "DE-S1-1"))
    assert any("no card" in r for r in result_problems(ws, "CL-S9-9"))
    confirmed(toy, "CL-S1-1")
    assert result_problems(Workspace(toy.root), "CL-S1-1") == []
    toy.card("DE-S2-1", kind="dead-end", refutes=["CL-S1-1"])
    assert any("refuted" in r for r in result_problems(Workspace(toy.root), "CL-S1-1"))


def test_bib_keys_are_stable(toy):
    def paper(pid, session, author="Yang, Lei"):
        toy.write(f"literature/{pid}.md", {"id": pid, "kind": "paper", "title": pid, "year": 2015,
                                           "authors": [author], "session": session})

    paper("P-1601.00002", "S1")
    paper("P-1601.00001", "S1", "Müller, Jörg")
    assert bib_keys(Workspace(toy.root)) == {"P-1601.00002": "yang2015", "P-1601.00001": "muller2015"}
    paper("P-1501.00001", "S2")  # a later session adds a paper with the same key and a smaller ID
    keys = bib_keys(Workspace(toy.root))
    assert keys["P-1601.00002"] == "yang2015" and keys["P-1501.00001"] == "yang2015b"


def test_check_accepts_a_clean_workspace(toy):
    build_chain(toy)
    confirmed(toy, "CL-S1-1")
    toy.draft(result("CL-S1-1"))
    report = run_checks(Workspace(toy.root))
    assert report.errors == [], report.problems


def test_check_finds_header_and_reference_errors(toy):
    toy.card("CL-S1-1", depends_on=["CL-S9-9"])
    toy.card("CL-S1-2", kind="dead-end")
    toy.card("DE-S1-1", kind="dead-end", supersedes=["CL-S1-1"])
    toy.card("Q-S1-1", kind="question")
    toy.derivation("D-S1-1", ["CL-S1-7"])
    report = run_checks(Workspace(toy.root))
    messages = [str(p) for p in report.problems]
    assert any("CL-S9-9, which does not exist" in m for m in messages)
    assert any("does not match the ID prefix" in m for m in messages)
    assert any("supersedes is only allowed on claim" in m for m in messages)
    assert any("Q-S1-1" in m and "not a card ID" in m for m in messages)
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


def test_a_session_corrects_its_own_cards(toy):
    toy.git_init()
    base = toy.commit("base")
    toy.card("CL-S2-1")
    toy.commit("[S2] first wording")
    toy.card("CL-S2-1", statement="corrected wording, in the same session")
    assert run_checks(Workspace(toy.root), base=base, session="S2").errors == []


def test_check_warns_about_long_statements(toy):
    toy.card("CL-S1-1", statement="One sentence. " * 30)
    [warning] = [p for p in run_checks(Workspace(toy.root)).problems if "characters long" in p.message]
    assert warning.severity == "warning" and warning.path == "claims/CL-S1-1.md"


def test_session_rules_apply_to_the_sessions_own_commits(toy):
    toy.card("CL-S1-1")
    toy.debrief("S1", DEBRIEF.format(s="S1"))
    (toy.root / "literature/seeds.md").write_text("# Seeds\n")
    toy.git_init()
    base = toy.commit("base")
    # The researcher answers the S1 debrief while S2 runs (local mode, same branch): that is theirs.
    (toy.root / "sessions/S1/debrief.md").write_text(DEBRIEF.format(s="S1").replace("> **Note:**", "> **Note:** hi"))
    toy.commit("Researcher's edits")
    assert run_checks(Workspace(toy.root), base=base, session="S2").errors == []
    # The session itself touches another session's folder, the seeds, project.toml and a foreign ID.
    (toy.root / "sessions/S1/log.md").write_text("tampered\n")
    (toy.root / "literature/seeds.md").write_text("# Seeds\n\n2301.01234\n")
    toy.card("CL-S4-1")
    (toy.root / ".physics-hive").mkdir()
    (toy.root / ".physics-hive/VERSION").write_text("x\n")
    toy.commit("[S2] tamper")
    messages = [str(e) for e in run_checks(Workspace(toy.root), base=base, session="S2").errors]
    assert any("sessions/S1/log.md" in m and "belongs to session S1" in m for m in messages)
    assert any("literature/seeds.md" in m and "only the researcher" in m for m in messages)
    assert any("CL-S4-1" in m and "belongs to S4" in m for m in messages)
    assert any(".physics-hive/VERSION" in m for m in messages)
    assert not any("sessions/S1/debrief.md" in m for m in messages)


def test_check_on_the_draft_blames_only_the_session(toy):
    toy.card("CL-S1-1")
    toy.card("CL-S1-2")
    confirmed(toy, "CL-S1-1")
    toy.git_init()
    # The researcher puts an unreviewed claim in the draft as a result: a warning, never the session's error.
    toy.draft(result("CL-S1-2"))
    base = toy.commit("Researcher's edit of the draft")
    report = run_checks(Workspace(toy.root), base=base, session="S2")
    assert report.errors == [] and any("CL-S1-2" in p.message for p in report.problems)
    # A session copies a reviewed result: fine. An unreviewed one, or an unknown card: errors.
    toy.draft(result("CL-S1-2"), result("CL-S1-1"))
    toy.commit("[S2] apply the lines ticked in the S1 debrief")
    assert run_checks(Workspace(toy.root), base=base, session="S2").errors == []
    toy.card("CL-S2-1")
    toy.draft(result("CL-S1-2"), result("CL-S1-1"), result("CL-S2-1"), conjecture("CL-S9-9"))
    toy.commit("[S2] copy more")
    messages = [e.message for e in run_checks(Workspace(toy.root), base=base, session="S2").errors]
    assert any("CL-S2-1" in m and "copy it as a conjecture" in m for m in messages)
    assert any("CL-S9-9" in m and "does not exist" in m for m in messages)
    assert not any("CL-S1-2" in m for m in messages)


def test_check_on_notes_and_debriefs(toy):
    toy.card("CL-S2-1")
    toy.git_init()
    base = toy.commit("base")
    (toy.root / "sessions/S2").mkdir(parents=True)
    (toy.root / "sessions/S2/note.tex").write_text("\\begin{result}x\\card{CL-S2-1}\\card{CL-S2-7}\\end{result}\n")
    toy.debrief("S2", "Summary.\n\n**Question 1.** Without an answer line?\n\n- [ ] A line.\n")
    toy.commit("[S2] note and debrief")
    messages = [e.message for e in run_checks(Workspace(toy.root), base=base, session="S2").errors]
    assert any("CL-S2-7" in m for m in messages)
    assert any("question 1 has no answer line" in m for m in messages)
    assert any("no note box" in m for m in messages)
