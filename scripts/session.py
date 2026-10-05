# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "huggingface_hub>=1.0"]
# ///
"""Open, follow and close a research session.

Subcommands:
  start --harness H --model M   Open a session. Refuses if the checkout has uncommitted
                                changes or a session is already active. Shared mode: opens a
                                draft pull request (its number is the session number) and
                                moves the checkout to the session's branch. Local mode: takes
                                the next free number in sessions/. Prints what is waiting.
  status                        Where the active session stands, and what is waiting.
  next <CL|Q|DE|D|C|CR>         Print the next free ID of that prefix in the active session.
  next review <artefact>        Print the path of the next review file of that artefact.
  brief                         Commit sessions/S<n>/brief.md; shared mode: push it and copy
                                it to the pull request.
  end [--no-merge]              Run check. Shared mode: rebase on main if needed, push, upload
                                sources and the trace, mark the pull request ready and merge it.
  abort                         Abandon the active session.

Usage: uv run .physics-intern/scripts/session.py <subcommand> [options]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import Workspace, find_root, natural_key, split_front_matter  # noqa: E402
from check import run_checks  # noqa: E402
from common import (  # noqa: E402
    ScriptError,
    clear_active,
    detect_harness,
    dirty_paths,
    git,
    git_out,
    is_git_repo,
    load_active,
    now_iso,
    operator_name,
    rendered_version,
    rerender,
    save_active,
    say,
)
from regen import regenerate  # noqa: E402

PREFIX_FOLDERS = {"CL": "claims", "Q": "claims", "DE": "claims", "D": "derivations", "C": "computations", "CR": "critiques"}
CARD_ID_RE = re.compile(r"\b(?:CL|Q|DE)-[A-Za-z0-9._-]+\b")

LOG_TEMPLATE = """# Session {id} log

Started {started} by {operator} with {harness} ({model}).

## Dispatches

## Flag dispositions

