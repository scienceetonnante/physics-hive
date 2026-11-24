# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Validate a PhysicsHive workspace.

Checks only what a script can verify: that every card, artefact summary,
review and paper card has a well-formed header; that every reference points to
an existing item of the right kind; that the dependency graph has no cycle;
that every card named with \\card in the draft and the notes exists; that every
`result` environment of the draft names a claim with confirmed evidence; and
that debriefs have the shape the Space and the next session read.

Compared with a base commit (a session's start), it also checks the changes:
no record file edited or deleted after its creation (a file added since the
base may change until the session ends), the method copy and project.toml
untouched, and, for the changes the session made itself (its `[S<n>]` commits
and uncommitted changes): no other session's folder touched, no file of the
lead's alone (seeds, ratings) touched, new IDs that belong to the
session, a valid draft, and a well-formed note and debrief. Problems in the
draft or a debrief that the session did not cause are warnings.

When a session is active in this checkout, the base and the session default to
those recorded in `.active-session`.

Usage: uv run .physics-hive/scripts/check.py [--base REF] [--session S12] [--root PATH]
Exit status 1 when there is at least one error. Warnings do not fail the check.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import (  # noqa: E402
    CARD_KINDS,
    PAPER_ID_RE,
    PREFIX_TO_KIND,
    RATINGS,
    RATINGS_FILE,
    RESEARCHER_FILES,
    REVIEW_ID_RE,
    SESSION_ID_RE,
    VERDICTS,
    Problem,
    Workspace,
    find_root,
    natural_key,
    result_problems,
    session_of,
)
from common import changes_since, is_git_repo, load_active, session_paths  # noqa: E402
from human import debrief_problems, tex_cards  # noqa: E402

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MAX_STATEMENT = 300  # characters; a longer statement is usually several sentences
IMMUTABLE_DIRS = ("claims/", "derivations/", "computations/")
SESSION_FOLDER_RE = re.compile(r"^sessions/(S\d+)/")


class Report:
    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def error(self, path: str, message: str) -> None:
        self.problems.append(Problem("error", path, message))

    def warning(self, path: str, message: str) -> None:
        self.problems.append(Problem("warning", path, message))

    def add(self, severity: str, path: str, message: str) -> None:
        self.problems.append(Problem(severity, path, message))

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.severity == "error"]


def check_cards(ws: Workspace, r: Report) -> None:
    for card in ws.sorted_cards():
        path = card.path
        stem = Path(path).stem
        if card.id != stem:
            r.error(path, f"id {card.id!r} does not match the file name {stem!r}")
        m = SESSION_ID_RE.match(card.id)
        prefix = m.group(1) if m else None
        if prefix not in PREFIX_TO_KIND:
            r.error(path, f"id {card.id!r} is not a card ID (CL-S<n>-<k> or DE-S<n>-<k>)")
        elif card.kind != PREFIX_TO_KIND[prefix]:
            r.error(path, f"kind {card.kind!r} does not match the ID prefix {prefix}- (expected {PREFIX_TO_KIND[prefix]!r})")
        if card.kind not in CARD_KINDS:
            r.error(path, f"kind must be one of {', '.join(CARD_KINDS)} (questions come from the lead, "
                          "through debriefs)")
        if not card.statement:
            r.error(path, "statement is empty")
        elif CONTROL_CHARS.search(card.statement):
            r.warning(path, "statement contains control characters; LaTeX backslashes need single quotes in YAML")
        if len(card.statement) > MAX_STATEMENT:
            r.warning(path, f"statement is {len(card.statement)} characters long; a statement is one sentence, "
                            "with context and caveats in the body")
        produced = card.produced_by
        if produced.get("kind") == "agent":
            for key in ("model", "operator"):
                if not produced.get(key):
                    r.warning(path, f"produced_by has no {key}")
        elif produced.get("kind") == "human":
            if not produced.get("user"):
                r.error(path, "produced_by of a human card needs a user")
        else:
            r.error(path, "produced_by must be {kind: agent, model, operator} or {kind: human, user}")
        if m and card.session != session_of(card.id):
            r.error(path, f"session is {card.session!r} but the ID belongs to {session_of(card.id)}")
        if card.meta.get("answers"):
            r.error(path, "answers is no longer a card field (there are no question cards)")
        check_card_refs(ws, card, r)


