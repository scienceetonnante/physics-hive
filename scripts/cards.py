"""Read a PhysicsIntern workspace and compute what follows from its files.

The record of a workspace is small Markdown files with a YAML front matter:
cards in `claims/` (claims and dead ends), artefact summaries and reviews in
`derivations/` and `computations/`, paper cards in `literature/`, critiques,
and one folder per session in `sessions/`. A card never changes once its
session has ended; everything that happens to it later is a new file that
names it.

The human view (project.md, conventions.md, draft.tex, the debriefs, the
ratings) is parsed by human.py. A claim is *established* when a `result`
environment of draft.tex names it, so status depends on both.

This module loads those files and computes, for each card, its status, its
evidence and whether it needs a re-check. Nothing it computes is stored. It is
imported by regen.py, check.py, session.py and the Space, so it must stay free
of side effects. Requires PyYAML.
"""

from __future__ import annotations

import datetime as _dt
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from human import (  # noqa: F401  (re-exported for the scripts and the Space)
    HUMAN_FILES,
    RATINGS,
    RATINGS_FILE,
    RESEARCHER_FILES,
    Debrief,
    DraftBlock,
    Project,
    parse_debrief,
    parse_draft,
    parse_project,
    parse_ratings,
)

# ----- identifiers -----

CARD_KINDS = {"claim": "CL", "dead-end": "DE"}
PREFIX_TO_KIND = {prefix: kind for kind, prefix in CARD_KINDS.items()}

# Items created inside a session: CL-S12-2, DE-S12-1, D-S12-3, C-S12-1, CR-S12-1
SESSION_ID_RE = re.compile(r"^(CL|DE|D|C|CR)-S(\d+)-(\d+)$")
# Reviews sit next to their target: D-S3-2_R-S7-1 (by an agent, or a human verification written by S7)
REVIEW_ID_RE = re.compile(r"^((?:D|C)-S\d+-\d+)_R-S(\d+)-(\d+)$")
PAPER_ID_RE = re.compile(r"^P-[A-Za-z0-9._-]+$")
SESSION_DIR_RE = re.compile(r"^S(\d+)$")

VERDICTS = ("confirmed", "refuted", "inconclusive")


def natural_key(text: str) -> list:
    """Sort key that orders `S2` before `S10` and `CL-S3-2` before `CL-S3-10`."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def session_of(item_id: str) -> str | None:
    """Return the session (e.g. `S12`) embedded in an ID, or None."""
    m = REVIEW_ID_RE.match(item_id) or SESSION_ID_RE.match(item_id)
    return f"S{m.group(2)}" if m else None


def utc_stamp(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S")


# ----- front matter -----


class FrontMatterError(ValueError):
    pass


def split_front_matter(text: str) -> tuple[dict, str]:
    """Split `---`-delimited YAML front matter from the Markdown body."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 3)
    if end == -1:
        if text.rstrip().endswith("\n---"):
            end = text.rstrip().rfind("\n---")
            header, body = text[4:end], ""
        else:
            raise FrontMatterError("front matter opened with --- but never closed")
    else:
        header, body = text[4:end], text[end + 5 :]
    try:
        meta = yaml.safe_load(header) or {}
    except yaml.YAMLError as exc:
        raise FrontMatterError(f"invalid YAML in front matter: {exc}") from exc
    if not isinstance(meta, dict):
        raise FrontMatterError("front matter is not a mapping")
    return _plain(meta), body


def _plain(value: Any) -> Any:
    """Turn YAML dates into ISO strings so values compare and print simply."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    return value


def id_list(value: Any) -> list[str]:
    """Normalise a reference field (null, a single ID, or a list) to a list of IDs."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return [str(value).strip()]


def dump_front_matter(meta: dict, body: str = "") -> str:
    """Serialise a record the way scripts write it."""
    header = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000).strip()
    return f"---\n{header}\n---\n{body}"


# ----- records -----


@dataclass
class Problem:
    """Something wrong with a file, found while loading or checking."""

    severity: str  # "error" or "warning"
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity}: {self.path}: {self.message}"


@dataclass
class Card:
    id: str
    kind: str
    statement: str
    path: str
    body: str
    depends_on: list[str]
    supersedes: list[str]
    refutes: list[str]
    produced_by: dict
    session: str | None
    meta: dict


@dataclass
class Artefact:
    """A derivation or computation, represented by its one-page summary."""

    id: str
    kind: str  # "derivation" or "computation"
    path: str  # the summary file
    supports: list[str]
    full: list[str]  # the full material (.tex, .py, .out, data files)
    meta: dict


