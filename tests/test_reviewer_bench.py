"""Tests of the reviewer benchmark (bench/reviewer/): the cases are well-formed and paired,
the scoring reads review files correctly, and a dry run scores every case end to end.

No model is called: the dry run replaces the harness with a fake reviewer.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from cards import split_front_matter

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "bench" / "reviewer"
CASES = sorted(p for p in (BENCH / "cases").iterdir() if (p / "case.toml").is_file())

spec = importlib.util.spec_from_file_location("reviewer_bench", BENCH / "run.py")
bench = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bench
spec.loader.exec_module(bench)

ARTEFACT_FILES = {"derivation": (".summary.md", ".tex"), "computation": (".md", ".py", ".out")}


def load(case_dir: Path) -> dict:
    return tomllib.loads((case_dir / "case.toml").read_text(encoding="utf-8"))


# ----- the cases -----


@pytest.mark.parametrize("case_dir", CASES, ids=[c.name for c in CASES])
def test_case_is_well_formed(case_dir):
    meta = load(case_dir)
    assert meta["label"] in ("correct", "planted")
    assert re.fullmatch(r"(D|C)-S\d+-\d+", meta["artefact"])
    for field in ("claim", "problem", "conventions"):
        assert isinstance(meta.get(field), str) and meta[field].strip(), field
    planted_fields = ("error", "location", "severity")
    if meta["label"] == "planted":
        for field in planted_fields:
            assert isinstance(meta.get(field), str) and meta[field].strip(), field
        assert meta["severity"] in ("breaks the result", "weakens it")
        assert any(bench.refs(meta["location"])), "location must name an equation or a line"
    else:
        assert not any(field in meta for field in planted_fields)

    artefact = meta["artefact"]
    kind = "derivation" if artefact.startswith("D-") else "computation"
    for suffix in ARTEFACT_FILES[kind]:
        path = case_dir / f"{artefact}{suffix}"
        assert path.is_file() and path.read_text(encoding="utf-8").strip(), path.name
    for path in case_dir.iterdir():
        assert path.name == "case.toml" or path.name.startswith(artefact + "."), f"unexpected file {path.name}"

    summary = case_dir / f"{artefact}{ARTEFACT_FILES[kind][0]}"
    head, body = split_front_matter(summary.read_text(encoding="utf-8"))
    assert head["id"] == artefact
    assert head["kind"] == kind
    assert head["supports"] and all(re.fullmatch(r"CL-S\d+-\d+", s) for s in head["supports"])
    assert set(head) == {"id", "kind", "supports"}, "the summary header carries no authorship"
    for heading in ("## Summary", "## Result", "## Flags"):
        assert heading in body

    # Nothing in what the reviewer receives may give the case away.
    for path in case_dir.iterdir():
        if path.name != "case.toml":
            text = path.read_text(encoding="utf-8").lower()
            assert "planted" not in text and "benchmark" not in text, path.name


def test_cases_are_balanced_pairs():
    metas = {c.name: load(c) for c in CASES}
    labels = [m["label"] for m in metas.values()]
    assert labels.count("correct") == labels.count("planted") >= 5
    pairs: dict[str, list[tuple[Path, dict]]] = {}
    for case_dir in CASES:
        pairs.setdefault(metas[case_dir.name]["pair"], []).append((case_dir, metas[case_dir.name]))
    for name, members in pairs.items():
        assert sorted(m["label"] for _, m in members) == ["correct", "planted"], name
        (dir_a, a), (dir_b, b) = members
        for field in ("artefact", "problem", "conventions", "field"):
            assert a[field] == b[field], f"{name}: {field} differs"
        assert a["claim"] != b["claim"], f"{name}: the planted claim must state the wrong result"
        assert {p.name for p in dir_a.iterdir()} == {p.name for p in dir_b.iterdir()}, name
    computations = [m for m in metas.values() if m["artefact"].startswith("C-")]
    assert len(computations) >= 2


# ----- scoring -----


def write_review(ws: Path, case, verdict: str, remarks: str = "No issue found.", name: str | None = None) -> None:
    path = ws / case.subdir / (name or f"{case.artefact}_R-S1-1.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: x\nkind: review\ntarget: {case.artefact}\nsupports: [CL-S1-1]\nclaim: 'c'\nverdict: {verdict}\n"
        f"by: {{kind: agent}}\nsession: S1\ndate: 2026-10-05\n---\n## Summary\n\n## Remarks\n{remarks}\n\n"
        f"## Verdict\n{verdict.capitalize()}: reasons.\n",
        encoding="utf-8",
    )


def test_scoring(tmp_path):
    planted = bench.load_cases(["kapitza-planted"])[0]  # planted at Eq. (9)
    correct = bench.load_cases(["kapitza-correct"])[0]

    def scored(case, *args, **kwargs):
        ws = tmp_path / f"ws{len(list(tmp_path.iterdir()))}"
        ws.mkdir()
        if args:
            write_review(ws, case, *args, **kwargs)
        return bench.score(case, ws)

    row = scored(planted, "refuted", "- [breaks the result] Eq. (10): the factor 1/2 is missing.\n- [cosmetic] Section 2: typo.")
    assert (row["outcome"], row["located"], row["remarks"]["breaks the result"], row["remarks"]["cosmetic"]) == ("caught", True, 1, 1)
    row = scored(planted, "refuted", "- **[Breaks the result]** eq. 3: wrong Lagrangian.")
    assert (row["outcome"], row["located"]) == ("caught", False)
    assert scored(planted, "confirmed")["outcome"] == "missed"
    assert scored(planted, "inconclusive")["outcome"] == "inconclusive"
    assert scored(correct, "refuted", "- [breaks the result] Eq. (4): wrong sign.")["outcome"] == "false alarm"
    assert scored(correct, "confirmed")["outcome"] == "passed"
    assert scored(correct, "Confirmed")["verdict"] == "confirmed"

    row = scored(correct)
    assert (row["review"], row["outcome"], row["verdict"]) == ("missing", "no review", None)
    row = scored(correct, "probably fine")
    assert (row["review"], row["outcome"]) == ("malformed", "no review")
    ws = tmp_path / "broken"
    (ws / "derivations").mkdir(parents=True)
    (ws / "derivations" / "D-S1-1_R-S1-1.md").write_text("---\nverdict: confirmed\n", encoding="utf-8")
    assert bench.score(correct, ws)["review"] == "malformed"
    row = scored(correct, "confirmed", name="D-S1-1_R-S1-2.md")
    assert row["outcome"] == "passed" and "written at" in row["note"]
    ws = tmp_path / "disagree"
    write_review(ws, correct, "refuted")
    path = ws / "derivations" / "D-S1-1_R-S1-1.md"
    path.write_text(path.read_text().replace("Refuted: reasons.", "**Confirmed.** Reasons."), encoding="utf-8")
    assert bench.score(correct, ws)["note"] == "## Verdict says confirmed"
    path.write_text(path.read_text().replace("**Confirmed.** Reasons.", "Refuted: it cannot be confirmed."), encoding="utf-8")
    assert bench.score(correct, ws)["note"] == ""

    rows = [
        {"label": "planted", "verdict": "refuted", "outcome": "caught", "cost_usd": 1.0},
        {"label": "planted", "verdict": "confirmed", "outcome": "missed", "cost_usd": 0.5},
        {"label": "planted", "verdict": None, "outcome": "no review", "cost_usd": None},
        {"label": "correct", "verdict": "refuted", "outcome": "false alarm", "cost_usd": None},
        {"label": "correct", "verdict": "inconclusive", "outcome": "inconclusive", "cost_usd": None},
    ]
    assert bench.summarize(rows) == {"caught": 1, "planted_reviewed": 2, "false_alarms": 1, "correct_reviewed": 2,
                                     "inconclusive": 1, "reviewed": 4, "no_review": 1, "cost_usd": 1.5}
    assert bench.rate(1, 2) == "1/2 (50%)" and bench.rate(0, 0) == "-"


def test_harness_commands(tmp_path):
    for harness in bench.ROLE_FILES:
        cmd = bench.harness_command({"harness": harness, "model": "M", "args": ["--x"]}, "PROMPT", tmp_path)
        assert cmd[0] == harness and cmd[-1] == "PROMPT" and "--x" in cmd
        assert cmd[cmd.index("--model") + 1] == "M"


# ----- end to end, without models -----


def test_dry_run_scores_every_case(tmp_path):
    results = tmp_path / "results"
    proc = subprocess.run([sys.executable, str(BENCH / "run.py"), "--dry-run", "--results-dir", str(results)],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    configs = bench.load_configs()
    assert len({c["harness"] for c in configs}) >= 2

    [result_file] = results.glob("*.json")
    result = json.loads(result_file.read_text())
    assert result["dry_run"] is True
    n_planted = sum(load(c)["label"] == "planted" for c in CASES)
    n_correct = len(CASES) - n_planted
    for config in configs:
        summary = result["summary"][config["label"]]
        assert summary == {"caught": n_planted, "planted_reviewed": n_planted, "false_alarms": 0,
                           "correct_reviewed": n_correct, "inconclusive": 0, "reviewed": len(CASES),
                           "no_review": 0, "cost_usd": None}
        assert f"| {n_planted}/{n_planted} (100%) | 0/{n_correct} (0%) |" in proc.stdout
    assert len(result["results"]) == len(configs) * len(CASES)

    for row in result["results"]:
        assert row["status"] == "dry run" and row["review"] == "ok"
        assert row["outcome"] == ("caught" if row["label"] == "planted" else "passed")
        assert row["located"] is (True if row["label"] == "planted" else None)
        assert Path(row["review_file"]).is_file()
        log = Path(row["log"]).read_text()
        command, prompt = log.split("\n\n", 1)
        assert bench.ROLE_FILES[row["harness"]] in prompt
        assert f"{row['artefact']}_R-S1-1.md" in prompt and "[CL-S1-1]" in prompt
        # The reviewer must not learn the case's name or that it is a test.
        for text in (command, prompt):
            assert row["case"] not in text and "planted" not in text.lower() and "bench" not in text.lower()
        assert "workspace" not in row  # removed without --keep