def check_card_refs(ws: Workspace, card, r: Report) -> None:
    rules = (
        ("depends_on", card.depends_on, None, None),
        ("supersedes", card.supersedes, "claim", ("claim",)),
        ("refutes", card.refutes, "claim", ("dead-end",)),
    )
    for field, ids, target_kind, allowed_on in rules:
        if ids and allowed_on and card.kind not in allowed_on:
            r.error(card.path, f"{field} is only allowed on {' and '.join(allowed_on)} cards")
        for ref in ids:
            if ref == card.id:
                r.error(card.path, f"{field} names the card itself")
            elif ref not in ws.cards:
                r.error(card.path, f"{field} names {ref}, which does not exist in claims/")
            elif target_kind and ws.cards[ref].kind != target_kind:
                r.error(card.path, f"{field} names {ref}, a {ws.cards[ref].kind} card (expected a {target_kind})")


def check_cycles(ws: Workspace, r: Report) -> None:
    graph = {cid: card.depends_on + card.supersedes for cid, card in ws.cards.items()}
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        state[node] = 1
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                cycle = trail[trail.index(nxt):] + [nxt] if nxt in trail else [node, nxt]
                r.error(ws.cards[node].path, "dependency cycle: " + " -> ".join(cycle))
            elif state.get(nxt) is None:
                visit(nxt, trail + [nxt])
        state[node] = 2

    for node in sorted(graph, key=natural_key):
        if state.get(node) is None:
            visit(node, [node])


def check_artefacts(ws: Workspace, r: Report) -> None:
    for art in sorted(ws.artefacts.values(), key=lambda a: natural_key(a.id)):
        stem = Path(art.path).name.removesuffix(".summary.md").removesuffix(".md")
        if art.id != stem:
            r.error(art.path, f"id {art.id!r} does not match the file name {stem!r}")
        m = SESSION_ID_RE.match(art.id)
        expected = "D" if art.kind == "derivation" else "C"
        if not m or m.group(1) != expected:
            r.error(art.path, f"id {art.id!r} should look like {expected}-S<n>-<k>")
        if art.meta.get("kind") != art.kind:
            r.error(art.path, f"kind should be {art.kind!r}")
        for key in ("model", "operator", "produced_by", "author"):
            if key in art.meta:
                r.error(art.path, f"artefacts carry no authorship (remove {key!r}); the trace records it")
        for ref in art.supports:
            if ref not in ws.cards:
                r.warning(art.path, f"supports {ref}, which has no card yet (reserved ID never written?)")
            elif ws.cards[ref].kind != "claim":
                r.error(art.path, f"supports {ref}, a {ws.cards[ref].kind} card (only claims are supported)")
        wanted = ".tex" if art.kind == "derivation" else ".py"
        if not any(p.endswith(wanted) for p in art.full):
            r.warning(art.path, f"no {wanted} file next to the summary")


