"""Read a PhysicsIntern workspace and compute what follows from its files.

A workspace stores results as small Markdown files with a YAML front matter:
cards in `claims/`, artefact summaries and reviews in `derivations/` and
`computations/`, reactions, human reviews and promotion records in
`feedback/`, paper cards in `literature/`, and one folder per session in
`sessions/`. Files are never edited after they are created; everything that
happens to a card later is a new file that names it.

This module loads those files and computes, for each card, its status, its
evidence and whether it needs a re-check. Nothing it computes is stored. It is
imported by regen.py, check.py, session.py, promote.py and the Space, so it
must stay free of side effects. Requires PyYAML.
"""

from __future__ import annotations

import datetime as _dt
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ----- identifiers -----

CARD_KINDS = {"claim": "CL", "question": "Q", "dead-end": "DE"}
PREFIX_TO_KIND = {prefix: kind for kind, prefix in CARD_KINDS.items()}

# Items created inside a session: CL-S12-2, D-S12-3, C-S12-1, CR-S12-1, ...
SESSION_ID_RE = re.compile(r"^(CL|Q|DE|D|C|CR)-S(\d+)-(\d+)$")
# Items created outside a session (from the Space): CL-alice-20261005T141233
USER_ID_RE = re.compile(r"^(CL|Q|DE|R)-([A-Za-z0-9][A-Za-z0-9._-]*)-(\d{8}T\d{6})$")
# Agent reviews sit next to their target: D-S3-2_R-S7-1
REVIEW_ID_RE = re.compile(r"^((?:D|C)-S\d+-\d+)_R-S(\d+)-(\d+)$")
PAPER_ID_RE = re.compile(r"^P-[A-Za-z0-9._-]+$")
SESSION_DIR_RE = re.compile(r"^S(\d+)$")

VERDICTS = ("confirmed", "refuted", "inconclusive")
CLAIM_REACTIONS = ("convinced", "doubtful", "wrong")
PAPER_REACTIONS = ("key", "useful", "irrelevant")

# Files the lead scientist owns. Sessions never touch them in shared mode.
LEAD_FILES = ("problem.md", "plan.md", "conventions.md", "literature/seeds.md")


