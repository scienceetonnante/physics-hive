# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "huggingface_hub>=1.0"]
# ///
"""Open, follow and close a research session.

Subcommands:
  start --harness H --model M   Open a session. Refuses if a session is already active, if
                                project.md has no title and goal yet, or if the checkout has
                                uncommitted changes (in local mode, uncommitted edits of the
                                researcher's files are first committed as theirs). Shared mode:
                                opens a draft pull request (its number is the session number)
                                and moves the checkout to the session's branch. Local mode: takes
                                the next free number in sessions/. Prints what the researcher
                                sent since the previous session started, and records it in
                                sessions/S<n>/received.md.
  status                        Where the active session stands; without one, what a session
                                started now would receive.
  next <CL|DE|D|C|CR>           Print the next free ID of that prefix in the active session.
  next review <artefact>        Print the path of the next review file of that artefact.
  answer <S> <n|note> <text>    Record an answer (or the note) the researcher gave in the
                                terminal, in the debrief of session S, as theirs.
  tick <S> <k> [<k> ...]        Tick lines k (1, 2, ...) of the debrief of session S, as the
                                researcher asked in the terminal.
  brief                         Commit sessions/S<n>/brief.md; shared mode: push it and copy
                                it to the pull request.
  end [--no-merge]              Needs note.tex and debrief.md. Writes "Changed by this session"
                                in the debrief from git, runs check. Shared mode: rebase on main
                                if needed, push, upload sources and the trace, merge.
  abort                         Abandon the active session.

Usage: uv run .physics-hive/scripts/session.py <subcommand> [options]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import Workspace, dump_front_matter, find_root, split_front_matter  # noqa: E402
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
from human import (  # noqa: E402
    HUMAN_FILES,
    RESEARCHER_FILES,
    History,
    changed_by_session,
    format_received,
    handoff,
    one_line,
    previous_start,
    received,
    received_record,
    set_answer,
    set_changed,
    set_note,
    set_ticks,
)
from regen import regenerate  # noqa: E402

PREFIX_FOLDERS = {"CL": "claims", "DE": "claims", "D": "derivations", "C": "computations", "CR": "critiques"}

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


def researcher_path(path: str) -> bool:
    """Files the researcher edits between sessions: the human files, seeds, ratings and debriefs."""
    return path in HUMAN_FILES or path in RESEARCHER_FILES or bool(re.match(r"^sessions/S\d+/debrief\.md$", path))


def commit_researcher_edits(root: Path, when: str) -> None:
    """Local mode: commit the researcher's uncommitted edits of their files as theirs, or refuse."""
    dirty = dirty_paths(root)
    if not dirty:
        return
    others = [p for p in dirty if not researcher_path(p)]
    if others:
        listing = ", ".join(others[:8]) + (", …" if len(others) > 8 else "")
        raise ScriptError(f"the checkout has uncommitted changes ({listing}); commit or discard them first")
    git(root, "add", "--", *dirty)
    git(root, "commit", "-q", "-m", f"Researcher's edits ({when})", "-m", "Committed by session.py: " + ", ".join(dirty))
    say(f"Committed your edits of {', '.join(dirty)} as yours.")


def project_is_template(root: Path) -> bool:
    from human import parse_project

    path = root / "project.md"
    return not path.is_file() or parse_project(path.read_text(encoding="utf-8")).is_template


def compute_received(root: Path, ws: Workspace):
    _, since = previous_start(ws.sessions.values())
    return received(ws, History(root, since))