def check_reviews(ws: Workspace, r: Report) -> None:
    for review in sorted(ws.reviews.values(), key=lambda x: natural_key(x.id)):
        path = review.path
        stem = Path(path).stem
        if review.id != stem:
            r.error(path, f"id {review.id!r} does not match the file name {stem!r}")
        if review.verdict not in VERDICTS:
            r.error(path, f"verdict must be one of {', '.join(VERDICTS)}")
        m = REVIEW_ID_RE.match(review.id)
        if not m:
            r.error(path, f"id {review.id!r} should look like <target>_R-S<n>-<k>")
        elif review.target != m.group(1):
            r.error(path, f"target {review.target!r} does not match the file name ({m.group(1)})")
        if review.target not in ws.artefacts:
            r.error(path, f"target {review.target} has no summary file")
        if m and review.session != f"S{m.group(2)}":
            r.error(path, f"session is {review.session!r} but the ID belongs to S{m.group(2)}")
        if review.by_human and not review.by.get("user"):
            r.error(path, "a human verification needs by: {kind: human, user}")
        elif not review.by_human and review.by.get("kind") != "agent":
            r.error(path, "by must be {kind: agent} or, for a verification by the lead, {kind: human, user}")
        for ref in review.supports:
            if ref not in ws.cards:
                r.error(path, f"supports {ref}, which does not exist in claims/")
            elif ws.cards[ref].kind != "claim":
                r.error(path, f"supports {ref}, a {ws.cards[ref].kind} card (only claims are supported)")


def check_papers(ws: Workspace, r: Report) -> None:
    for paper in ws.papers.values():
        if paper.id != Path(paper.path).stem:
            r.error(paper.path, f"id {paper.id!r} does not match the file name")
        if not PAPER_ID_RE.match(paper.id):
            r.error(paper.path, f"id {paper.id!r} should look like P-<arXiv id> (slashes replaced by underscores)")
        if not paper.title:
            r.warning(paper.path, "no title")
        if paper.rating and paper.rating not in ("high", "medium", "low"):
            r.warning(paper.path, "rating should be high, medium or low")
    text = ws.text(RATINGS_FILE)
    if text:
        import yaml

        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            r.warning(RATINGS_FILE, f"invalid YAML: {exc}")
            data = {}
        for paper, value in (data.items() if isinstance(data, dict) else []):
            if str(value).strip().lower().replace("-", " ") not in RATINGS:
                r.warning(RATINGS_FILE, f"{paper}: rating {value!r} is not one of {', '.join(RATINGS)}")
            if str(paper) not in ws.papers:
                r.warning(RATINGS_FILE, f"{paper} has no paper card")


def draft_problems(ws: Workspace, tex: str | None = None) -> list[tuple[str, str, str]]:
    """What the draft may not contain, as (card ID, 'result' or 'card', message): unknown cards, and
    results whose claims fail result_problems. `tex` defaults to the current draft.tex."""
    from human import parse_draft

    tex = ws.text("draft.tex") if tex is None else tex
    blocks = parse_draft(tex)
    problems = []
    for block in blocks:
        if block.kind == "result" and not block.cards:
            problems.append(("", "result", f"the result at line {block.line} names no card (\\card{{CL-...}})"))
        for card_id in block.cards:
            if block.kind == "result":
                problems += [(card_id, "result", f"the result at line {block.line}: {reason}; copy it as a "
                                                 "conjecture instead") for reason in result_problems(ws, card_id)]
    for card_id in tex_cards(tex):
        if card_id not in ws.cards and not any(p[0] == card_id for p in problems):
            problems.append((card_id, "card", f"\\card{{{card_id}}} names a card that does not exist"))
    return problems


def check_human_files(ws: Workspace, r: Report, session_changed: set[str], session: str | None,
                      base: str | None) -> None:
    """The draft, the notes and the debriefs: errors for what the active session wrote, warnings otherwise.

    In the draft, a problem is the session's when the session changed draft.tex and the card at fault was
    not already named that way at the base (so an edit by the lead never blocks a session).
    """
    before_results: set[str] = set()
    before_cards: set[str] = set()
    if "draft.tex" in session_changed and base:
        from common import git
        from human import parse_draft

        old = git(ws.root, "show", f"{base}:draft.tex", check=False).stdout
        before_results = {c for b in parse_draft(old) if b.kind == "result" for c in b.cards}
        before_cards = set(tex_cards(old))
    for card_id, kind, message in draft_problems(ws):
        before = before_results if kind == "result" else before_cards
        mine = "draft.tex" in session_changed and (not card_id or card_id not in before)
        r.add("error" if mine else "warning", "draft.tex", message)
    for s in ws.sessions.values():
        mine = s.id == session
        if s.has_note:
            rel = f"{s.path}/note.tex"
            for card_id in tex_cards(ws.text(rel)):
                if card_id not in ws.cards:
                    r.add("error" if mine else "warning", rel, f"\\card{{{card_id}}} names a card that does not exist")
        if s.debrief is not None:
            rel = f"{s.path}/debrief.md"
            severity = "error" if mine and rel in session_changed else "warning"
            for problem in debrief_problems(ws.text(rel)):
                r.add(severity, rel, problem)
        if s.brief is not None and not s.goal:
            r.warning(f"{s.path}/brief.md", "the brief has no goal in its front matter")


