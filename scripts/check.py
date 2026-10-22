# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Validate a PhysicsIntern workspace.

Checks only what a script can verify: that every card, artefact summary,
review, feedback record and paper card has a well-formed header; that every
reference points to an existing item of the right kind; that the dependency
graph has no cycle; and, compared with a base commit, that no file was edited
after its creation, that the method copy and (in shared mode) the lead's files
were not touched, that a session wrote no question card of its own (people
write them), and that new promotion records follow the promotion rule. A file
added since the base may be edited until the session ends.

When a session is active in this checkout, the base and the session default to
those recorded in `.active-session`.

Usage: uv run .physics-intern/scripts/check.py [--base REF] [--session S12] [--root PATH]
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
    CLAIM_REACTIONS,
    LEAD_FILES,
    PAPER_ID_RE,
    PAPER_REACTIONS,
    PREFIX_TO_KIND,
    REVIEW_ID_RE,
    SESSION_ID_RE,
    USER_ID_RE,
    VERDICTS,
    Problem,
    Workspace,
    find_root,
    natural_key,
    promotion_problems,
    session_of,
)
from common import changes_since, is_git_repo, load_active  # noqa: E402

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MAX_STATEMENT = 300  # characters; a longer statement is usually several sentences
IMMUTABLE_DIRS = ("claims/", "feedback/", "derivations/", "computations/")
SESSION_FOLDER_RE = re.compile(r"^sessions/(S\d+)/")


class Report:
    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def error(self, path: str, message: str) -> None:
        self.problems.append(Problem("error", path, message))

    def warning(self, path: str, message: str) -> None:
        self.problems.append(Problem("warning", path, message))

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.severity == "error"]


def check_cards(ws: Workspace, r: Report) -> None:
    for card in ws.sorted_cards():
        path = card.path
        stem = Path(path).stem
        if card.id != stem:
            r.error(path, f"id {card.id!r} does not match the file name {stem!r}")
        m_session, m_user = SESSION_ID_RE.match(card.id), USER_ID_RE.match(card.id)
        prefix = (m_session or m_user).group(1) if (m_session or m_user) else None
        if prefix not in PREFIX_TO_KIND:
            r.error(path, f"id {card.id!r} is not a card ID (CL-S<n>-<k>, Q-…, DE-…, or <prefix>-<user>-<timestamp>)")
        elif card.kind != PREFIX_TO_KIND[prefix]:
            r.error(path, f"kind {card.kind!r} does not match the ID prefix {prefix}- (expected {PREFIX_TO_KIND[prefix]!r})")
        if card.kind not in CARD_KINDS:
            r.error(path, f"kind must be one of {', '.join(CARD_KINDS)}")
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
        if m_session and card.session != session_of(card.id):
            r.error(path, f"session is {card.session!r} but the ID belongs to {session_of(card.id)}")
        if m_user and card.session:
            r.warning(path, "a card with a user ID was written outside a session; session should be null")
        check_card_refs(ws, card, r)