def print_context(ws: Workspace, root: Path, active: dict, news) -> None:
    """What the coordinator needs besides the researcher's input: handoffs, re-checks, draft flags, other sessions."""
    for d in news.debriefs:
        if not d.full:
            continue
        session = ws.sessions.get(d.session)
        text = handoff(ws.text(f"{session.path}/log.md")) if session and session.has_log else ""
        if text:
            say("")
            say(f"Handoff from {d.session} (end of sessions/{d.session}/log.md):")
            say("\n".join("  " + line for line in text.splitlines()))
    recheck = []
    for card in ws.sorted_cards():
        causes = ws.needs_recheck(card.id)
        if causes and ws.status(card.id) not in ("refuted", "revised"):
            recheck.append(f"{card.id}: depends on " + ", ".join(f"{c} ({ws.status(c)})" for c in causes))
    flags = ws.draft_flags()
    sections = [("Cards that need a re-check", recheck), ("Draft flags (propose a change in the debrief)", flags)]
    if ws.mode == "shared":
        import hub

        sections += hub.shared_waiting(ws, root, active)
    for title, items in sections:
        if items:
            say("")
            say(f"{title}:")
            for item in items:
                say(f"- {item}")
    if news.unanswered:
        say("")
        say("Questions without an answer (show them to the operator and wait, or go on if they say so):")
        for session_id, number, question in news.unanswered:
            say(f"- {session_id} question {number}: {one_line(question, 200)}")


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
    ws = Workspace(root)
    if ws.mode == "local":
        commit_researcher_edits(root, "before a session")
    elif dirty_paths(root):
        dirty = dirty_paths(root)
        raise ScriptError(f"the checkout has uncommitted changes ({', '.join(dirty[:8])}); commit or discard them "
                          "first (in a shared space, the researcher edits their files in the Space)")
    if project_is_template(root):
        raise ScriptError(
            "project.md has no title or goal yet. The researcher writes the question in one line as its title and "
            "the goal under ## Goal (in the Space, in an editor, or by dictating them to the coordinator outside a "
            "session), and commits it; in shared mode it is pushed to main "
            "(`uv run .physics-hive/scripts/hubgit.py push origin main`)."
        )
    if ws.mode == "local":
        refuse_if_stale(root, (root / ".physics-hive" / "VERSION").read_text().strip())
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
    ws = Workspace(root)  # in shared mode the checkout has just moved to the latest main
    news = compute_received(root, ws)
    text = format_received(news)
    folder = root / "sessions" / info["id"]
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "log.md"
    if not log.exists():
        log.write_text(LOG_TEMPLATE.format(**info), encoding="utf-8")
    meta = {"session": info["id"], "started": info["started"], "base": info["base"], "previous": news.previous,
            "debriefs": received_record(news)}
    (folder / "received.md").write_text(dump_front_matter(meta, f"```text\n{text}\n```\n"), encoding="utf-8")
    save_active(root, info)
    ws = regenerate(root)

    say(f"Session {info['id']} started ({info['mode']} mode).")
    if info.get("pr_url"):
        say(f"Draft pull request #{info['pr']}: {info['pr_url']}")
        say(f"Branch: {info['branch']} (based on main at {info['base'][:12]}).")
    say(f"In cards, use produced_by: {{kind: agent, model: {model}, operator: {info['operator']}}}.")
    say(f"This is recorded in sessions/{info['id']}/received.md; it is committed with the brief.")
    say("")
    say(text)
    print_context(ws, root, info, news)
    say("")
    say(f"Next: apply the ticked lines (one commit: `[{info['id']}] apply the lines ticked in the S<m> debrief`), "
        f"then propose a brief, write sessions/{info['id']}/brief.md and run `session.py brief`.")


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
        say("No session is active in this checkout. A session started now would receive:")
        say("")
        say(format_received(compute_received(root, ws)))
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
        say(f"Brief: {meta.get('goal', '?')} (budget {meta.get('budget', '?')} dispatches).")
    else:
        say("Brief: not written yet.")
    say(f"Dispatches logged: {dispatches}.")
    for name in ("note.tex", "debrief.md"):
        say(f"{name}: {'written' if (folder / name).exists() else 'not written yet'}.")
    received_file = folder / "received.md"
    if received_file.exists():
        say("")
        say(f"What this session received from the researcher (sessions/{active['id']}/received.md):")
        say(split_front_matter(received_file.read_text(encoding="utf-8"))[1].strip().strip("`").removeprefix("text").strip())


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


def _debrief_of(root: Path, session_id: str) -> Path:
    if not re.match(r"^S\d+$", session_id):
        raise ScriptError(f"{session_id} is not a session (S<n>)")
    path = root / "sessions" / session_id / "debrief.md"
    if not path.is_file():
        raise ScriptError(f"sessions/{session_id}/debrief.md does not exist")
    return path


def _record_in_received(root: Path, active: dict, session_id: str, key: str, value) -> None:
    """Add what the researcher gave in the terminal to the active session's received.md."""
    path = root / "sessions" / active["id"] / "received.md"
    if not path.is_file():
        return
    meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    entry = (meta.setdefault("debriefs", {}) or {}).setdefault(session_id, {}) or {}
    if key == "answers":
        entry.setdefault("answers", {}).update(value)
    elif key == "ticked":
        entry["ticked"] = list(dict.fromkeys([*(entry.get("ticked") or []), *value]))
    else:
        entry["note"] = value
    meta["debriefs"][session_id] = entry
    path.write_text(dump_front_matter(meta, body), encoding="utf-8")


def _commit_researcher(root: Path, path: Path, message: str) -> None:
    """Commit one file as the researcher's (a message without the session prefix), and nothing else."""
    rel = str(path.relative_to(root))
    if git(root, "diff", "--quiet", "HEAD", "--", rel, check=False).returncode != 0:
        git(root, "commit", "-q", "-m", message, "--", rel)