def check_changes(ws: Workspace, base: str, session: str | None, r: Report) -> set[str]:
    """Rules that compare the working tree with a base commit. Returns the paths the session changed."""
    changes = changes_since(ws.root, base)
    mine = session_paths(ws.root, base, session) if session else set()
    for status, path in changes:
        if path.startswith(".physics-hive/"):
            r.error(path, "the method copy changes only through an upgrade, never inside a session")
        if status in ("M", "D") and path.startswith(IMMUTABLE_DIRS) and "/.briefs/" not in path and not path.endswith(".gitkeep"):
            verb = "edited" if status == "M" else "deleted"
            r.error(path, f"{verb} after creation; nothing is edited or deleted, write a new file that names it instead")
        if status in ("M", "D") and path.startswith("literature/P-"):
            r.error(path, "paper cards are not edited after creation; the lead's ratings go to "
                          f"{RATINGS_FILE}")
        if session and path == "project.toml":
            r.error(path, "a session does not change project.toml")
        if path not in mine:
            continue
        if path in RESEARCHER_FILES:
            r.error(path, "only the lead writes this file")
        m = SESSION_FOLDER_RE.match(path)
        if m and m.group(1) != session:
            r.error(path, f"belongs to session {m.group(1)}, not to {session}; never edit another session's "
                          "files, and never the lead's answers in a debrief")
    added = {path for status, path in changes if status == "A"}
    for path in sorted(added & mine):
        name = Path(path).name
        stem = name.removesuffix(".summary.md").removesuffix(".md")
        if path.startswith(("claims/", "derivations/", "computations/", "critiques/")) and "/.briefs/" not in path:
            owner = session_of(stem.split(".")[0])
            if owner and owner != session:
                r.error(path, f"new in this session but its ID belongs to {owner}")
    return mine


def run_checks(ws: Workspace, base: str | None = None, session: str | None = None) -> Report:
    r = Report()
    r.problems.extend(ws.problems)
    check_cards(ws, r)
    check_cycles(ws, r)
    check_artefacts(ws, r)
    check_reviews(ws, r)
    check_papers(ws, r)
    mine: set[str] = set()
    if base:
        mine = check_changes(ws, base, session, r)
    check_human_files(ws, r, mine, session, base)
    return r


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--base", help="commit to compare against (default: the active session's base)")
    parser.add_argument("--session", help="session whose changes are checked (default: the active session)")
    args = parser.parse_args()
    root = args.root.resolve() if args.root else find_root()
    active = load_active(root) or {}
    base = args.base or active.get("base")
    session = args.session or active.get("id")
    if base and not is_git_repo(root):
        base = None
    ws = Workspace(root)
    report = run_checks(ws, base=base, session=session)
    for problem in sorted(report.problems, key=lambda p: (p.severity != "error", p.path)):
        print(problem)
    n_err = len(report.errors)
    n_warn = len(report.problems) - n_err
    scope = f" (changes since {base[:12]}{', session ' + session if session else ''})" if base else ""
    print(f"check: {n_err} error(s), {n_warn} warning(s){scope}.")
    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
