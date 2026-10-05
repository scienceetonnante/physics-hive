"""Workspace access for the PhysicsIntern Space, without any user interface.

The Space shows a workspace to people who only use a browser, and writes what
they do there: reactions, cards, verifications, promotions and edits of the
lead's files. Everything except the page layout lives in this module, so that
it can be tested on a folder.

Two ways to reach a workspace:

- In the deployed Space, the workspace is a private dataset repository on the
  Hub, named by the Space variable `PHYSICS_INTERN_WORKSPACE` (org/name). It is
  downloaded with the Space secret `HF_TOKEN`, refreshed on demand and after
  each write, and every write is a commit made with that token, whose message
  names the signed-in user.
- For development and tests, `PHYSICS_INTERN_LOCAL=/path/to/workspace` reads a
  folder directly and writes files into it instead of committing. The
  signed-in user is then `PHYSICS_INTERN_LOCAL_USER`.

What the files mean (status, evidence, needs re-check, current reactions, the
promotion rule, the checks) comes from the workspace's own copy of the method
scripts, `.physics-intern/scripts/`, imported again at every refresh. The Space
therefore computes exactly what `regen` and `check` compute for that workspace.
Every write is a new file with a unique name, except a lead's edit of a lead's
file, so writes from the Space never conflict with sessions.
"""

from __future__ import annotations

import datetime as dt
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from huggingface_hub import CommitOperationAdd, HfApi, snapshot_download
from huggingface_hub.utils import disable_progress_bars

disable_progress_bars()

DATASET = "dataset"
# Fallback method scripts for a workspace without a method copy (the test toys):
# this repository's scripts/, or those of the method copy this app sits in.
REPO_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
# Modules of the method copy that import each other by plain name.
METHOD_MODULES = ("cards", "common", "regen", "check", "promote")
MAX_AGE = 120  # seconds after which a page load refreshes the workspace
MAX_CHARS = 60_000  # longest file shown in full in the page

# Values shown as buttons and choices. The workspace's own cards.py and check.py
# decide at write time what is allowed.
CLAIM_REACTIONS = ("convinced", "doubtful", "wrong")
PAPER_REACTIONS = ("key", "useful", "irrelevant")
VERDICTS = ("confirmed", "refuted", "inconclusive")
LEAD_FILES = ("problem.md", "plan.md", "conventions.md", "literature/seeds.md")

# Filters of the Results page: label -> (card kind, status), None meaning any.
FILTERS = {
    "All cards": (None, None),
    "Working claims": ("claim", "working"),
    "Established claims": ("claim", "established"),
    "Revised claims": ("claim", "revised"),
    "Refuted claims": ("claim", "refuted"),
    "Open questions": ("question", "open"),
    "Answered questions": ("question", "answered"),
    "Dead ends": ("dead-end", None),
    "Needing a re-check": (None, "needs re-check"),
}
CODE_LANGUAGES = {".tex": "latex", ".py": "python", ".json": "json", ".md": "markdown"}