def cmd_answer(root: Path, args) -> None:
    active = load_active(root) or {}
    path = _debrief_of(root, args.session)
    text = path.read_text(encoding="utf-8")
    answer = " ".join(args.text).strip()
    if args.what == "note":
        path.write_text(set_note(text, answer), encoding="utf-8")
        what, record = "the note", ("note", answer)
    else:
        if not args.what.isdigit():
            raise ScriptError("usage: session.py answer <session> <question number | note> <text>")
        try:
            path.write_text(set_answer(text, int(args.what), answer), encoding="utf-8")
        except ValueError as exc:
            raise ScriptError(str(exc)) from None
        what, record = f"question {args.what}", ("answers", {int(args.what): answer})
    where = f" in {active['id']}" if active else ""
    _commit_researcher(root, path, f"Researcher's answer to {what} of the {args.session} debrief "
                                   f"(given to the coordinator{where})")
    if active:
        _record_in_received(root, active, args.session, *record)
    say(f"Recorded the researcher's answer to {what} in sessions/{args.session}/debrief.md, as theirs.")


def cmd_tick(root: Path, args) -> None:
    from human import parse_debrief

    active = load_active(root) or {}
    path = _debrief_of(root, args.session)
    text = path.read_text(encoding="utf-8")
    ticks = parse_debrief(text).ticks
    wanted = {}
    for k in args.lines:
        if not 1 <= k <= len(ticks):
            raise ScriptError(f"the {args.session} debrief has {len(ticks)} tick lines; there is no line {k}")
        wanted[k - 1] = True
    path.write_text(set_ticks(text, wanted), encoding="utf-8")
    where = f" in {active['id']}" if active else ""
    _commit_researcher(root, path, f"Researcher's ticks in the {args.session} debrief (given to the coordinator{where})")
    if active:
        _record_in_received(root, active, args.session, "ticked", [ticks[i].text for i in sorted(wanted)])
    say(f"Ticked line(s) {', '.join(map(str, args.lines))} of sessions/{args.session}/debrief.md, as the researcher's.")


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
    missing = [name for name in ("note.tex", "debrief.md") if not (folder / name).is_file()]
    if missing:
        raise ScriptError(f"write and commit sessions/{active['id']}/{' and '.join(missing)} before ending the session")
    dirty = dirty_paths(root)
    if dirty:
        raise ScriptError(f"uncommitted changes ({', '.join(dirty[:8])}); commit them before ending the session (if "
                          "some are the researcher's own edits, commit those separately, with a message that does "
                          f"not start with [{active['id']}])")
    if active["mode"] == "shared":
        import hub

        hub.end_session(root, active, merge=not args.no_merge, finish=finish)
        return
    finish(root, active["base"], active["id"])
    clear_active(root)
    regenerate(root)
    say(f"Session {active['id']} closed: check passed.")


def finish(root: Path, base: str, session: str) -> None:
    """Write 'Changed by this session' in the debrief from the session's commits since `base`, commit, check."""
    path = root / "sessions" / session / "debrief.md"
    text = path.read_text(encoding="utf-8")
    updated = set_changed(text, changed_by_session(History(root, None), session, base))
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        git(root, "add", "--", str(path.relative_to(root)))
        git(root, "commit", "-q", "-m", f"[{session}] debrief: changed by this session")
        say("Wrote 'Changed by this session' in the debrief.")
    check_or_fail(root, base, session)


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
    p.add_argument("what", help="CL, DE, D, C, CR, or review")
    p.add_argument("target", nargs="?", help="with review: the artefact ID")
    p = sub.add_parser("answer")
    p.add_argument("session", help="the session whose debrief it answers, e.g. S3")
    p.add_argument("what", help="the question number, or note")
    p.add_argument("text", nargs="+", help="the researcher's words")
    p = sub.add_parser("tick")
    p.add_argument("session", help="the session whose debrief it ticks, e.g. S3")
    p.add_argument("lines", nargs="+", type=int, help="tick lines to tick, counted from 1")
    sub.add_parser("brief")
    p = sub.add_parser("end")
    p.add_argument("--no-merge", action="store_true", help="shared mode: leave the pull request open for the operator")
    sub.add_parser("abort")
    args = parser.parse_args()
    root = args.root.resolve() if args.root else find_root()
    commands = {"start": cmd_start, "status": cmd_status, "next": cmd_next, "answer": cmd_answer, "tick": cmd_tick,
                "brief": cmd_brief, "end": cmd_end, "abort": cmd_abort}
    commands[args.command](root, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