## Notes
"""


def require_active(root: Path) -> dict:
    active = load_active(root)
    if not active:
        raise ScriptError("no session is active in this checkout; start one with `session.py start`")
    return active


def problem_is_empty(root: Path) -> bool:
    path = root / "problem.md"
    if not path.is_file():
        return True
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return not text.strip()


# ----- what is waiting -----


def last_commit_adding(root: Path, pathspec: str) -> str | None:
    out = git(root, "log", "-1", "--format=%H", "--diff-filter=A", "--", pathspec, check=False).stdout.strip()
    return out or None


def last_commit_touching(root: Path, path: str) -> str | None:
    out = git(root, "log", "-1", "--format=%H", "--", path, check=False).stdout.strip()
    return out or None


def files_added_since(root: Path, commit: str | None, *paths: str) -> set[str]:
    rng = [f"{commit}..HEAD"] if commit else ["HEAD"]
    out = git(root, "log", "--diff-filter=A", "--name-only", "--format=", *rng, "--", *paths, check=False).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def waiting_items(ws: Workspace, root: Path) -> list[tuple[str, list[str]]]:
    """Sections of the 'what is waiting' list printed by start and status."""
    sections: list[tuple[str, list[str]]] = []

    open_q = [c for c in ws.sorted_cards("question") if ws.status(c.id) == "open"]
    sections.append(("Open questions", [f"{c.id}: {one_line(c.statement)}" for c in open_q]))

    recheck = []
    for card in ws.sorted_cards():
        causes = ws.needs_recheck(card.id)
        if causes and ws.status(card.id) not in ("refuted", "revised"):
            recheck.append(f"{card.id}: depends on " + ", ".join(f"{c} ({ws.status(c)})" for c in causes))
    sections.append(("Needs re-check", recheck))

    people: list[str] = []
    if is_git_repo(root):
        since = last_commit_adding(root, "sessions/*/report.md")
        added = files_added_since(root, since, "claims", "feedback")
        for reaction in ws.reactions:
            if reaction.path in added:
                comment = f': "{one_line(reaction.comment, 120)}"' if reaction.comment else ""
                people.append(f"reaction {reaction.value} on {reaction.target} by {reaction.user}{comment}")
        for review in ws.reviews.values():
            if review.path in added and review.by_human:
                people.append(
                    f"verification {review.id} of {', '.join(review.supports)} by {review.by.get('user')}: {review.verdict}"
                )
        for promotion in ws.promotions:
            if promotion.path in added:
                who = promotion.by.get("user") or "an agent"
                people.append(f"promotion of {promotion.target} by {who}")
        for card in ws.sorted_cards():
            if card.path in added and card.produced_by.get("kind") == "human":
                people.append(f"{card.kind} card {card.id} by {card.produced_by.get('user')}: {one_line(card.statement)}")
    sections.append(("New from people since the last session", sorted(people)))

    proposals = []
    if is_git_repo(root):
        since_plan = last_commit_touching(root, "plan.md")
        reports = files_added_since(root, since_plan, "sessions")
        for session in sorted(ws.sessions.values(), key=lambda s: s.number):
            if f"{session.path}/report.md" not in reports:
                continue
            text = session.report_sections.get("Proposed plan changes", "").strip()
            if text and text.lower().strip("-() .") not in ("none", ""):
                proposals.append(f"from {session.id}: " + one_line(text, 400))
    sections.append(("Plan-change proposals not yet taken into plan.md", proposals))

    pending = []
    for session in sorted(ws.sessions.values(), key=lambda s: s.number):
        text = session.report_sections.get("Proposed promotions", "")
        for card_id in sorted(set(CARD_ID_RE.findall(text)), key=natural_key):
            if card_id in ws.cards and ws.status(card_id) == "working":
                pending.append(f"{card_id} (proposed in {session.id})")
    sections.append(("Promotions proposed but not recorded", pending))
    return sections


def one_line(text: str, limit: int = 200) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def print_waiting(ws: Workspace, root: Path, active: dict) -> None:
    sections = waiting_items(ws, root)
    if ws.mode == "shared":
        import hub

        sections += hub.shared_waiting(ws, root, active)
    say("What is waiting:")
    for title, items in sections:
        say("")
        say(f"{title} ({len(items)}):")
        for item in items or ["(none)"]:
            say(f"- {item}")
    say("")
    if problem_is_empty(root):
        say("WARNING: problem.md is still the empty template; the lead must state the question first.")
    else:
        say("problem.md states a question.")


# ----- subcommands -----


def cmd_start(root: Path, args) -> None:
    active = load_active(root)
    if active:
        raise ScriptError(
            f"session {active['id']} is already active in this checkout (started {active['started']}). "
            "Finish it with `session.py end` or abandon it with `session.py abort`. "
            "To run two sessions at once, join the space a second time in another folder."
        )
    if not is_git_repo(root):
        raise ScriptError("the workspace is not a git repository")
    dirty = dirty_paths(root)
    if dirty:
        listing = ", ".join(dirty[:8]) + (", …" if len(dirty) > 8 else "")
        raise ScriptError(f"the checkout has uncommitted changes ({listing}); commit or discard them first")
    if problem_is_empty(root):
        raise ScriptError(
            "problem.md is still the empty template. State the question and its definition of done first: "
            "edit problem.md, or ask the coordinator to write it with you, then commit it (in shared mode a "
            "lead pushes it to main with `uv run .physics-intern/scripts/hubgit.py push origin main`)."
        )
    ws = Workspace(root)
    if ws.mode == "local":
        refuse_if_stale(root, (root / ".physics-intern" / "VERSION").read_text().strip())
    harness = args.harness or detect_harness()
    model = args.model or "unknown"
    info = {"mode": ws.mode, "harness": harness, "model": model, "started": now_iso()}

    if ws.mode == "shared":
        import hub

        info.update(hub.open_session(ws, root, harness, model))
    else:
        numbers = [s.number for s in ws.sessions.values()]
        number = max(numbers, default=0) + 1
        info.update(
            id=f"S{number}",
            number=number,
            operator=operator_name(root),
            branch=git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            base=git_out(root, "rev-parse", "HEAD"),
        )
    folder = root / "sessions" / info["id"]
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "log.md"
    if not log.exists():
        log.write_text(LOG_TEMPLATE.format(**info), encoding="utf-8")
    save_active(root, info)
    ws = regenerate(root)

    say(f"Session {info['id']} started ({info['mode']} mode).")
    if info.get("pr_url"):
        say(f"Draft pull request #{info['pr']}: {info['pr_url']}")
        say(f"Branch: {info['branch']} (based on main at {info['base'][:12]}).")
    say(f"In cards, use produced_by: {{kind: agent, model: {model}, operator: {info['operator']}}}.")
    say(f"Log: sessions/{info['id']}/log.md. Next: propose a brief to the operator, then write "
        f"sessions/{info['id']}/brief.md and run `session.py brief`.")
    say("")
    print_waiting(ws, root, info)


def refuse_if_stale(root: Path, method: str) -> None:
    """Stop when the harness files were rendered from another method version than `method`."""
    rendered = rendered_version(root)
    if rendered and rendered != method:
        rerender(root)
        raise ScriptError(
            f"the method copy is now version {method}, but this harness was loaded with prompts from {rendered}. "
            "The harness files have just been re-rendered: restart your harness in this folder so that it "
            "loads the new prompts, then start the session again."
        )


def cmd_status(root: Path, args) -> None:
    active = load_active(root)
    ws = Workspace(root)
    if not active:
        say("No session is active in this checkout.")
        print_waiting(ws, root, {})
        return
    folder = root / "sessions" / active["id"]
    log = folder / "log.md"
    dispatches = len(re.findall(r"^\s*-?\s*Dispatch \d+", log.read_text(encoding="utf-8"), flags=re.M)) if log.exists() else 0
    say(f"Session {active['id']} is active ({active['mode']} mode), started {active['started']} by "
        f"{active['operator']} with {active['harness']} ({active['model']}).")
    if active.get("pr_url"):
        say(f"Pull request #{active['pr']}: {active['pr_url']} (branch {active['branch']}).")
    brief = folder / "brief.md"
    if brief.exists():
        meta, _ = split_front_matter(brief.read_text(encoding="utf-8"))
        say(f"Brief: {meta.get('goal', '?')} (budget {meta.get('budget', '?')} dispatches, merge {meta.get('merge', 'auto')}).")
    else:
        say("Brief: not written yet.")
    say(f"Dispatches logged: {dispatches}.")
    say(f"Report: {'written' if (folder / 'report.md').exists() else 'not written yet'}.")
    say("")
    print_waiting(ws, root, active)


def cmd_next(root: Path, args) -> None:
    active = require_active(root)
    session = active["id"]
    texts = []
    for folder in (root / "sessions" / session, root / "derivations" / ".briefs", root / "computations" / ".briefs"):
        if folder.is_dir():
            texts += [p.read_text(encoding="utf-8", errors="ignore") for p in folder.glob("*.md")]
    if args.what == "review":
        if not args.target:
            raise ScriptError("usage: session.py next review <artefact id>")
        target = args.target
        if not re.match(r"^(D|C)-S\d+-\d+$", target):
            raise ScriptError(f"{target} is not an artefact ID (D-S<n>-<k> or C-S<n>-<k>)")
        folder = "derivations" if target.startswith("D-") else "computations"
        pattern = re.compile(rf"{re.escape(target)}_R-{session}-(\d+)\b")
        used = [int(m) for p in (root / folder).glob(f"{target}_R-{session}-*.md") for m in pattern.findall(p.name)]
        used += [int(m) for text in texts for m in pattern.findall(text)]
        say(f"{folder}/{target}_R-{session}-{max(used, default=0) + 1}.md")
        return
    prefix = args.what
    if prefix not in PREFIX_FOLDERS:
        raise ScriptError(f"unknown prefix {prefix!r}; use one of {', '.join(PREFIX_FOLDERS)} or `review <artefact>`")
    pattern = re.compile(rf"(?<![A-Za-z]){prefix}-{session}-(\d+)(?![\d])")
    names = [p.name for p in (root / PREFIX_FOLDERS[prefix]).glob(f"{prefix}-{session}-*")]
    used = [int(m) for name in names for m in pattern.findall(name)]
    used += [int(m) for text in texts for m in pattern.findall(text)]
    say(f"{prefix}-{session}-{max(used, default=0) + 1}")


def cmd_brief(root: Path, args) -> None:
    active = require_active(root)
    folder = root / "sessions" / active["id"]
    brief = folder / "brief.md"
    if not brief.is_file():
        raise ScriptError(f"write {brief.relative_to(root)} first")
    text = brief.read_text(encoding="utf-8")
    meta, _ = split_front_matter(text)
    missing = [key for key in ("goal", "budget") if not meta.get(key)]
    if missing:
        raise ScriptError(f"the brief's front matter needs {', '.join(missing)}")
    git(root, "add", "--", str(folder.relative_to(root)))
    if git(root, "diff", "--cached", "--quiet", check=False).returncode != 0:
        git(root, "commit", "-q", "-m", f"[{active['id']}] brief: {one_line(meta['goal'], 120)}")
    if active["mode"] == "shared":
        import hub

        hub.publish_brief(Workspace(root), root, active, text, str(meta["goal"]))
        say(f"Brief committed and copied to pull request #{active['pr']}.")
    else:
        say("Brief committed.")


def cmd_end(root: Path, args) -> None:
    active = require_active(root)
    folder = root / "sessions" / active["id"]
    if not (folder / "report.md").is_file():
        raise ScriptError(f"write and commit sessions/{active['id']}/report.md before ending the session")
    dirty = dirty_paths(root)
    if dirty:
        raise ScriptError(f"uncommitted changes ({', '.join(dirty[:8])}); commit them before ending the session")
    if active["mode"] == "shared":
        import hub

        hub.end_session(root, active, merge=not args.no_merge, run_check=check_or_fail)
        return
    check_or_fail(root, active["base"], active["id"])
    clear_active(root)
    regenerate(root)
    say(f"Session {active['id']} closed: check passed.")


def check_or_fail(root: Path, base: str, session: str) -> None:
    regenerate(root)
    report = run_checks(Workspace(root), base=base, session=session)
    for problem in sorted(report.problems, key=lambda p: (p.severity != "error", p.path)):
        say(str(problem))
    if report.errors:
        raise ScriptError(f"check found {len(report.errors)} error(s); fix them, commit, and run `session.py end` again")
    say(f"check passed ({len(report.problems)} warning(s)).")


def cmd_abort(root: Path, args) -> None:
    active = require_active(root)
    folder = root / "sessions" / active["id"]
    tracked = git(root, "ls-files", "--", str(folder.relative_to(root)), check=False).stdout.strip()
    if folder.is_dir() and not tracked:
        for path in sorted(folder.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        folder.rmdir()
    if active["mode"] == "shared":
        import hub

        hub.abort_session(root, active)
    clear_active(root)
    regenerate(root)
    say(f"Session {active['id']} abandoned." + ("" if not tracked else f" Its committed files stay in sessions/{active['id']}/."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("--harness", help="claude, codex, opencode or pi (default: detected)")
    p.add_argument("--model", help="the coordinator's model ID")
    sub.add_parser("status")
    p = sub.add_parser("next")
    p.add_argument("what", help="CL, Q, DE, D, C, CR, or review")
    p.add_argument("target", nargs="?", help="with review: the artefact ID")
    sub.add_parser("brief")
    p = sub.add_parser("end")
    p.add_argument("--no-merge", action="store_true", help="shared mode: leave the pull request open for the operator")
    sub.add_parser("abort")
    args = parser.parse_args()
    root = args.root.resolve() if args.root else find_root()
    commands = {"start": cmd_start, "status": cmd_status, "next": cmd_next, "brief": cmd_brief,
                "end": cmd_end, "abort": cmd_abort}
    commands[args.command](root, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