def check_card_refs(ws: Workspace, card, r: Report) -> None:
    rules = (
        ("depends_on", card.depends_on, None, None),
        ("supersedes", card.supersedes, "claim", ("claim",)),
        ("refutes", card.refutes, "claim", ("dead-end",)),
        ("answers", card.answers, "question", ("claim", "dead-end")),
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
        if review.id != stem and not path.startswith("feedback/"):
            r.error(path, f"id {review.id!r} does not match the file name {stem!r}")
        if review.verdict not in VERDICTS:
            r.error(path, f"verdict must be one of {', '.join(VERDICTS)}")
        if path.startswith("feedback/"):
            if not review.by_human or not review.by.get("user"):
                r.error(path, "a review in feedback/ is a human verification and needs by: {kind: human, user}")
            if not USER_ID_RE.match(review.id) or not review.id.startswith("R-"):
                r.error(path, f"id {review.id!r} should look like R-<user>-<timestamp>")
            if review.target and review.target not in ws.artefacts and review.target not in ws.cards:
                r.error(path, f"target {review.target} does not exist")
            if not review.supports:
                r.error(path, "a verification must name the card(s) it verifies in supports")
        else:
            m = REVIEW_ID_RE.match(review.id)
            if not m:
                r.error(path, f"id {review.id!r} should look like <target>_R-S<n>-<k>")
            elif review.target != m.group(1):
                r.error(path, f"target {review.target!r} does not match the file name ({m.group(1)})")
            if review.target not in ws.artefacts:
                r.error(path, f"target {review.target} has no summary file")
            if m and review.session != f"S{m.group(2)}":
                r.error(path, f"session is {review.session!r} but the ID belongs to S{m.group(2)}")
        for ref in review.supports:
            if ref not in ws.cards:
                r.error(path, f"supports {ref}, which does not exist in claims/")
            elif ws.cards[ref].kind != "claim":
                r.error(path, f"supports {ref}, a {ws.cards[ref].kind} card (only claims are supported)")


def check_feedback(ws: Workspace, r: Report) -> None:
    for reaction in ws.reactions:
        if not reaction.user:
            r.error(reaction.path, "a reaction needs by: {kind: human, user}")
        if reaction.target in ws.papers:
            allowed = PAPER_REACTIONS
        elif reaction.target in ws.cards:
            allowed = CLAIM_REACTIONS
        else:
            r.error(reaction.path, f"target {reaction.target!r} is neither a card nor a paper card")
            continue
        if reaction.value not in allowed:
            r.error(reaction.path, f"value must be one of {', '.join(allowed)}")
    for promotion in ws.promotions:
        if promotion.target not in ws.cards:
            r.error(promotion.path, f"target {promotion.target!r} does not exist in claims/")
        elif ws.cards[promotion.target].kind != "claim":
            r.error(promotion.path, f"target {promotion.target} is not a claim")
        if promotion.by.get("kind") not in ("human", "agent"):
            r.error(promotion.path, "by must be {kind: human, user} or {kind: agent, model, operator}")


def check_papers(ws: Workspace, r: Report) -> None:
    for paper in ws.papers.values():
        if paper.id != Path(paper.path).stem:
            r.error(paper.path, f"id {paper.id!r} does not match the file name")
        if not PAPER_ID_RE.match(paper.id):
            r.error(paper.path, f"id {paper.id!r} should look like P-<arXiv id> (slashes replaced by underscores)")
        if not paper.title:
            r.warning(paper.path, "no title")


def check_sessions(ws: Workspace, r: Report) -> None:
    for session in ws.sessions.values():
        if session.brief is not None and not session.goal:
            r.warning(f"{session.path}/brief.md", "the brief has no goal in its front matter")
        if session.report is not None and not session.report.get("stop_reason"):
            r.warning(f"{session.path}/report.md", "the report has no stop_reason in its front matter")


def check_changes(ws: Workspace, base: str, session: str | None, r: Report) -> None:
    """Rules that compare the working tree with a base commit."""
    changes = changes_since(ws.root, base)
    added = {path for status, path in changes if status == "A"}
    for status, path in changes:
        if path.startswith(".physics-intern/"):
            r.error(path, "the method copy changes only through an upgrade, never inside a session")
        if status in ("M", "D") and path.startswith(IMMUTABLE_DIRS) and "/.briefs/" not in path and not path.endswith(".gitkeep"):
            verb = "edited" if status == "M" else "deleted"
            r.error(path, f"{verb} after creation; nothing is edited or deleted, write a new file that names it instead")
        if status in ("M", "D") and path.startswith("literature/P-"):
            r.error(path, "paper cards are not edited after creation")
        if session and ws.mode == "shared" and (path in LEAD_FILES or path == "project.toml"):
            r.error(path, "this is a lead's file; a session proposes changes in its report or with propose.py")
        m = SESSION_FOLDER_RE.match(path)
        if session and m and m.group(1) != session:
            r.error(path, f"belongs to session {m.group(1)}, not to {session}")
    if not session:
        return
    for path in sorted(added):
        name = Path(path).name
        stem = name.removesuffix(".summary.md").removesuffix(".md")
        if path.startswith(("claims/", "derivations/", "computations/", "critiques/")) and "/.briefs/" not in path:
            owner = session_of(stem.split(".")[0])
            if owner and owner != session:
                r.error(path, f"new in this session but its ID belongs to {owner}")
    for card in ws.sorted_cards("question"):
        if card.path in added and card.produced_by.get("kind") != "human":
            r.error(card.path, "question cards are written by people; put open work under Proposed plan changes, "
                               "or under Needs a human decision, in the session report")
    new_promotions = [p for p in ws.promotions if p.path in added]
    for promotion in new_promotions:
        if ws.mode == "shared":
            r.error(promotion.path, "in shared mode a lead records promotions with promote.py or from the Space, not inside a session")
            continue
        for reason in promotion_problems(ws, promotion.target, promotion.by):
            r.error(promotion.path, f"promotion refused: {reason}")


def run_checks(ws: Workspace, base: str | None = None, session: str | None = None) -> Report:
    r = Report()
    r.problems.extend(ws.problems)
    check_cards(ws, r)
    check_cycles(ws, r)
    check_artefacts(ws, r)
    check_reviews(ws, r)
    check_feedback(ws, r)
    check_papers(ws, r)
    check_sessions(ws, r)
    if base:
        check_changes(ws, base, session, r)
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