class SpaceError(Exception):
    """A problem to show to the person using the Space, in plain words."""


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(moment: dt.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def clip(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[… cut here: the file has {len(text)} characters, of which the first {limit} are shown]"


def demote_headings(text: str, levels: int = 2) -> str:
    """Make the headings of an included file smaller, so that they sit under the page's own."""
    return re.sub(r"^(#{1,6}) ", lambda m: "#" * min(6, len(m.group(1)) + levels) + " ", text, flags=re.M)


def is_session_pr(pr: dict) -> bool:
    """Session pull requests are titled `[S12] …`; just after the claim, `[draft] session by …`."""
    return pr["title"].startswith(("[S", "[draft] session"))


# ----- the method copy -----


def method_scripts(root: Path) -> Path:
    """The scripts of the workspace's method copy, or the fallback ones for a toy workspace."""
    for folder in (root / ".physics-intern" / "scripts", REPO_SCRIPTS):
        if (folder / "cards.py").is_file():
            return folder
    raise SpaceError("The workspace has no method copy (.physics-intern/scripts/cards.py), so the Space "
                     "cannot interpret its files.")


def load_method(scripts: Path) -> SimpleNamespace:
    """Import cards, regen, check and promote from `scripts`, leaving other imports untouched.

    The scripts import each other by plain name (`from cards import ...`), so they
    are imported with `scripts` first on sys.path. Afterwards sys.path and
    sys.modules are restored, so that two method copies never mix and nothing
    else in the process sees these modules under their plain names.
    """
    saved_modules = {name: sys.modules.pop(name) for name in METHOD_MODULES if name in sys.modules}
    saved_path, saved_bytecode = list(sys.path), sys.dont_write_bytecode
    sys.path.insert(0, str(scripts))
    sys.dont_write_bytecode = True  # do not write __pycache__ into the workspace
    try:
        importlib.invalidate_caches()
        return SimpleNamespace(**{name: importlib.import_module(name) for name in ("cards", "regen", "check", "promote")})
    finally:
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_bytecode
        for name in METHOD_MODULES:
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


# ----- where the workspace lives -----


class LocalStore:
    """A workspace folder on this machine, for development and tests. Writes are plain files."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.label = str(self.root)

    def snapshot(self) -> tuple[Path, str | None]:
        if not (self.root / "project.toml").is_file():
            raise SpaceError(f"{self.root} is not a PhysicsIntern workspace (it has no project.toml).")
        return self.root, None

    def commit(self, files: dict[str, str], message: str, parent: str | None = None) -> None:
        for rel, content in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def propose(self, path: str, content: str, title: str, description: str) -> tuple[int, str]:
        raise SpaceError("This Space reads a local folder, which has no pull requests, so only a lead can save "
                         "the lead's files here.")

    def merge(self, number: int, comment: str) -> None:
        raise SpaceError("This Space reads a local folder, which has no pull requests.")

    def pull_requests(self) -> list[dict]:
        return []

    def recent_commits(self, n: int) -> list[dict]:
        if not (self.root / ".git").exists():
            return []
        proc = subprocess.run(["git", "log", f"-n{n}", "--format=%cI%x1f%an%x1f%s"], cwd=self.root,
                              capture_output=True, text=True)
        rows = []
        for line in proc.stdout.splitlines():
            date, author, title = (line.split("\x1f") + ["", ""])[:3]
            rows.append({"date": date[:16].replace("T", " "), "authors": [author], "title": title})
        return rows

    def chat_log_target(self, hub: dict) -> str:
        return os.environ.get("PHYSICS_INTERN_CHAT_LOG") or str(Path(tempfile.gettempdir()) / "physics-intern-chat-debug.jsonl")

    def log_chat(self, record: dict, hub: dict) -> None:
        with open(self.chat_log_target(hub), "a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")


class HubStore:
    """The workspace as a private dataset repository on the Hub, read and written with the Space's token."""

    def __init__(self, repo_id: str, token: str, api: HfApi | None = None):
        self.repo_id, self.token = repo_id, token
        self.api = api or HfApi(token=token)
        self.label = repo_id

    def snapshot(self) -> tuple[Path, str]:
        """Download main as it is now. Each commit gets its own folder in the Hub cache."""
        try:
            revision = self.api.repo_info(self.repo_id, repo_type=DATASET).sha
            path = snapshot_download(self.repo_id, repo_type=DATASET, revision=revision, token=self.token)
        except Exception as exc:
            raise SpaceError(f"The Space could not read the workspace {self.repo_id} from the Hub "
                             f"({type(exc).__name__}: {exc}). Check that the Space secret HF_TOKEN is a token "
                             "that can read and write this repository.") from exc
        return Path(path), revision

    def commit(self, files: dict[str, str], message: str, parent: str | None = None) -> None:
        operations = [CommitOperationAdd(path_in_repo=rel, path_or_fileobj=content.encode("utf-8"))
                      for rel, content in files.items()]
        self.api.create_commit(self.repo_id, operations, commit_message=message, repo_type=DATASET,
                               parent_commit=parent)

    def propose(self, path: str, content: str, title: str, description: str) -> tuple[int, str]:
        info = self.api.create_commit(self.repo_id, [CommitOperationAdd(path, content.encode("utf-8"))],
                                      commit_message=title, commit_description=description,
                                      repo_type=DATASET, create_pr=True)
        return info.pr_num, info.pr_url

    def merge(self, number: int, comment: str) -> None:
        self.api.merge_pull_request(self.repo_id, number, repo_type=DATASET, comment=comment)

    def pull_requests(self) -> list[dict]:
        rows = []
        for d in self.api.get_repo_discussions(self.repo_id, repo_type=DATASET, discussion_type="pull_request"):
            rows.append({"num": d.num, "title": d.title, "status": d.status, "author": d.author,
                         "date": d.created_at.strftime("%Y-%m-%d") if d.created_at else "", "url": d.url})
        return sorted(rows, key=lambda r: -r["num"])

    def recent_commits(self, n: int) -> list[dict]:
        commits = self.api.list_repo_commits(self.repo_id, repo_type=DATASET)[:n]
        return [{"date": c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
                 "authors": list(c.authors or []), "title": c.title} for c in commits]

    def chat_log_target(self, hub: dict) -> str | None:
        return hub.get("chat_debug") or None

    def log_chat(self, record: dict, hub: dict) -> None:
        """Add one exchange as a new file of the chat_debug dataset, without making the reader wait."""
        repo = self.chat_log_target(hub)
        if not repo:
            return
        stamp = record["date"].replace(":", "").replace("-", "")
        name = f"exchanges/{record['date'][:10]}/{stamp}-{record['user']}-{uuid.uuid4().hex[:8]}.json"
        future = self.api.create_commit(repo, [CommitOperationAdd(name, json.dumps(record, ensure_ascii=False, indent=1).encode())],
                                        commit_message=f"Chat exchange ({record['user']})", repo_type=DATASET,
                                        run_as_future=True)
        future.add_done_callback(lambda f: f.exception() and print(f"chat debug log failed: {f.exception()}", file=sys.stderr))


# ----- the backend -----


@dataclass
class Snapshot:
    """One loaded state of the workspace, with the method modules that interpret it."""

    root: Path
    revision: str | None  # commit of main (Hub), None for a local folder
    m: SimpleNamespace  # cards, regen, check and promote from the workspace's method copy
    ws: object  # cards.Workspace
    loaded_at: float


class Backend:
    """Computed views of one workspace for the pages, and every write the Space makes."""

    def __init__(self, store: LocalStore | HubStore | None = None, *, local_user: str | None = None,
                 chat_debug: bool = False, error: str | None = None):
        self.store = store
        self.local_user = local_user
        self.chat_debug = chat_debug
        self.snap: Snapshot | None = None
        self.error = error  # why the workspace cannot be shown, if it cannot
        self.pull_requests: list[dict] = []
        self.commits: list[dict] = []
        self.commits_of: str | None = None  # the main commit that self.commits was listed at
        self.notes: list[str] = []  # things that failed without blocking the pages
        self._lock = threading.RLock()

    @classmethod
    def from_env(cls, env: dict | None = None) -> Backend:
        env = os.environ if env is None else env
        debug = env.get("CHAT_DEBUG", "0").strip() == "1"
        if env.get("PHYSICS_INTERN_LOCAL"):
            return cls(LocalStore(env["PHYSICS_INTERN_LOCAL"]), local_user=env.get("PHYSICS_INTERN_LOCAL_USER") or None,
                       chat_debug=debug)
        repo = env.get("PHYSICS_INTERN_WORKSPACE", "").strip()
        token = env.get("HF_TOKEN", "").strip()
        if not repo:
            return cls(chat_debug=debug, error="This Space does not know which workspace to show: the Space "
                       "variable PHYSICS_INTERN_WORKSPACE (org/name) is not set.")
        if not token:
            return cls(chat_debug=debug, error=f"This Space cannot read the workspace {repo}: the Space secret "
                       f"HF_TOKEN is not set. A lead adds it in the Space settings (a token that can read and write {repo}).")
        return cls(HubStore(repo, token), chat_debug=debug)

    @property
    def local(self) -> bool:
        return isinstance(self.store, LocalStore)

    def user(self, signed_in: str | None) -> str | None:
        """The person behind a request: the signed-in Hugging Face user, or the local user in local mode."""
        return self.local_user if self.local else signed_in

    # --- loading ---

    def _load(self) -> Snapshot:
        if self.store is None:
            raise SpaceError(self.error or "The Space has no workspace configured.")
        root, revision = self.store.snapshot()
        m = load_method(method_scripts(root))
        self.snap = Snapshot(root, revision, m, m.cards.Workspace(root), time.time())
        return self.snap

    def _fresh(self) -> Snapshot:
        """The workspace as it is now on main; every write starts from it."""
        try:
            return self._load()
        except SpaceError:
            raise
        except Exception as exc:
            raise SpaceError(f"The workspace could not be loaded ({type(exc).__name__}: {exc}).") from exc

    def refresh(self) -> None:
        """Load the latest workspace, pull requests and recent commits. Shows problems instead of raising."""
        if self.store is None:
            return
        with self._lock:
            try:
                snap = self._fresh()
            except SpaceError as exc:
                self.error = str(exc)
                return
            self.error, self.notes = None, []
            try:
                self.pull_requests = self.store.pull_requests()
            except Exception as exc:
                self.notes.append(f"the pull requests could not be listed ({type(exc).__name__})")
            # Listing commits reads the whole history on the Hub, so do it only when main has moved.
            if snap.revision is None or snap.revision != self.commits_of:
                try:
                    self.commits, self.commits_of = self.store.recent_commits(15), snap.revision
                except Exception as exc:
                    self.notes.append(f"the recent commits could not be listed ({type(exc).__name__})")

    def refresh_if_stale(self, max_age: float = MAX_AGE) -> None:
        if self.snap is None or time.time() - self.snap.loaded_at > max_age:
            self.refresh()

    def current(self) -> Snapshot:
        """The loaded workspace, or a SpaceError saying why there is none.

        It loads the workspace the first time. After a failed load it does not
        try again by itself; a page load or the Refresh button does.
        """
        if self.snap is None and not self.error:
            self.refresh()
        if self.snap is None:
            raise SpaceError(self.error or "The workspace is not loaded.")
        return self.snap

    def read(self, rel: str) -> str:
        """Text of a workspace file ('' if it does not exist)."""
        path = self.current().root / rel
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
        except UnicodeDecodeError:
            return "(binary file, not shown)"

    def body(self, rel: str) -> str:
        """A record's Markdown body, without its front matter."""
        text = self.read(rel)
        try:
            return self.current().m.cards.split_front_matter(text)[1].strip()
        except ValueError:
            return text.strip()

    # --- small helpers for the pages ---

    def is_lead(self, user: str | None) -> bool:
        try:
            return bool(user) and user in self.current().ws.leads
        except SpaceError:
            return False

    def chat_model(self) -> str | None:
        return (self.current().ws.project.get("models") or {}).get("chat")

    def chat_log_target(self) -> str | None:
        if self.store is None:
            return None
        hub = self.snap.ws.hub if self.snap else {}
        return self.store.chat_log_target(hub)

    def status_markdown(self) -> str:
        if self.snap is None:
            return f"**{self.error}**" if self.error else "Loading…"
        ws = self.snap.ws
        version = (ws.project.get("method") or {}).get("physics_intern_version", "?")
        where = f"local folder `{self.store.label}`" if self.local else f"workspace **{self.store.label}**"
        commit = f", main at `{self.snap.revision[:8]}`" if self.snap.revision else ""
        loaded = time.strftime("%H:%M UTC", time.gmtime(self.snap.loaded_at))
        line = f"Reading the {where}{commit} (loaded {loaded}, method {version})."
        if self.error:
            line += f" **The last refresh failed:** {self.error}"
        if self.notes:
            line += " Note: " + "; ".join(self.notes) + "."
        return line

    def who_markdown(self, user: str | None) -> str:
        if user:
            role = "a lead" if self.is_lead(user) else "a member (not a lead)"
            text = f"Signed in as **{user}**, {role}."
        elif self.local:
            text = "No user: set PHYSICS_INTERN_LOCAL_USER to write."
        else:
            text = "Not signed in: you can read; sign in to react, write or verify."
        if self.local:
            text += " Local mode: writes go to files in the folder, without commits."
        return text

    def chat_banner(self) -> str:
        if not self.chat_debug:
            return ""
        if self.snap is None:
            return "**Debug mode: chat conversations are logged**, outside the workspace."
        target = self.chat_log_target()
        if target:
            return (f"**Debug mode: chat conversations are logged** (to `{target}`), with your user name, so that "
                    "the lead can tune the explainer. They are never written to the workspace.")
        return "**Debug mode is on**, but project.toml names no chat_debug dataset, so nothing is stored."

    def choices(self, kind: str | None = None, status: str | None = None) -> list[tuple[str, str]]:
        """(label, ID) of the cards of a kind and status, for the forms."""
        snap = self.current()
        one_line = snap.m.regen.one_line
        return [(f"{c.id} — {one_line(c.statement, 90)}", c.id) for c in snap.ws.sorted_cards(kind)
                if status is None or snap.ws.status(c.id) == status]

    # --- Overview ---

    def overview_markdown(self) -> str:
        snap = self.current()
        problem = self.read("problem.md")
        plan = self.read("plan.md")
        out = ["## The question", "",
               demote_headings(problem.strip()) if _has_text(problem) else "*problem.md is still empty: the lead has not written the question yet.*",
               "", "## Current strategy", "",
               demote_headings(plan.strip()) if _has_text(plan) else "*plan.md is still empty.*",
               "", "## Where things stand", "", snap.m.regen.summary(snap.ws) + ".", "", "## Active sessions", ""]
        if self.local:
            out.append("*This Space reads a local folder: sessions are pull requests on the Hub, so none are listed here.*")
        else:
            out += [_pr_line(pr) for pr in self.open_sessions()] or ["No session is running."]
        out += ["", "## Recent changes", ""]
        out += [f"- {c['date']} · {c['title']} · {', '.join(c['authors'])}" for c in self.commits] or ["(none found)"]
        return "\n".join(out)

    # --- Results ---

    def matching_cards(self, filter_name: str = "All cards", query: str = "") -> list:
        ws = self.current().ws
        kind, status = FILTERS.get(filter_name or "All cards", (None, None))
        words = (query or "").lower().split()
        found = []
        for card in ws.sorted_cards(kind):
            if status == "needs re-check":
                if not ws.needs_recheck(card.id):
                    continue
            elif status and ws.status(card.id) != status:
                continue
            if all(w in f"{card.id} {card.statement}".lower() for w in words):
                found.append(card)
        return found

    def index_markdown(self, filter_name: str = "All cards", query: str = "") -> str:
        snap = self.current()
        cards = self.matching_cards(filter_name, query)
        if not cards:
            return "*No card matches.*"
        proposals = snap.m.regen.proposed_promotions(snap.ws)
        lines = [snap.m.regen.card_line(snap.ws, card, proposals) for card in cards]
        return f"{len(cards)} card(s), one line each: status, statement, evidence, links.\n\n" + "\n".join(lines)

    def card_choices(self, filter_name: str = "All cards", query: str = "") -> list[tuple[str, str]]:
        one_line = self.current().m.regen.one_line
        return [(f"{c.id} — {one_line(c.statement, 90)}", c.id) for c in self.matching_cards(filter_name, query)]

    def related(self, card_id: str) -> list[tuple[str, list[str]]]:
        """The cards linked to a card, by relation, both ways."""
        ws = self.current().ws
        card = ws.cards.get(card_id)
        if card is None:
            return []
        dependents = [c.id for c in ws.sorted_cards() if card_id in c.depends_on]
        rows = [("Depends on", card.depends_on), ("Cards that depend on it", dependents),
                ("Supersedes", card.supersedes), ("Revised by", ws.revisers(card_id)),
                ("Refutes", card.refutes), ("Refuted by", ws.refuters(card_id)),
                ("Answers", card.answers), ("Answered by", ws.answerers(card_id))]
        return [(label, ids) for label, ids in rows if ids]

    def card_markdown(self, card_id: str | None) -> str:
        if not card_id:
            return "*Choose a card above.*"
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        card = ws.cards.get(card_id)
        if card is None:
            return f"*There is no card {card_id} in this workspace.*"
        out = [f"## {card.id}", "", f"**{card.kind}** · **{regen.status_text(ws, card.id)}**", "",
               f"> {regen.one_line(card.statement)}", ""]
        causes = ws.needs_recheck(card.id)
        if causes:
            out += ["**Needs re-check:** this card depends, directly or not, on "
                    + ", ".join(f"{c} ({ws.status(c)})" for c in causes) + ".", ""]
        if card.body.strip():
            out += [card.body.strip(), ""]
        out += [f"**Origin:** {origin_text(card)}", ""]
        traces = ws.hub.get("traces")
        if card.session and traces:
            url = f"https://huggingface.co/datasets/{traces}/tree/main/{card.session}"
            out += [f"**Trace:** the full record of session {card.session} is in [{traces}/{card.session}]({url}).", ""]
        for label, ids in self.related(card_id):
            out.append(f"**{label}**")
            for ref in ids:
                other = ws.cards.get(ref)
                text = f"{ws.status(ref)} — {regen.one_line(other.statement, 160)}" if other else "missing"
                out.append(f"- {ref} · {text}")
            out.append("")
        if card.kind == "claim":
            evidence = regen.evidence_parts(ws, card.id)
            out += [f"**Evidence:** {', '.join(evidence) if evidence else 'none yet'} (details below)", ""]
            proposed = regen.proposed_promotions(ws).get(card.id)
            if proposed and ws.status(card.id) == "working":
                out += [f"**Promotion proposed in:** {', '.join(proposed)}", ""]
        promotions = ws.promotions_of(card.id)
        if promotions:
            out.append("**Promotion history**")
            for p in promotions:
                who = p.by.get("user") or f"agent ({p.by.get('model', '?')})"
                note = "" if ws.promotion_is_valid(p) else " (not counted: its author is not a lead)"
                reason = f": {regen.one_line(p.reason, 300)}" if p.reason else ""
                out.append(f"- promoted by {who} on {p.date[:10]}{note}{reason}")
            out.append("")
        reactions = ws.current_reactions(card.id)
        out.append("**Reactions** (one per person, the latest; they carry no evidential weight)")
        out += [_reaction_line(r) for r in reactions] or ["- none yet"]
        return "\n".join(out)

    def evidence_items(self, card_id: str | None) -> list[dict]:
        """Each piece of evidence of a card, with its summary, full material and reviews."""
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        if not card_id or card_id not in ws.cards:
            return []
        items = []
        for ev in ws.evidence(card_id):
            if ev.verification is not None:
                r = ev.verification
                items.append({"title": f"Human verification {regen.review_label(r)}: {r.verdict}",
                              "summary": self.body(r.path) or "(no text)", "files": [], "reviews": []})
                continue
            art = ws.artefacts[ev.artefact]
            title = f"{art.id} ({art.kind})"
            if ev.attached_by:
                title += f", attached to this card by the review {ev.attached_by}"
            files = [{"path": p, "text": clip(self.read(p)), "language": CODE_LANGUAGES.get(Path(p).suffix)}
                     for p in art.full]
            reviews = [{"title": f"Review {regen.review_label(r)}: {r.verdict}", "body": self.body(r.path) or "(no text)"}
                       for r in ev.reviews]
            items.append({"title": title, "summary": self.body(art.path), "files": files, "reviews": reviews})
        return items

    def artefact_choices(self, card_id: str | None) -> list[str]:
        """Artefacts in a card's evidence, which a verification may name as its target."""
        ws = self.current().ws
        if not card_id or card_id not in ws.cards:
            return []
        return [ev.artefact for ev in ws.evidence(card_id) if ev.artefact]

    # --- Literature ---

    def papers_markdown(self) -> str:
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        if not ws.papers:
            return "*No paper cards yet.*"
        lines = []
        for paper_id in sorted(ws.papers, key=snap.m.cards.natural_key):
            p = ws.papers[paper_id]
            year = f" ({p.year})" if p.year else ""
            triage = regen.reaction_text(ws, paper_id) or "not triaged yet"
            lines.append(f"- **{paper_id}** — {regen.one_line(p.title, 160)}{year} — {triage}")
        return "\n".join(lines)

    def paper_choices(self) -> list[tuple[str, str]]:
        snap = self.current()
        return [(f"{pid} — {snap.m.regen.one_line(snap.ws.papers[pid].title, 80)}", pid)
                for pid in sorted(snap.ws.papers, key=snap.m.cards.natural_key)]

    def paper_markdown(self, paper_id: str | None) -> str:
        if not paper_id:
            return "*Choose a paper above.*"
        ws = self.current().ws
        paper = ws.papers.get(paper_id)
        if paper is None:
            return f"*There is no paper card {paper_id}.*"
        meta = paper.meta
        authors = meta.get("authors") or []
        details = [", ".join(map(str, authors)) if isinstance(authors, list) else str(authors)]
        if paper.year:
            details.append(str(paper.year))
        if meta.get("arxiv"):
            details.append(f"[arXiv:{meta['arxiv']}](https://arxiv.org/abs/{meta['arxiv']})")
        if meta.get("doi"):
            details.append(f"doi:{meta['doi']}")
        out = [f"## {paper.title or paper_id}", "", " · ".join(d for d in details if d), "",
               demote_headings(self.body(paper.path), 1), "",
               "**Triage** (one per person, the latest)"]
        out += [_reaction_line(r) for r in ws.current_reactions(paper_id)] or ["- none yet"]
        return "\n".join(out)

    # --- Sessions and proposals ---

    def open_sessions(self) -> list[dict]:
        return [pr for pr in self.pull_requests if is_session_pr(pr) and pr["status"] in ("draft", "open")]

    def proposal_prs(self) -> list[dict]:
        return [pr for pr in self.pull_requests if not is_session_pr(pr) and pr["status"] in ("draft", "open")]

    def open_sessions_markdown(self) -> str:
        if self.local:
            return "*This Space reads a local folder: open sessions are pull requests on the Hub, so none are listed.*"
        return "\n".join(_pr_line(pr) for pr in self.open_sessions()) or "No session is running."

    def proposals_markdown(self) -> str:
        if self.local:
            return "*This Space reads a local folder, which has no pull requests.*"
        return "\n".join(_pr_line(pr) for pr in self.proposal_prs()) or "No open proposal."

    def session_views(self) -> list[dict]:
        """Sessions with a brief or a report, newest first, with the promotions each report proposes."""
        snap = self.current()
        ws, m = snap.ws, snap.m
        views = []
        for session in sorted(ws.sessions.values(), key=lambda s: -s.number):
            title = f"{session.id} — {m.regen.one_line(session.goal, 100) or '(no brief yet)'}"
            if session.report is None:
                title += " (no report yet)"
            proposals, seen = [], set()
            for line in session.report_sections.get("Proposed promotions", "").splitlines():
                for card_id in m.regen.CARD_ID_RE.findall(line):
                    card = ws.cards.get(card_id)
                    if card is None or card.kind != "claim" or card_id in seen:
                        continue
                    seen.add(card_id)
                    proposals.append({"card": card_id, "reason": line.strip().lstrip("-* ").strip(),
                                      "status": ws.status(card_id), "statement": m.regen.one_line(card.statement, 200)})
            views.append({"id": session.id, "title": title, "markdown": self._session_markdown(session, m),
                          "proposals": proposals})
        return views

    def _session_markdown(self, session, m) -> str:
        brief = session.brief or {}
        out = []
        if brief:
            out.append(f"**Goal:** {session.goal or '(none given)'}")
            details = []
            if brief.get("budget"):
                details.append(f"budget of {brief['budget']} dispatches")
            if brief.get("starts_from"):
                details.append("starts from " + ", ".join(m.cards.id_list(brief["starts_from"])))
            if details:
                out.append("Brief: " + "; ".join(details) + ".")
        else:
            out.append("*No brief.*")
        if session.report is None:
            out.append("*No report yet: the session is still running, or was abandoned.*")
            return "\n\n".join(out)
        report = session.report
        stopped = f"**Stopped:** {report.get('stop_reason', '?')}"
        if report.get("dispatches"):
            stopped += f", after {report['dispatches']} dispatches"
        out.append(stopped + ".")
        for heading, text in session.report_sections.items():
            out.append(f"#### {heading}\n\n{text or '(none)'}")
        return "\n\n".join(out)

    # --- Questions ---

    def questions_markdown(self) -> str:
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        open_questions = [c for c in ws.sorted_cards("question") if ws.status(c.id) == "open"]
        if not open_questions:
            return "*No open question.*"
        proposals = regen.proposed_promotions(ws)
        return "\n".join(regen.card_line(ws, c, proposals) for c in open_questions)

    # --- Edit ---

    def lead_file(self, path: str) -> str:
        if path not in LEAD_FILES:
            raise SpaceError(f"{path} is not one of the lead's files ({', '.join(LEAD_FILES)}).")
        return self.read(path)

    # ----- writes -----

    def _require(self, user: str | None, action: str) -> None:
        if not user:
            raise SpaceError(f"Sign in with your Hugging Face account to {action}.")

    def _check_new_file(self, snap: Snapshot, rel: str, content: str) -> list[str]:
        """Errors that the workspace's own check reports for the file `rel` once it is added."""
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "workspace"
            shutil.copytree(snap.root, copy, ignore=shutil.ignore_patterns(
                ".git", ".physics-intern", "sources", ".cache", "__pycache__"))
            (copy / rel).parent.mkdir(parents=True, exist_ok=True)
            (copy / rel).write_text(content, encoding="utf-8")
            report = snap.m.check.run_checks(snap.m.cards.Workspace(copy))
        return [p.message for p in report.errors if p.path == rel]

    def _commit(self, files: dict[str, str], message: str, parent: str | None = None) -> None:
        try:
            self.store.commit(files, message, parent)
        except SpaceError:
            raise
        except Exception as exc:
            raise SpaceError(f"The Hub refused the commit ({type(exc).__name__}: {exc}).") from exc
        self.refresh()

    def _write_record(self, snap: Snapshot, rel: str, content: str, message: str) -> None:
        """Check a new file with the workspace's own checks, then commit it and refresh."""
        if (snap.root / rel).exists():
            raise SpaceError(f"{rel} already exists; wait a second and try again.")
        errors = self._check_new_file(snap, rel, content)
        if errors:
            raise SpaceError("The workspace's checks refused it: " + "; ".join(errors) + ".")
        self._commit({rel: content}, message)

    def react(self, user: str | None, target: str, value: str, comment: str = "") -> str:
        """Record a reaction on a card or a paper. One counts per person: the latest."""
        self._require(user, "react")
        with self._lock:
            snap = self._fresh()
            ws, cards = snap.ws, snap.m.cards
            if target in ws.papers:
                allowed = cards.PAPER_REACTIONS
            elif target in ws.cards:
                allowed = cards.CLAIM_REACTIONS
            else:
                raise SpaceError(f"There is no card or paper card {target!r}.")
            if value not in allowed:
                raise SpaceError(f"A reaction on {target} is one of: {', '.join(allowed)}.")
            now = now_utc()
            rel = f"feedback/reaction-{target}-{user}-{cards.utc_stamp(now)}.md"
            meta = {"kind": "reaction", "target": target, "value": value, "by": {"kind": "human", "user": user},
                    "date": iso(now)}
            comment = " ".join((comment or "").split())
            self._write_record(snap, rel, cards.dump_front_matter(meta, f"{comment}\n" if comment else ""),
                               f"Reaction {value} on {target} ({user}, from the Space)")
        return f"Recorded your reaction **{value}** on {target}."

    def write_card(self, user: str | None, kind: str, statement: str, body: str = "", depends_on=(),
                   answers=(), supersedes=()) -> str:
        """Write a question card or a claim card under the user's name. Nobody types YAML."""
        self._require(user, "write a card")
        if kind not in ("question", "claim"):
            raise SpaceError("A card written in the Space is a question or a claim.")
        statement = " ".join((statement or "").split())
        if not statement:
            raise SpaceError("Write a statement: one sentence that says what the card claims or asks.")
        with self._lock:
            snap = self._fresh()
            cards = snap.m.cards
            now = now_utc()
            card_id = f"{cards.CARD_KINDS[kind]}-{user}-{cards.utc_stamp(now)}"
            meta = {"id": card_id, "kind": kind, "statement": statement, "depends_on": _ids(depends_on),
                    "produced_by": {"kind": "human", "user": user}, "session": None,
                    "supersedes": _ids(supersedes) if kind == "claim" else [], "refutes": [],
                    "answers": _ids(answers) if kind == "claim" else []}
            body = (body or "").strip()
            self._write_record(snap, f"claims/{card_id}.md", cards.dump_front_matter(meta, f"{body}\n" if body else ""),
                               f"{kind.capitalize()} card {card_id} ({user}, from the Space)")
        what = "The agents will see it among the open questions." if kind == "question" else (
            "It starts with no evidence; anyone can verify it, and a lead can promote it once it has some.")
        return f"Wrote **{card_id}**. {what}"

    def verify(self, user: str | None, card_id: str, verdict: str, body: str, target: str | None = None) -> str:
        """Record a human verification of a claim. It counts as evidence, unlike a reaction."""
        self._require(user, "verify a claim")
        body = (body or "").strip()
        if not body:
            raise SpaceError("Say what you checked: which steps, limits or numbers, and how.")
        with self._lock:
            snap = self._fresh()
            ws, cards = snap.ws, snap.m.cards
            card = ws.cards.get(card_id)
            if card is None or card.kind != "claim":
                raise SpaceError(f"{card_id} is not a claim card; only claims are verified.")
            if verdict not in cards.VERDICTS:
                raise SpaceError(f"The verdict is one of: {', '.join(cards.VERDICTS)}.")
            target = target or None
            if target and target not in [ev.artefact for ev in ws.evidence(card_id)]:
                raise SpaceError(f"{target} is not among the evidence of {card_id}.")
            now = now_utc()
            stamp = cards.utc_stamp(now)
            meta = {"id": f"R-{user}-{stamp}", "kind": "review", "target": target, "supports": [card_id],
                    "claim": card.statement, "verdict": verdict, "by": {"kind": "human", "user": user},
                    "date": iso(now)}
            self._write_record(snap, f"feedback/review-{card_id}-{user}-{stamp}.md",
                               cards.dump_front_matter(meta, body + "\n"),
                               f"Verification of {card_id}: {verdict} ({user}, from the Space)")
        return f"Recorded your verification of {card_id} (**{verdict}**). It now counts in the card's evidence."

    def promote(self, user: str | None, card_id: str, reason: str = "") -> str:
        """Record a lead's promotion of a claim to established, if the workspace's rule allows it."""
        self._require(user, "promote a claim")
        by = {"kind": "human", "user": user}
        with self._lock:
            for attempt in (1, 2):
                snap = self._fresh()
                ws, m = snap.ws, snap.m
                reasons = list(m.cards.promotion_problems(ws, card_id, by))
                if ws.mode != "shared" and user not in ws.leads:  # promotion_problems checks leads in shared mode only
                    reasons.insert(0, f"{user} is not in [people] leads of project.toml")
                if reasons:
                    raise SpaceError(f"Promotion of {card_id} refused: " + "; ".join(reasons) + ".")
                rel, content = m.promote.promotion_record(card_id, by, None, reason or "")
                try:
                    # Committed against the commit it was checked on; if main moved, check again.
                    self.store.commit({rel: content}, f"Promote {card_id} ({user})", parent=snap.revision)
                    break
                except SpaceError:
                    raise
                except Exception as exc:
                    if attempt == 2:
                        raise SpaceError(f"The Hub refused the promotion commit ({type(exc).__name__}: {exc}).") from exc
            self.refresh()
        return f"Promoted **{card_id}** to established ({rel})."

    def save_lead_file(self, user: str | None, path: str, content: str, base: str | None = None) -> str:
        """Save a lead's file: a lead commits to main; anyone else opens a pull request.

        `base` is the text the editor started from; if main changed since, the
        save is refused rather than overwriting someone else's edit.
        """
        self._require(user, "save")
        if path not in LEAD_FILES:
            raise SpaceError(f"{path} is not one of the lead's files ({', '.join(LEAD_FILES)}).")
        content = (content or "").replace("\r\n", "\n")
        if content and not content.endswith("\n"):
            content += "\n"
        with self._lock:
            snap = self._fresh()
            current = self.read(path)
            if base is not None and current.strip() != base.replace("\r\n", "\n").strip():
                raise SpaceError(f"{path} changed on main since you opened it. Copy your text, press Reload, "
                                 "and apply your change again.")
            if content.strip() == current.strip():
                raise SpaceError("Nothing to save: the text is the same as on main.")
            if user in snap.ws.leads:
                self._commit({path: content}, f"Edit {path} ({user}, from the Space)")
                return f"Saved {path} on main."
            try:
                number, url = self.store.propose(path, content, f"Proposal: {path} (by {user})",
                                                 f"Proposed by {user} from the Space. A lead merges, edits or "
                                                 "closes this pull request.")
            except SpaceError:
                raise
            except Exception as exc:
                raise SpaceError(f"The Hub refused to open the pull request ({type(exc).__name__}: {exc}).") from exc
            self.refresh()
        return (f"You are not a lead, so your change is a proposal: pull request [#{number}]({url}). "
                "A lead merges, edits or closes it.")

    def merge_proposal(self, user: str | None, number) -> str:
        """Merge an open proposal pull request (leads only)."""
        self._require(user, "merge a proposal")
        with self._lock:
            snap = self._fresh()
            if user not in snap.ws.leads:
                raise SpaceError(f"Only a lead can merge a proposal, and {user} is not in [people] leads of project.toml.")
            try:
                number = int(number)
            except (TypeError, ValueError):
                raise SpaceError("Choose the proposal to merge.") from None
            self.pull_requests = self.store.pull_requests()
            if number not in {pr["num"] for pr in self.proposal_prs()}:
                raise SpaceError(f"#{number} is not an open proposal (session pull requests are merged by their session).")
            try:
                self.store.merge(number, f"Merged from the Space by {user}.")
            except SpaceError:
                raise
            except Exception as exc:
                raise SpaceError(f"The Hub refused to merge #{number} ({type(exc).__name__}: {exc}).") from exc
            self.refresh()
        return f"Merged pull request #{number}."

    def log_chat(self, record: dict) -> None:
        """Debug mode only: keep one chat exchange outside the workspace."""
        if self.chat_debug and self.store is not None:
            self.store.log_chat(record, self.snap.ws.hub if self.snap else {})


# ----- formatting helpers -----


def _has_text(markdown: str) -> bool:
    """Whether a lead's file says anything beyond its heading and the template's comment."""
    text = re.sub(r"<!--.*?-->", "", markdown, flags=re.S)
    return any(line.strip() and not line.startswith("#") for line in text.splitlines())


def _ids(values) -> list[str]:
    return [str(v).strip() for v in (values or []) if v and str(v).strip()]


def origin_text(card) -> str:
    produced = card.produced_by
    if produced.get("kind") == "human":
        origin = f"written by {produced.get('user', '?')}"
    elif produced:
        origin = f"agent ({produced.get('model', '?')}), operator {produced.get('operator', '?')}"
    else:
        origin = "author not recorded"
    return origin + (f", session {card.session}" if card.session else "")


def _reaction_line(reaction) -> str:
    comment = f': "{reaction.comment}"' if reaction.comment else ""
    return f"- **{reaction.value}** — {reaction.user}{comment} ({reaction.date[:10]})"


def _pr_line(pr: dict) -> str:
    return f"- #{pr['num']} {pr['title']} — {pr['status']}, opened by {pr['author']} on {pr['date']} — [open on the Hub]({pr['url']})"
