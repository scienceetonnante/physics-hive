# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Reviewer benchmark: how often a reviewer configuration catches planted errors, and how
often it raises false alarms on correct work.

Each case in cases/ is a derivation or a computation in the exact format a reviewer receives,
with a case.toml that says whether it is correct or holds one planted error. For each
configuration in configs.toml (harness and model) and each case, the runner creates a fresh
local workspace with scripts/init.py, copies the artefact in and commits it, then runs the
harness non-interactively with a prompt that makes it act as the reviewer role of that harness
on the artefact. It reads the verdict of the review file and scores it: a planted case is
caught when the verdict is `refuted`, and a correct case is a false alarm when it is `refuted`.

A real run calls models and costs money. --dry-run replaces the harness call with a fake
reviewer that refutes every planted case and confirms every correct one, so the pipeline can be
tested for free.

Usage:
  uv run bench/reviewer/run.py [--config LABEL] [--case NAME] [--keep] [--dry-run]
                               [--timeout SECONDS] [--jobs N] [--results-dir DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from cards import VERDICTS, FrontMatterError, dump_front_matter, split_front_matter  # noqa: E402

CASES_DIR = HERE / "cases"
CONFIGS_FILE = HERE / "configs.toml"
RESULTS_DIR = HERE / "results"
SESSION = "S1"
REVIEW_SUFFIX = f"_R-{SESSION}-1"
ROLE_FILES = {
    "claude": ".claude/agents/reviewer.md",
    "codex": ".codex/agents/reviewer.toml",
    "opencode": ".opencode/agents/reviewer.md",
    "pi": ".pi/agents/reviewer.md",
}
SEVERITIES = ("breaks the result", "weakens it", "cosmetic")


# ----- cases and configurations -----


@dataclass
class Case:
    name: str
    folder: Path
    meta: dict  # the content of case.toml

    @property
    def label(self) -> str:
        return self.meta["label"]

    @property
    def artefact(self) -> str:
        return self.meta["artefact"]

    @property
    def kind(self) -> str:
        return "derivation" if self.artefact.startswith("D-") else "computation"

    @property
    def subdir(self) -> str:
        return "derivations" if self.kind == "derivation" else "computations"

    @property
    def files(self) -> list[Path]:
        """The artefact's files: everything in the case folder named after its ID."""
        return sorted(p for p in self.folder.iterdir() if p.name.startswith(self.artefact + "."))

    @property
    def summary(self) -> Path:
        suffix = ".summary.md" if self.kind == "derivation" else ".md"
        return self.folder / f"{self.artefact}{suffix}"

    @property
    def supports(self) -> list[str]:
        meta, _ = split_front_matter(self.summary.read_text(encoding="utf-8"))
        return list(meta.get("supports") or [])

    @property
    def review_path(self) -> str:
        return f"{self.subdir}/{self.artefact}{REVIEW_SUFFIX}.md"


def load_cases(names: list[str] | None = None) -> list[Case]:
    cases = [
        Case(folder.name, folder, tomllib.loads((folder / "case.toml").read_text(encoding="utf-8")))
        for folder in sorted(CASES_DIR.iterdir())
        if (folder / "case.toml").is_file()
    ]
    if names:
        unknown = set(names) - {c.name for c in cases}
        if unknown:
            raise SystemExit(f"ERROR: unknown case(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c.name in names]
    return cases


def load_configs(labels: list[str] | None = None, path: Path = CONFIGS_FILE) -> list[dict]:
    configs = tomllib.loads(path.read_text(encoding="utf-8")).get("config", [])
    for config in configs:
        if config.get("harness") not in ROLE_FILES:
            raise SystemExit(f"ERROR: config {config.get('label')!r}: harness must be one of {', '.join(ROLE_FILES)}")
    if labels:
        unknown = set(labels) - {c["label"] for c in configs}
        if unknown:
            raise SystemExit(f"ERROR: unknown config(s): {', '.join(sorted(unknown))}")
        configs = [c for c in configs if c["label"] in labels]
    return configs


# ----- one review -----


def git(ws: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=ws, check=True, capture_output=True, text=True)


def make_workspace(case: Case, harness: str) -> Path:
    """A fresh local workspace holding the case's artefact, committed as a session leaves it.

    The folder name is neutral: the reviewer sees its working directory, so it must not
    give away the case name or the fact that this is a benchmark.
    """
    ws = Path(tempfile.mkdtemp(prefix="physics-")) / "workspace"
    init = [sys.executable, str(REPO / "scripts" / "init.py"), "--mode", "local", "--harness", harness, "--dir", str(ws), "--yes"]
    proc = subprocess.run(init, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"init.py failed: {proc.stderr.strip() or proc.stdout.strip()}")
    problem = case.meta["problem"].strip()
    title = problem.splitlines()[0].lstrip("# ").strip()
    (ws / "project.md").write_text(f"# {title}\n\n## Goal\n\n{problem}\n\n## The question in full\n\n{problem}\n",
                                   encoding="utf-8")
    (ws / "conventions.md").write_text(case.meta["conventions"].strip() + "\n", encoding="utf-8")
    git(ws, "add", "project.md", "conventions.md")
    git(ws, "commit", "-q", "-m", "Write the problem and conventions")
    for path in case.files:
        shutil.copy2(path, ws / case.subdir / path.name)
    verb = "derive" if case.kind == "derivation" else "compute"
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", f"[{SESSION}] {verb}({case.artefact}): add the {case.kind}")
    return ws


def dispatch_prompt(case: Case, harness: str) -> str:
    """The reviewer's dispatch, as /review would pass it (blind: nothing about the author)."""
    where = " (the instructions are its developer_instructions)" if harness == "codex" else ""
    files = ", ".join(f"{case.subdir}/{p.name}" for p in case.files)
    claim = case.meta["claim"].strip()
    return (
        "You are the reviewer sub-agent of this PhysicsHive workspace, not its coordinator. "
        f"Read your role file, {ROLE_FILES[harness]}{where}, and follow it exactly. Do the review "
        "yourself in this conversation: do not dispatch sub-agents, start a session or commit.\n\n"
        "Dispatch:\n"
        f"- Target: {case.artefact} ({files})\n"
        f"- Statement of the claim under review: '{claim}'\n"
        f"- Card IDs to record in supports: [{', '.join(case.supports)}]\n"
        f"- Output path: {case.review_path}\n"
        f"- Session: {SESSION}\n"
        "- Conventions: conventions.md\n"
    )


def harness_command(config: dict, prompt: str, ws: Path) -> list[str]:
    """The non-interactive command line of each harness. Flags checked against each CLI's --help."""
    model, extra = config["model"], [str(a) for a in config.get("args", [])]
    harness = config["harness"]
    if harness == "claude":
        # A non-interactive run cannot answer permission prompts: allow exactly what a reviewer
        # needs (files, and Python for its spot checks) and deny the rest without asking.
        return ["claude", "-p", "--model", model, "--permission-mode", "dontAsk",
                "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash(uv run:*),Bash(python:*),Bash(python3:*)",
                "--output-format", "json", *extra, prompt]
    if harness == "codex":
        return ["codex", "exec", "--model", model, "--sandbox", "workspace-write",
                "-c", "sandbox_workspace_write.network_access=true", "--cd", str(ws), *extra, prompt]
    if harness == "opencode":
        return ["opencode", "run", "--model", model, "--dir", str(ws), "--auto", *extra, prompt]
    return ["pi", "-p", "--model", model, *extra, prompt]


def run_harness(cmd: list[str], ws: Path, timeout: float, log) -> str:
    """Run the harness in the workspace, its output going to the log. Returns a status."""
    proc = subprocess.Popen(cmd, cwd=ws, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)  # the harness may have started child processes
        proc.wait()
        return "timeout"
    return "ok" if proc.returncode == 0 else f"exit {proc.returncode}"


def fake_review(case: Case, ws: Path) -> None:
    """Dry run: write the review a perfect reviewer would write, from the case's label."""
    planted = case.label == "planted"
    verdict = "refuted" if planted else "confirmed"
    meta = {
        "id": f"{case.artefact}{REVIEW_SUFFIX}",
        "kind": "review",
        "target": case.artefact,
        "supports": case.supports,
        "claim": case.meta["claim"].strip(),
        "verdict": verdict,
        "by": {"kind": "agent"},
        "session": SESSION,
        "date": dt.date.today().isoformat(),
    }
    remark = f"- [breaks the result] {case.meta['location']}: dry run." if planted else "No issue found."
    body = (
        f"## Summary\nReviewed {case.artefact}. Verdict: {verdict}. Wrote {case.review_path}.\n\n"
        "## Result\nDry run: no model was called.\n\n## Flags\n- (none)\n\n"
        "## Tests\n| Check | Outcome | Detail |\n|---|---|---|\n| dry run | could not run | no model was called |\n\n"
        f"## Remarks\n{remark}\n\n## Verdict\n{verdict}: dry run.\n"
    )
    (ws / case.review_path).write_text(dump_front_matter(meta, body), encoding="utf-8")


# ----- scoring -----


def section(body: str, title: str) -> str:
    """The text under a `## title` heading, up to the next `## ` heading."""
    match = re.search(rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S | re.I)
    return match.group(1) if match else ""


def remarks(body: str) -> list[tuple[str, str]]:
    """(severity, text) for each bullet of `## Remarks` that names a severity."""
    found = []
    for item in re.split(r"^\s*(?:[-*]|\d+\.)\s+", section(body, "Remarks"), flags=re.M)[1:]:
        match = re.search("|".join(SEVERITIES), item[:80], re.I)
        if match:
            found.append((match.group(0).lower(), item.strip()))
    return found


def refs(text: str) -> tuple[set[int], set[int]]:
    """Equation and line numbers a text points to, as in 'Eq. (9)', '(10)' or 'line 27'."""
    eqs = {int(n) for n in re.findall(r"\((\d{1,3})\)", text)}
    eqs |= {int(n) for n in re.findall(r"\beq(?:uation)?s?\.?\s*\(?(\d{1,3})", text, re.I)}
    lines = {int(n) for n in re.findall(r"\blines?\s*(\d{1,4})", text, re.I)}
    return eqs, lines


def near_location(location: str, texts: list[str]) -> bool:
    """Whether any text points within one equation or three lines of the planted location."""
    eqs, lines = refs(location)
    for text in texts:
        found_eqs, found_lines = refs(text)
        if any(abs(a - b) <= 1 for a in eqs for b in found_eqs):
            return True
        if any(abs(a - b) <= 3 for a in lines for b in found_lines):
            return True
    return False


def outcome(label: str, verdict: str | None) -> str:
    if verdict is None:
        return "no review"
    if verdict == "inconclusive":
        return "inconclusive"
    if label == "planted":
        return "caught" if verdict == "refuted" else "missed"
    return "false alarm" if verdict == "refuted" else "passed"


def score(case: Case, ws: Path) -> dict:
    """Read the review file of a case and score it."""
    row = {"review": "ok", "verdict": None, "note": "", "review_file": None}
    path = ws / case.review_path
    if not path.is_file():
        # A review written next to the target under another name still counts, with a note.
        others = sorted((ws / case.subdir).glob(f"{case.artefact}_R-*.md"))
        if len(others) != 1:
            row.update(review="missing", outcome="no review")
            return row
        path = others[0]
        row["note"] = f"written at {path.relative_to(ws)}"
    row["review_file"] = path
    try:
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    except (FrontMatterError, UnicodeDecodeError) as exc:
        row.update(review="malformed", outcome="no review", note=str(exc))
        return row
    verdict = str(meta.get("verdict", "")).strip().lower()
    if verdict not in VERDICTS:
        row.update(review="malformed", outcome="no review", note=f"verdict field is {meta.get('verdict')!r}")
        return row
    # Compare with the verdict section only when it opens with a verdict word ("**Refuted.** ...").
    stated = re.match(rf"[\s*_]*({'|'.join(VERDICTS)})\b", section(body, "Verdict"), re.I)
    if stated and stated.group(1).lower() != verdict:
        row["note"] = (row["note"] + "; " if row["note"] else "") + f"## Verdict says {stated.group(1).lower()}"
    found = remarks(body)
    counts = {s: sum(1 for sev, _ in found if sev == s) for s in SEVERITIES}
    breaks = [text for sev, text in found if sev == "breaks the result"]
    located = near_location(case.meta["location"], breaks) if case.label == "planted" and breaks else None
    row.update(verdict=verdict, outcome=outcome(case.label, verdict), remarks=counts, located=located)
    return row


def cost_from_log(text: str) -> float | None:
    """Claude Code's JSON output reports the cost of the call; other harnesses do not."""
    match = re.search(r'"total_cost_usd"\s*:\s*([0-9.eE+-]+)', text)
    return float(match.group(1)) if match else None


def review_one(config: dict, case: Case, args, out_dir: Path) -> dict:
    """Create the workspace, run the reviewer, score the review, and keep its traces in out_dir."""
    harness = config["harness"]
    row = {"config": config["label"], "harness": harness, "model": config["model"], "case": case.name,
           "pair": case.meta.get("pair"), "field": case.meta.get("field"), "label": case.label,
           "artefact": case.artefact, "error_kind": case.meta.get("error_kind"), "cost_usd": None}
    start = time.monotonic()
    ws = make_workspace(case, harness)
    prompt = dispatch_prompt(case, harness)
    cmd = harness_command(config, prompt, ws)
    log_path = out_dir / config["label"] / f"{case.name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {shlex.join(cmd[:-1])} <prompt>\n\n{prompt}\n--- output ---\n")
        log.flush()
        if not (ws / ROLE_FILES[harness]).is_file():
            status = f"missing role file {ROLE_FILES[harness]}"
        elif args.dry_run:
            fake_review(case, ws)
            status = "dry run"
        else:
            status = run_harness(cmd, ws, args.timeout, log)
    row["status"] = status
    row["seconds"] = round(time.monotonic() - start, 1)
    row["cost_usd"] = cost_from_log(log_path.read_text(encoding="utf-8", errors="replace"))
    row.update(score(case, ws))
    if row["review_file"]:
        shutil.copy2(row["review_file"], log_path.with_suffix(".review.md"))
    row["review_file"] = str(log_path.with_suffix(".review.md")) if row["review_file"] else None
    row["log"] = str(log_path)
    if args.keep:
        row["workspace"] = str(ws)
    else:
        shutil.rmtree(ws.parent, ignore_errors=True)
    return row


# ----- report -----


def rate(k: int, n: int) -> str:
    return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "-"


def summarize(rows: list[dict]) -> dict:
    reviewed = [r for r in rows if r["verdict"]]
    planted = [r for r in reviewed if r["label"] == "planted"]
    correct = [r for r in reviewed if r["label"] == "correct"]
    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    return {
        "caught": sum(r["outcome"] == "caught" for r in planted),
        "planted_reviewed": len(planted),
        "false_alarms": sum(r["outcome"] == "false alarm" for r in correct),
        "correct_reviewed": len(correct),
        "inconclusive": sum(r["outcome"] == "inconclusive" for r in reviewed),
        "reviewed": len(reviewed),
        "no_review": len(rows) - len(reviewed),
        "cost_usd": round(sum(costs), 4) if costs else None,
    }


def markdown(config: dict, rows: list[dict], s: dict) -> str:
    cost = f"{s['cost_usd']:.2f}" if s["cost_usd"] is not None else "-"
    lines = [
        f"## {config['label']} ({config['harness']}, {config['model']})",
        "",
        "| Catch rate | False-alarm rate | Inconclusive | No valid review | Cost (USD) |",
        "|---|---|---|---|---|",
        f"| {rate(s['caught'], s['planted_reviewed'])} | {rate(s['false_alarms'], s['correct_reviewed'])} "
        f"| {rate(s['inconclusive'], s['reviewed'])} | {s['no_review']} | {cost} |",
        "",
        "| Case | Label | Verdict | Outcome | Breaks / weakens / cosmetic | Near planted location | Time (s) | Note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        counts = r.get("remarks") or {}
        severities = " / ".join(str(counts.get(s, "-")) for s in SEVERITIES) if counts else "-"
        located = {True: "yes", False: "no", None: "-"}[r.get("located")]
        note = "; ".join(x for x in (r["status"] if r["status"] not in ("ok", "dry run") else "",
                                     r["review"] if r["review"] != "ok" else "", r["note"]) if x)
        lines.append(f"| {r['case']} | {r['label']} | {r['verdict'] or '-'} | {r['outcome']} | {severities} "
                     f"| {located} | {r['seconds']:.0f} | {note} |")
    return "\n".join(lines) + "\n"


# ----- entry point -----


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", action="append", help="run only this configuration (repeatable)")
    parser.add_argument("--case", action="append", help="run only this case (repeatable)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary workspaces")
    parser.add_argument("--dry-run", action="store_true", help="use a fake reviewer instead of the harness")
    parser.add_argument("--timeout", type=float, default=1800, help="seconds allowed per review (default 1800)")
    parser.add_argument("--jobs", type=int, default=1, help="reviews to run in parallel (default 1)")
    parser.add_argument("--configs-file", type=Path, default=CONFIGS_FILE, help=argparse.SUPPRESS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help="where to save results")
    args = parser.parse_args()

    configs = load_configs(args.config, args.configs_file)
    cases = load_cases(args.case)
    if not configs or not cases:
        raise SystemExit("ERROR: nothing to run (no configuration or no case selected)")
    if not args.dry_run:
        missing = sorted({c["harness"] for c in configs if not shutil.which(c["harness"])})
        if missing:
            raise SystemExit(f"ERROR: harness not found on PATH: {', '.join(missing)}")

    started = dt.datetime.now(dt.timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + ("-dry-run" if args.dry_run else "")
    out_dir = args.results_dir / run_id
    tasks = [(config, case) for config in configs for case in cases]
    print(f"{len(tasks)} reviews ({len(configs)} configurations x {len(cases)} cases)"
          f"{', dry run' if args.dry_run else ''}. Logs in {out_dir}", flush=True)

    done, lock = [0], threading.Lock()

    def work(task):
        config, case = task
        try:
            row = review_one(config, case, args, out_dir)
        except Exception as exc:  # a broken workspace must not stop the other reviews
            row = {"config": config["label"], "harness": config["harness"], "model": config["model"],
                   "case": case.name, "label": case.label, "artefact": case.artefact, "status": f"error: {exc}",
                   "seconds": 0.0, "cost_usd": None, "review": "missing", "verdict": None,
                   "outcome": "no review", "note": "", "review_file": None}
        with lock:
            done[0] += 1
            print(f"[{done[0]}/{len(tasks)}] {row['config']} {row['case']}: {row['verdict'] or row['status']}"
                  f" ({row['outcome']}), {row['seconds']:.0f} s", flush=True)
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = list(pool.map(work, tasks))

    print()
    summaries = {}
    for config in configs:
        config_rows = [r for r in rows if r["config"] == config["label"]]
        summaries[config["label"]] = summarize(config_rows)
        print(markdown(config, config_rows, summaries[config["label"]]))

    result = {
        "run": run_id,
        "started": started.isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "method_version": (REPO / "VERSION").read_text().strip(),
        "configs": configs,
        "summary": summaries,
        "results": rows,
    }
    args.results_dir.mkdir(parents=True, exist_ok=True)
    out_file = args.results_dir / f"{run_id}.json"
    out_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Raw results saved to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