@dataclass
class Review:
    """A review of an artefact: blind, by an agent, or a human verification recorded by a session."""

    id: str
    path: str
    target: str | None
    supports: list[str]
    verdict: str
    by: dict
    claim: str
    session: str | None
    date: str
    meta: dict

    @property
    def by_human(self) -> bool:
        return self.by.get("kind") == "human"


@dataclass
class Paper:
    id: str
    path: str
    title: str
    year: Any
    meta: dict

    @property
    def why(self) -> str:
        return str(self.meta.get("why") or "").strip()

    @property
    def topic(self) -> str:
        return str(self.meta.get("topic") or "").strip()

    @property
    def rating(self) -> str:
        """The agent's estimate of how much the paper matters here (the researcher's is in ratings.yaml)."""
        return str(self.meta.get("rating") or "").strip().lower()


@dataclass
class Session:
    id: str
    number: int
    path: str
    brief: dict | None = None
    debrief: Debrief | None = None
    received: dict | None = None  # front matter of received.md, written by session.py start
    has_note: bool = False
    has_log: bool = False

    @property
    def goal(self) -> str:
        return str((self.brief or {}).get("goal", "")).strip()


@dataclass
class Evidence:
    """One piece of support for a claim: an artefact, with the reviews of it that concern the claim."""

    artefact: str
    reviews: list[Review]
    attached_by: str | None = None  # review that attached the artefact to the claim

    @property
    def confirmed(self) -> bool:
        return any(r.verdict == "confirmed" for r in self.reviews)


# ----- the workspace -----


