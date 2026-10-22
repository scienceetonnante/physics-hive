"""Workspace access for the PhysicsIntern Space, without any user interface.

The Space shows a workspace to people who only use a browser, and writes what
they do there: question and claim cards, promotions, edits of the lead's files
and decisions on proposals. Reactions and verifications are written here too,
for the pages that may show them again. Everything except the page layout
lives in this module, so that it can be tested on a folder.

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
from huggingface_hub import constants as hf_constants
from huggingface_hub.utils import disable_progress_bars

disable_progress_bars()

DATASET = "dataset"
HUB = hf_constants.ENDPOINT
# Fallback method scripts for a workspace without a method copy (the test toys):
# this repository's scripts/, or those of the method copy this app sits in.
REPO_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
# Modules of the method copy that import each other by plain name.
METHOD_MODULES = ("cards", "common", "regen", "check", "promote")
MAX_AGE = 120  # seconds after which a page load refreshes the workspace
MAX_CHARS = 60_000  # longest file shown in full in the page

LEAD_FILES = ("problem.md", "plan.md", "conventions.md", "literature/seeds.md")
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
    """A session's pull request is titled `[S12] …`, 12 being its own number; just after the claim, `[draft] session by …`.

    Other pull requests may start with a session too: the plan proposal drafted in S1 is `[S1] Plan proposal: …`.
    """
    return pr["title"].startswith((f"[S{pr['num']}]", "[draft] session"))


def split_text(text: str) -> tuple[str, str]:
    """A card's statement (the first paragraph) and body (the rest), from what a person typed in one box."""
    first, _, rest = (text or "").replace("\r\n", "\n").strip().partition("\n\n")
    return " ".join(first.split()), rest.strip()


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

    close = merge

    def proposal(self, number: int) -> dict:
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

    def close(self, number: int, comment: str) -> None:
        self.api.change_discussion_status(self.repo_id, number, "closed", comment=comment, repo_type=DATASET)

    def proposal(self, number: int) -> dict:
        """The description of a pull request, and the files it changes as they are in it (None if deleted or binary).

        The Hub does not always return a pull request's diff, so the changed files are found by comparing
        the files of the pull request with those of the commit of main it starts from.
        """
        details = self.api.get_discussion_details(self.repo_id, number, repo_type=DATASET)
        comments = [e for e in details.events if e.type == "comment"]
        head = f"refs/pr/{number}"
        on_main = {c.commit_id for c in self.api.list_repo_commits(self.repo_id, repo_type=DATASET)}
        base = next(c.commit_id for c in self.api.list_repo_commits(self.repo_id, repo_type=DATASET, revision=head)
                    if c.commit_id in on_main)

        def blobs(revision: str) -> dict[str, str]:
            tree = self.api.list_repo_tree(self.repo_id, repo_type=DATASET, revision=revision, recursive=True)
            return {f.path: f.blob_id for f in tree if getattr(f, "blob_id", None)}

        before, after = blobs(base), blobs(head)
        files = []
        for rel in sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p)):
            try:
                local = self.api.hf_hub_download(self.repo_id, rel, repo_type=DATASET, revision=head)
                text = Path(local).read_text(encoding="utf-8")
            except Exception:
                text = None
            files.append({"path": rel, "text": text})
        return {"description": (comments[0].content or "").strip() if comments else "", "files": files}

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

    def project_name(self) -> str:
        """The project's short name: the workspace repository's name, or the folder's."""
        label = self.store.label if self.store is not None else "PhysicsIntern"
        return label.rstrip("/").rsplit("/", 1)[-1]

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

    def hub_url(self, kind: str, *parts: str) -> str | None:
        """A page on the Hub for one of the project's repositories (None in local mode)."""
        repo = self.current().ws.hub.get(kind)
        if self.local or not repo:
            return None
        return "/".join([f"{HUB}/datasets/{repo}", *parts])

    # --- the Status page ---

    def lead_text(self, path: str) -> str | None:
        """A lead's file, with its headings under the page's own, or None while it holds only its template."""
        text = self.read(path)
        return demote_headings(text.strip()) if _has_text(text) else None

    def counts(self) -> dict[str, int]:
        ws = self.current().ws
        claims = [ws.status(c.id) for c in ws.sorted_cards("claim")]
        return {"established claims": claims.count("established"), "working claims": claims.count("working"),
                "open questions": sum(ws.status(c.id) == "open" for c in ws.sorted_cards("question")),
                "cards to re-check": sum(1 for c in ws.cards if self._recheck(c)),
                "dead ends": len(ws.sorted_cards("dead-end")), "papers": len(ws.papers)}

    def sessions(self) -> list:
        """The sessions with a brief or a report, newest first."""
        return sorted(self.current().ws.sessions.values(), key=lambda s: -s.number)

    def attention(self) -> dict:
        """What waits for a person: open proposals, the decisions the latest report asks for, proposed promotions."""
        snap = self.current()
        ws = snap.ws
        reported = [s for s in self.sessions() if s.report is not None]
        decisions = reported[0].report_sections.get("Needs a human decision", "") if reported else ""
        proposed = snap.m.regen.proposed_promotions(ws)
        return {"proposals": self.proposal_prs(),
                "decisions": (reported[0].id, decisions) if _says(decisions) else None,
                "promotions": [(self.row(card_id), proposed[card_id])
                               for card_id in sorted(proposed, key=snap.m.cards.natural_key)
                               if ws.status(card_id) == "working"]}

    # --- cards ---

    def _recheck(self, card_id: str) -> list[str]:
        """What a card needs a re-check for; nothing once the card itself is refuted or revised."""
        ws = self.current().ws
        return [] if ws.status(card_id) in ("refuted", "revised") else ws.needs_recheck(card_id)

    def row(self, card_id: str) -> dict:
        """What a list shows of a card."""
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        card = ws.cards.get(card_id)
        if card is None:
            return {"id": card_id, "kind": None, "status": "missing", "status_text": "missing", "recheck": [],
                    "statement": "", "evidence": None, "author": None}
        human = card.produced_by.get("kind") == "human"
        return {"id": card.id, "kind": card.kind, "status": ws.status(card.id),
                "status_text": regen.status_text(ws, card.id),
                "recheck": [(c, ws.status(c)) for c in self._recheck(card.id)], "statement": card.statement,
                "evidence": regen.evidence_parts(ws, card.id) if card.kind == "claim" else None,
                "author": card.produced_by.get("user") if human else None}

    def results(self) -> dict:
        """The Results page: the cards in the groups it shows, the papers and the survey summaries."""
        snap = self.current()
        ws = snap.ws

        def rows(kind: str, *statuses: str) -> list[dict]:
            return [self.row(c.id) for c in ws.sorted_cards(kind) if not statuses or ws.status(c.id) in statuses]

        surveys = sorted((snap.root / "literature").glob("survey-*.md"), key=lambda p: snap.m.cards.natural_key(p.name))
        return {"claims": rows("claim", "established") + rows("claim", "working"),
                "past_claims": rows("claim", "revised", "refuted"),
                "questions": rows("question", "open"), "answered": rows("question", "answered"),
                "dead_ends": rows("dead-end"),
                "papers": [ws.papers[p] for p in sorted(ws.papers, key=snap.m.cards.natural_key)],
                "surveys": [p.relative_to(snap.root).as_posix() for p in surveys]}

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

    def card(self, card_id: str) -> dict:
        """Everything the card page shows."""
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        card = ws.cards.get(card_id)
        if card is None:
            raise SpaceError(f"There is no card {card_id} in this workspace.")
        promotions = [{"by": p.by.get("user") or f"an agent ({p.by.get('model', '?')})", "date": p.date[:10],
                       "counted": ws.promotion_is_valid(p), "reason": p.reason} for p in ws.promotions_of(card_id)]
        working_claim = card.kind == "claim" and ws.status(card_id) == "working"
        return {"card": card, "row": self.row(card_id), "origin": origin_text(card),
                "trace": self.hub_url("traces", "tree/main", card.session) if card.session else None,
                "related": [(label, [self.row(i) for i in ids]) for label, ids in self.related(card_id)],
                "evidence": self.evidence_items(card_id), "promotions": promotions,
                "proposed": regen.proposed_promotions(ws).get(card_id, []) if working_claim else []}

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

    # --- papers, sessions, files ---

    def paper(self, paper_id: str) -> dict:
        ws = self.current().ws
        paper = ws.papers.get(paper_id)
        if paper is None:
            raise SpaceError(f"There is no paper card {paper_id}.")
        authors = paper.meta.get("authors") or []
        return {"paper": paper, "authors": ", ".join(map(str, authors)) if isinstance(authors, list) else str(authors),
                "arxiv": paper.meta.get("arxiv"), "doi": paper.meta.get("doi"), "body": self.body(paper.path)}

    def session(self, session_id: str) -> dict:
        ws = self.current().ws
        session = ws.sessions.get(session_id)
        if session is None:
            raise SpaceError(f"There is no session {session_id} in this workspace.")
        sections = {h: t for h, t in session.report_sections.items() if _says(t)}
        return {"session": session, "brief": self.body(f"{session.path}/brief.md"), "sections": sections,
                "log": f"{session.path}/log.md" if session.has_log else None,
                "pr": self.hub_url("workspace", "discussions", str(session.number)),
                "trace": self.hub_url("traces", "tree/main", session.id)}

    def file_path(self, rel: str) -> Path | None:
        """A file of the workspace by its path in it, or None if there is none."""
        parts = Path(rel or "").parts
        if not parts or rel.startswith("/") or ".." in parts:
            return None
        path = self.current().root / rel
        return path if path.is_file() else None

    def file(self, rel: str) -> dict:
        """A workspace file for the file page: its header and body for Markdown, its text otherwise."""
        if self.file_path(rel) is None:
            raise SpaceError(f"There is no file {rel} in the workspace.")
        text = clip(self.read(rel))
        if not rel.endswith(".md"):
            return {"path": rel, "header": None, "body": None, "text": text}
        header, body = None, text
        end = text.find("\n---\n", 3) if text.startswith("---\n") else -1
        if end != -1:
            header, body = text[4:end], text[end + 5:]
        return {"path": rel, "header": header, "body": body, "text": None}

    # --- pull requests ---

    def open_sessions(self) -> list[dict]:
        return [pr for pr in self.pull_requests if is_session_pr(pr) and pr["status"] in ("draft", "open")]

    def proposal_prs(self) -> list[dict]:
        return [pr for pr in self.pull_requests if not is_session_pr(pr) and pr["status"] in ("draft", "open")]

    def proposal(self, number) -> dict:
        """A proposal pull request, with its description and the files it changes as they are in it."""
        try:
            number = int(number)
        except (TypeError, ValueError):
            raise SpaceError(f"{number!r} is not a pull request number.") from None
        self.current()
        pr = next((p for p in self.pull_requests if p["num"] == number and not is_session_pr(p)), None)
        if pr is None:
            raise SpaceError(f"#{number} is not a proposal of this workspace (session pull requests have their "
                             "session's page).")
        try:
            details = self.store.proposal(number)
        except SpaceError:
            raise
        except Exception as exc:
            raise SpaceError(f"The Hub did not return pull request #{number} ({type(exc).__name__}: {exc}).") from exc
        return {**pr, **details}

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
        if kind == "question":
            what = "The next session will see it among the open questions."
        elif answers:
            what = f"It answers {', '.join(_ids(answers))}."
        else:
            what = "It starts with no evidence."
        return f"Wrote **{card_id}**. {what}"

    def ask(self, user: str | None, text: str, about: str | None = None) -> str:
        """Write to the agents: a question card under the user's name, linked to the card or paper at hand."""
        statement, body = split_text(text)
        if not statement:
            raise SpaceError("Write something first.")
        ws = self.current().ws
        if about and about in ws.papers:
            body = f"About {about}.\n\n{body}".strip()
        depends_on = [about] if about and about in ws.cards else []
        return self.write_card(user, "question", statement, body, depends_on=depends_on)

    def answer(self, user: str | None, question_id: str, text: str) -> str:
        """Answer an open question: a claim card under the user's name that names it in `answers`."""
        statement, body = split_text(text)
        if not statement:
            raise SpaceError("Write the answer first.")
        return self.write_card(user, "claim", statement, body, answers=[question_id])

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
        return self._settle(user, number, "merge")

    def close_proposal(self, user: str | None, number) -> str:
        """Close an open proposal pull request without merging it (leads only)."""
        return self._settle(user, number, "close")

    def _settle(self, user: str | None, number, action: str) -> str:
        self._require(user, f"{action} a proposal")
        with self._lock:
            snap = self._fresh()
            if user not in snap.ws.leads:
                raise SpaceError(f"Only a lead can {action} a proposal, and {user} is not in [people] leads of project.toml.")
            try:
                number = int(number)
            except (TypeError, ValueError):
                raise SpaceError(f"Choose the proposal to {action}.") from None
            self.pull_requests = self.store.pull_requests()
            if number not in {pr["num"] for pr in self.proposal_prs()}:
                raise SpaceError(f"#{number} is not an open proposal (session pull requests are merged by their session).")
            done = {"merge": "Merged", "close": "Closed"}[action]
            try:
                getattr(self.store, action)(number, f"{done} from the Space by {user}.")
            except SpaceError:
                raise
            except Exception as exc:
                raise SpaceError(f"The Hub refused to {action} #{number} ({type(exc).__name__}: {exc}).") from exc
            self.refresh()
        return f"{done} pull request #{number}."

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


def _says(text: str) -> bool:
    """Whether a report section says something: not empty, and not `(none)`."""
    return (text or "").strip().lower().strip("-*() .") not in ("none", "")