def natural_key(text: str) -> list:
    """Sort key that orders `S2` before `S10` and `CL-S3-2` before `CL-S3-10`."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def session_of(item_id: str) -> str | None:
    """Return the session (e.g. `S12`) embedded in an ID, or None."""
    m = REVIEW_ID_RE.match(item_id) or SESSION_ID_RE.match(item_id)
    return f"S{m.group(2)}" if m else None


def utc_stamp(now: _dt.datetime | None = None) -> str:
    """Timestamp used in IDs and file names of items written outside a session."""
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
    """Serialise a record the way scripts and the Space write it."""
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
    answers: list[str]
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
    """A review of an artefact, by an agent, or a human verification."""

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
class Reaction:
    path: str
    target: str
    value: str
    user: str
    date: str
    comment: str


@dataclass
class Promotion:
    path: str
    target: str
    by: dict
    date: str
    session: str | None
    reason: str


@dataclass
class Paper:
    id: str
    path: str
    title: str
    year: Any
    meta: dict


@dataclass
class Session:
    id: str
    number: int
    path: str
    brief: dict | None = None
    report: dict | None = None
    report_sections: dict[str, str] = field(default_factory=dict)
    has_log: bool = False

    @property
    def goal(self) -> str:
        return str((self.brief or {}).get("goal", "")).strip()


@dataclass
class Evidence:
    """One piece of support for a card.

    Either an artefact (with the reviews of it that concern the card) or a
    human verification that names the card directly.
    """

    artefact: str | None
    reviews: list[Review]
    attached_by: str | None = None  # review that attached the artefact to the card
    verification: Review | None = None

    @property
    def confirmed(self) -> bool:
        if self.verification is not None:
            return self.verification.verdict == "confirmed"
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
        self.cards: dict[str, Card] = {}
        self.artefacts: dict[str, Artefact] = {}
        self.reviews: dict[str, Review] = {}
        self.reactions: list[Reaction] = []
        self.promotions: list[Promotion] = []
        self.papers: dict[str, Paper] = {}
        self.surveys: list[str] = []
        self.critiques: dict[str, dict] = {}
        self.sessions: dict[str, Session] = {}
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

    def _load(self) -> None:
        project = self.root / "project.toml"
        if project.is_file():
            try:
                self.project = tomllib.loads(project.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as exc:
                self._problem("error", "project.toml", f"invalid TOML: {exc}")
        self._load_cards()
        self._load_artefacts("derivations", "derivation")
        self._load_artefacts("computations", "computation")
        self._load_feedback()
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
                answers=id_list(meta.get("answers")),
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

    def _load_feedback(self) -> None:
        for path in sorted((self.root / "feedback").glob("*.md")):
            parsed = self._read(path)
            if parsed is None:
                continue
            meta, body = parsed
            kind = meta.get("kind")
            by = meta.get("by") if isinstance(meta.get("by"), dict) else {}
            if kind == "review":
                self._load_review(path)
            elif kind == "reaction":
                self.reactions.append(
                    Reaction(
                        path=self._rel(path),
                        target=str(meta.get("target") or ""),
                        value=str(meta.get("value") or ""),
                        user=str(by.get("user") or ""),
                        date=str(meta.get("date") or ""),
                        comment=body.strip().splitlines()[0] if body.strip() else "",
                    )
                )
            elif kind == "promotion":
                self.promotions.append(
                    Promotion(
                        path=self._rel(path),
                        target=str(meta.get("target") or ""),
                        by=by,
                        date=str(meta.get("date") or ""),
                        session=(str(meta["session"]) if meta.get("session") else None),
                        reason=body.strip(),
                    )
                )
            else:
                self._problem("error", self._rel(path), f"unknown feedback kind {kind!r}")

    def _load_literature(self) -> None:
        lit = self.root / "literature"
        for path in sorted(lit.glob("P-*.md")):
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
        self.surveys = sorted((p.stem for p in lit.glob("survey-S*.md")), key=natural_key)

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
            if (folder / "brief.md").is_file():
                parsed = self._read(folder / "brief.md")
                if parsed is not None:
                    session.brief = parsed[0]
            if (folder / "report.md").is_file():
                parsed = self._read(folder / "report.md")
                if parsed is not None:
                    session.report = parsed[0]
                    session.report_sections = markdown_sections(parsed[1])
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

    def answerers(self, card_id: str) -> list[str]:
        return sorted(
            (c.id for c in self.cards.values() if card_id in c.answers),
            key=natural_key,
        )

    def promotion_is_valid(self, promotion: Promotion) -> bool:
        """A promotion counts if its author may promote (leads only, in shared mode)."""
        if self.mode == "shared":
            return promotion.by.get("kind") == "human" and promotion.by.get("user") in self.leads
        return True

    def promotions_of(self, card_id: str) -> list[Promotion]:
        return [p for p in self.promotions if p.target == card_id]

    def status(self, card_id: str) -> str:
        """Computed status of a card.

        Claims: `working` by default, `established` after a valid promotion,
        `refuted` when a dead-end card refutes them, `revised` when a claim card
        supersedes them. Refuted and revised win over established. Questions:
        `open` until a card answers them, then `answered`. Dead ends: `dead-end`.
        """
        card = self.cards.get(card_id)
        if card is None:
            return "missing"
        if card.kind == "question":
            return "answered" if self.answerers(card_id) else "open"
        if card.kind == "dead-end":
            return "dead-end"
        if self.refuters(card_id):
            return "refuted"
        if self.revisers(card_id):
            return "revised"
        if any(self.promotion_is_valid(p) for p in self.promotions_of(card_id)):
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
        """Everything that supports a card, with the reviews that bear on it.

        An artefact supports a card when its summary names the card in
        `supports`, or when a review of the artefact names the card in
        `supports` (this is how existing work is attached to a later card).
        A review concerns the card when it names the card in `supports`, or
        names nothing and the artefact itself names the card. Human reviews
        without an artefact target are direct verifications.
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
        result = [items[k] for k in sorted(items, key=natural_key)]
        for review in sorted(self.reviews.values(), key=lambda r: natural_key(r.id)):
            direct = review.target is None or review.target == card_id
            if review.by_human and direct and card_id in review.supports:
                result.append(Evidence(artefact=None, reviews=[], verification=review))
        return result

    def current_reactions(self, target: str) -> list[Reaction]:
        """One reaction per person: the latest one each person left on `target`."""
        latest: dict[str, Reaction] = {}
        for reaction in sorted(
            (r for r in self.reactions if r.target == target), key=lambda r: (r.date, r.path)
        ):
            latest[reaction.user] = reaction
        return [latest[u] for u in sorted(latest)]

    def sorted_cards(self, kind: str | None = None) -> list[Card]:
        cards = [c for c in self.cards.values() if kind is None or c.kind == kind]
        return sorted(cards, key=lambda c: natural_key(c.id))


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


def promotion_problems(ws: Workspace, card_id: str, by: dict) -> list[str]:
    """Reasons a promotion of `card_id` by `by` would be refused (empty if allowed).

    Only what a script can verify: the author may promote, the card is a claim
    that is neither refuted nor revised, and it has a supporting artefact with a
    confirming review or a human verification. Whether the evidence is robust
    enough is a judgment left to the person promoting.
    """
    reasons = []
    if ws.mode == "shared":
        if by.get("kind") != "human":
            reasons.append("in shared mode only a lead can promote, and agents cannot")
        elif by.get("user") not in ws.leads:
            reasons.append(f"{by.get('user') or 'unknown user'} is not in [people] leads of project.toml")
    card = ws.cards.get(card_id)
    if card is None:
        reasons.append(f"no card {card_id} in claims/")
        return reasons
    if card.kind != "claim":
        reasons.append(f"{card_id} is a {card.kind} card; only claims can be promoted")
        return reasons
    status = ws.status(card_id)
    if status in ("refuted", "revised"):
        reasons.append(f"{card_id} is {status}")
    if not any(item.confirmed for item in ws.evidence(card_id)):
        reasons.append(
            f"{card_id} has neither a supporting artefact with a confirming review nor a human verification"
        )
    return reasons