def find_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default: cwd) to the folder holding project.toml."""
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / "project.toml").is_file():
            return folder
    raise SystemExit("No project.toml found here or in a parent folder; is this a PhysicsIntern workspace?")


class Workspace:
    """Everything the files of a workspace say, with computed status and evidence."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.problems: list[Problem] = []
        self.project: dict = {}
        self.project_doc: Project | None = None
        self.cards: dict[str, Card] = {}
        self.artefacts: dict[str, Artefact] = {}
        self.reviews: dict[str, Review] = {}
        self.papers: dict[str, Paper] = {}
        self.ratings: dict[str, str] = {}
        self.critiques: dict[str, dict] = {}
        self.sessions: dict[str, Session] = {}
        self.draft: list[DraftBlock] = []
        self._load()
        self._recheck_cache: dict[str, list[str]] = {}

    # --- project settings ---

    @property
    def hub(self) -> dict:
        return self.project.get("hub") or {}

    @property
    def mode(self) -> str:
        return "shared" if self.hub.get("workspace") else "local"

    @property
    def leads(self) -> list[str]:
        return list((self.project.get("people") or {}).get("leads") or [])

    # --- loading ---

    def _problem(self, severity: str, path: Path | str, message: str) -> None:
        self.problems.append(Problem(severity, str(path), message))

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _read(self, path: Path) -> tuple[dict, str] | None:
        try:
            return split_front_matter(path.read_text(encoding="utf-8"))
        except (FrontMatterError, UnicodeDecodeError) as exc:
            self._problem("error", self._rel(path), str(exc))
            return None

    def text(self, rel: str) -> str:
        """A workspace file's text, or '' if it does not exist."""
        path = self.root / rel
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else ""
        except UnicodeDecodeError:
            return ""

    def _load(self) -> None:
        project = self.root / "project.toml"
        if project.is_file():
            try:
                self.project = tomllib.loads(project.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as exc:
                self._problem("error", "project.toml", f"invalid TOML: {exc}")
        if (self.root / "project.md").is_file():
            self.project_doc = parse_project(self.text("project.md"))
        self.draft = parse_draft(self.text("draft.tex"))
        self.ratings = parse_ratings(self.text(RATINGS_FILE))
        self._load_cards()
        self._load_artefacts("derivations", "derivation")
        self._load_artefacts("computations", "computation")
        self._load_literature()
        self._load_critiques()
        self._load_sessions()

    def _load_cards(self) -> None:
        for path in sorted((self.root / "claims").glob("*.md")):
            parsed = self._read(path)
            if parsed is None:
                continue
            meta, body = parsed
            card_id = str(meta.get("id") or path.stem)
            self.cards[card_id] = Card(
                id=card_id,
                kind=str(meta.get("kind", "")),
                statement=str(meta.get("statement") or "").strip(),
                path=self._rel(path),
                body=body,
                depends_on=id_list(meta.get("depends_on")),
                supersedes=id_list(meta.get("supersedes")),
                refutes=id_list(meta.get("refutes")),
                produced_by=meta.get("produced_by") if isinstance(meta.get("produced_by"), dict) else {},
                session=(str(meta["session"]) if meta.get("session") else None),
                meta=meta,
            )

    def _load_artefacts(self, folder: str, kind: str) -> None:
        base = self.root / folder
        for path in sorted(base.glob("*.md")):
            name = path.name
            if "_R-" in name:
                self._load_review(path)
                continue
            if kind == "derivation":
                if not name.endswith(".summary.md"):
                    continue
                stem = name[: -len(".summary.md")]
            else:
                stem = path.stem
            parsed = self._read(path)
            if parsed is None:
                continue
            meta, _body = parsed
            art_id = str(meta.get("id") or stem)
            full = sorted(
                self._rel(p)
                for p in base.glob(f"{stem}.*")
                if p != path and not p.name.endswith(".md")
            )
            self.artefacts[art_id] = Artefact(
                id=art_id,
                kind=kind,
                path=self._rel(path),
                supports=id_list(meta.get("supports")),
                full=full,
                meta=meta,
            )

    def _load_review(self, path: Path) -> None:
        parsed = self._read(path)
        if parsed is None:
            return
        meta, _body = parsed
        review_id = str(meta.get("id") or path.stem)
        by = meta.get("by") if isinstance(meta.get("by"), dict) else {}
        target = meta.get("target")
        self.reviews[review_id] = Review(
            id=review_id,
            path=self._rel(path),
            target=str(target).strip() if target else None,
            supports=id_list(meta.get("supports")),
            verdict=str(meta.get("verdict", "")).strip().lower(),
            by=by,
            claim=str(meta.get("claim") or "").strip(),
            session=(str(meta["session"]) if meta.get("session") else None),
            date=str(meta.get("date") or ""),
            meta=meta,
        )

    def _load_literature(self) -> None:
        for path in sorted((self.root / "literature").glob("P-*.md")):
            parsed = self._read(path)
            if parsed is None:
                continue
            meta, _body = parsed
            paper_id = str(meta.get("id") or path.stem)
            self.papers[paper_id] = Paper(
                id=paper_id,
                path=self._rel(path),
                title=str(meta.get("title") or "").strip(),
                year=meta.get("year"),
                meta=meta,
            )

    def _load_critiques(self) -> None:
        for path in sorted((self.root / "critiques").glob("CR-*.md")):
            parsed = self._read(path)
            if parsed is None:
                continue
            meta, _body = parsed
            self.critiques[str(meta.get("id") or path.stem)] = meta

    def _load_sessions(self) -> None:
        base = self.root / "sessions"
        if not base.is_dir():
            return
        for folder in sorted(base.iterdir(), key=lambda p: natural_key(p.name)):
            m = SESSION_DIR_RE.match(folder.name)
            if not folder.is_dir() or not m:
                continue
            session = Session(id=folder.name, number=int(m.group(1)), path=self._rel(folder))
            for name, attr in (("brief.md", "brief"), ("received.md", "received")):
                if (folder / name).is_file():
                    parsed = self._read(folder / name)
                    if parsed is not None:
                        setattr(session, attr, parsed[0])
            if (folder / "debrief.md").is_file():
                session.debrief = parse_debrief((folder / "debrief.md").read_text(encoding="utf-8"))
            session.has_note = (folder / "note.tex").is_file()
            session.has_log = (folder / "log.md").is_file()
            self.sessions[session.id] = session

    # --- computed views ---

    def refuters(self, card_id: str) -> list[str]:
        return sorted(
            (c.id for c in self.cards.values() if c.kind == "dead-end" and card_id in c.refutes),
            key=natural_key,
        )

    def revisers(self, card_id: str) -> list[str]:
        return sorted(
            (c.id for c in self.cards.values() if c.kind == "claim" and card_id in c.supersedes),
            key=natural_key,
        )

    def in_draft(self, card_id: str) -> str | None:
        """'result' if a result environment of draft.tex names the card, else 'conjecture' if one does, else None."""
        kinds = {block.kind for block in self.draft if card_id in block.cards}
        return "result" if "result" in kinds else ("conjecture" if "conjecture" in kinds else None)

    def status(self, card_id: str) -> str:
        """Computed status of a card.

        Claims: `working` by default, `established` when a result environment
        of draft.tex names them, `refuted` when a dead-end card refutes them,
        `revised` when a claim card supersedes them. Refuted and revised win
        over established. Dead ends: `dead-end`.
        """
        card = self.cards.get(card_id)
        if card is None:
            return "missing"
        if card.kind == "dead-end":
            return "dead-end"
        if self.refuters(card_id):
            return "refuted"
        if self.revisers(card_id):
            return "revised"
        if self.in_draft(card_id) == "result":
            return "established"
        return "working"

    def needs_recheck(self, card_id: str) -> list[str]:
        """Refuted or revised cards that this card depends on, directly or not.

        Empty when nothing upstream is in doubt. Never stored, so it cannot go stale.
        """
        if card_id in self._recheck_cache:
            return self._recheck_cache[card_id]
        causes: set[str] = set()
        seen: set[str] = {card_id}
        stack = list(self.cards[card_id].depends_on) if card_id in self.cards else []
        while stack:
            dep = stack.pop()
            if dep in seen:
                continue
            seen.add(dep)
            if self.status(dep) in ("refuted", "revised"):
                causes.add(dep)
            if dep in self.cards:
                stack.extend(self.cards[dep].depends_on)
        result = sorted(causes, key=natural_key)
        self._recheck_cache[card_id] = result
        return result

    def reviews_of(self, artefact_id: str) -> list[Review]:
        return sorted(
            (r for r in self.reviews.values() if r.target == artefact_id),
            key=lambda r: natural_key(r.id),
        )

    def evidence(self, card_id: str) -> list[Evidence]:
        """Everything that supports a claim, with the reviews that bear on it.

        An artefact supports a claim when its summary names the claim in
        `supports`, or when a review of the artefact names the claim in
        `supports` (this is how existing work is attached to a later claim).
        A review concerns the claim when it names the claim in `supports`, or
        names nothing and the artefact itself names the claim. A human
        verification is a review like the others, with `by.kind: human`.
        """
        items: dict[str, Evidence] = {}
        for art in self.artefacts.values():
            if card_id in art.supports:
                items[art.id] = Evidence(artefact=art.id, reviews=[])
        for review in sorted(self.reviews.values(), key=lambda r: natural_key(r.id)):
            if card_id in review.supports and review.target in self.artefacts and review.target not in items:
                items[review.target] = Evidence(artefact=review.target, reviews=[], attached_by=review.id)
        for art_id, item in items.items():
            art_supports = self.artefacts[art_id].supports
            item.reviews = [
                r
                for r in self.reviews_of(art_id)
                if card_id in r.supports or (not r.supports and card_id in art_supports)
            ]
        return [items[k] for k in sorted(items, key=natural_key)]

    def sorted_cards(self, kind: str | None = None) -> list[Card]:
        cards = [c for c in self.cards.values() if kind is None or c.kind == kind]
        return sorted(cards, key=lambda c: natural_key(c.id))

    def draft_flags(self) -> list[str]:
        """Problems with the cards the draft names: what the next debrief should propose to change."""
        flags = []
        for block in self.draft:
            for card_id in block.cards:
                status = self.status(card_id)
                if status == "refuted":
                    flags.append(f"{card_id} ({block.kind} at line {block.line}) is refuted by "
                                 + ", ".join(self.refuters(card_id)))
                elif status == "revised":
                    flags.append(f"{card_id} ({block.kind} at line {block.line}) is revised by "
                                 + ", ".join(self.revisers(card_id)))
                elif status == "missing":
                    flags.append(f"{card_id} ({block.kind} at line {block.line}) has no card in claims/")
                elif self.needs_recheck(card_id):
                    flags.append(f"{card_id} ({block.kind} at line {block.line}) needs a re-check: it depends on "
                                 + ", ".join(self.needs_recheck(card_id)))
                elif block.kind == "result" and not any(e.confirmed for e in self.evidence(card_id)):
                    flags.append(f"{card_id} (result at line {block.line}) has no confirmed evidence")
        return flags


def markdown_sections(body: str) -> dict[str, str]:
    """Split a Markdown body into its `## ` sections, keyed by heading text."""
    sections: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current, lines = line[3:].strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def result_problems(ws: Workspace, card_id: str) -> list[str]:
    """Reasons a `result` environment of the draft may not name `card_id` (empty if it may).

    The card must be a claim, neither refuted nor revised, with at least one
    supporting artefact that has a confirming review (by an agent, or a human
    verification). Whether the evidence is robust enough is the researcher's
    judgment, expressed by ticking the line that copies the result.
    """
    card = ws.cards.get(card_id)
    if card is None:
        return [f"there is no card {card_id} in claims/"]
    if card.kind != "claim":
        return [f"{card_id} is a {card.kind} card; only claims can be results"]
    reasons = []
    status = ws.status(card_id)
    if status in ("refuted", "revised"):
        reasons.append(f"{card_id} is {status}")
    if not any(item.confirmed for item in ws.evidence(card_id)):
        reasons.append(f"{card_id} has no supporting artefact with a confirming review (by an agent, or a human "
                       "verification)")
    return reasons
