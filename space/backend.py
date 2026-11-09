"""Workspace access for the PhysicsHive Space, without any user interface.

The Space shows the human view of a workspace (design, section 14): the
debriefs, project.md and conventions.md, the draft, the session notes and the
literature. It writes only files: the researcher's answers, ticks and notes in
a debrief, their edits of project.md, conventions.md, the draft and the seeds,
and their ratings of papers. It applies nothing: ticked lines are applied by
the next session.

Two ways to reach a workspace:

- In the deployed Space, the workspace is a private dataset repository on the
  Hub, named by the Space variable `PHYSICS_HIVE_WORKSPACE` (org/name). The
  Space keeps a git clone of it (with the Space secret `HF_TOKEN`), fetched on
  demand and after each write, and shows each commit of main from its own git
  worktree, so that it can read the history as `session.py` does. Every write
  is a commit made through the Hub API with that token, on the commit the page
  was built from, and names the signed-in user in its message.
- For development, tests and local mode, `PHYSICS_HIVE_LOCAL=/path/to/workspace`
  reads a folder directly and writes files into it without committing; the next
  `session.py start` commits them as the researcher's. The signed-in user is
  then `PHYSICS_HIVE_LOCAL_USER`.

What the files mean (status, evidence, the draft's results, debriefs and which
session read them, the checks, references.bib, the PDF) comes from the
workspace's own copy of the method scripts, `.physics-hive/scripts/`,
imported again at every refresh.
"""

from __future__ import annotations

import base64
import datetime as dt
import functools
import hashlib
import importlib
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from huggingface_hub import CommitOperationAdd, HfApi
from huggingface_hub import constants as hf_constants
from huggingface_hub.utils import disable_progress_bars

import latex

disable_progress_bars()
log = logging.getLogger("physics_hive")  # how long loads and writes take (app.py prints it)

DATASET = "dataset"
HUB = hf_constants.ENDPOINT
# Fallback method scripts for a workspace without a method copy (the test toys):
# this repository's scripts/, or those of the method copy this app sits in.
REPO_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
# Modules of the method copy, which import each other by plain name.
METHOD_MODULES = ("cards", "common", "human", "regen", "check", "pdf")
MAX_AGE = 120  # seconds after which a page load refreshes the workspace
MAX_CHARS = 60_000  # longest file shown in full in the page
KEEP_WORKTREES = 3  # commits of main kept checked out in the Hub clone

DEBRIEF_RE = re.compile(r"^sessions/S\d+/debrief\.md$")
EDITABLE = ("project.md", "conventions.md", "draft.tex", "literature/seeds.md")
CODE_LANGUAGES = {".tex": "latex", ".py": "python", ".json": "json", ".md": "markdown"}


class SpaceError(Exception):
    """A problem to show to the person using the Space, in plain words."""


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def clip(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[… cut here: the file has {len(text)} characters, of which the first {limit} are shown]"


def normalise(text: str) -> str:
    text = (text or "").replace("\r\n", "\n")
    return text if not text or text.endswith("\n") else text + "\n"


def first_sentence(text: str, limit: int = 220) -> str:
    plain = " ".join(re.sub(r"[*_`#>]", "", text or "").split())
    m = re.match(r"(.+?[.!?])(\s|$)", plain)
    sentence = m.group(1) if m else plain
    return sentence if len(sentence) <= limit else sentence[: limit - 1] + "…"


# ----- what the pages say about claims and debriefs, computed from the record -----

ARTEFACT_WORDS = {"derivation": ("a derivation", "derivations"), "computation": ("a computation", "computations")}
NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
# Tick lines are grouped by the file they change: the first of these patterns found in the line; "Other" if none.
TICK_GROUPS = ((re.compile(r"draft\.tex|\bthe draft\b", re.I), "Draft (draft.tex)"),
               (re.compile(r"project\.md|\bnext steps?\b|\bthe approach\b", re.I), "Research plan (project.md)"),
               (re.compile(r"conventions\.md|\bthe conventions\b", re.I), "Conventions (conventions.md)"))
FILE_NAMES = {"project.md": "Research plan", "conventions.md": "Notation and conventions", "draft.tex": "Draft"}
# A file line of "Changed by this session", as session.py end writes it (human.changed_by_session).
CHANGED_LINE_RE = re.compile(r"^- `([^`]+)`(?: \(\+(\d+) −(\d+) lines?\))?: (.*)$")


def joined(parts: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def counted(n: int, one: str, many: str) -> str:
    return one if n == 1 else f"{NUMBER_WORDS.get(n, str(n))} {many}"


def review_outcome(reviews) -> tuple[str, str]:
    """What the reviews of one artefact say about a claim, in words, with a tone: ok, open or bad."""
    if not reviews:
        return "not reviewed yet", "open"
    verdicts = {r.verdict for r in reviews}
    if "refuted" in verdicts:
        return ("with reviews that disagree", "bad") if "confirmed" in verdicts else ("refuted by a review", "bad")
    confirmed = [r for r in reviews if r.verdict == "confirmed"]
    if not confirmed:
        return "with an inconclusive review", "open"
    people = [str(r.by.get("user") or "a person") for r in confirmed if r.by_human]
    agents = len(confirmed) - len(people)
    parts = ([f"confirmed by {counted(agents, 'a blind review (agent)', 'blind reviews (agent)')}"] if agents else []) + \
            ([f"checked by {joined(people)}"] if people else [])
    return " and ".join(parts), "ok"


def evidence_text(ws, card_id: str) -> tuple[str, str]:
    """One sentence, without its full stop, on what supports a claim ('A derivation and a computation, each
    confirmed by a blind review (agent)'), and its tone: ok (confirmed), open (not confirmed yet) or bad
    (a review refutes it)."""
    items = ws.evidence(card_id)
    if not items:
        return "No evidence yet: no derivation or computation supports it", "open"
    groups: dict[str, dict[str, int]] = {}
    tones = []
    order = list(ARTEFACT_WORDS)  # derivations first
    items = sorted(items, key=lambda i: order.index(k) if (k := ws.artefacts[i.artefact].kind) in order else len(order))
    for item in items:
        outcome, tone = review_outcome(item.reviews)
        kind = ws.artefacts[item.artefact].kind
        groups.setdefault(outcome, {}).setdefault(kind, 0)
        groups[outcome][kind] += 1
        tones.append(tone)
    phrases = []
    for outcome, kinds in groups.items():
        things = joined([counted(n, *ARTEFACT_WORDS.get(k, (f"a {k}", f"{k}s"))) for k, n in kinds.items()])
        each = "each " if sum(kinds.values()) > 1 and outcome.startswith(("confirmed", "checked", "refuted")) else ""
        phrases.append(f"{things}, {each}{outcome}")
    text = "; ".join(phrases)
    tone = "bad" if "bad" in tones else "ok" if "ok" in tones else "open"
    return text[0].upper() + text[1:], tone


def place_text(ws, card_id: str) -> str:
    return {"result": "In the draft, as a result",
            "conjecture": "In the draft, as a conjecture"}.get(ws.in_draft(card_id), "Not in the draft")


def warning_text(ws, card_id: str) -> str | None:
    """Why a claim is in doubt: refuted, revised, or depending on a claim that is."""
    status = ws.status(card_id)
    if status == "refuted":
        return f"Refuted by {', '.join(ws.refuters(card_id))}."
    if status == "revised":
        return f"Revised by {', '.join(ws.revisers(card_id))}: the newer claim replaces it."
    causes = ws.needs_recheck(card_id)
    if causes:
        return "Needs a re-check: it depends on " + ", ".join(f"{c} ({ws.status(c)})" for c in causes) + "."
    return None


def tick_groups(ticks) -> list[tuple[str, list]]:
    """The tick lines grouped by the file they change (the first one they name), each with its index."""
    groups: dict[str, list] = {label: [] for _, label in TICK_GROUPS}
    groups["Other"] = []
    for index, tick in enumerate(ticks):
        found = sorted((m.start(), label) for pattern, label in TICK_GROUPS if (m := pattern.search(tick.text)))
        groups[found[0][1] if found else "Other"].append((index, tick))
    return [(label, items) for label, items in groups.items() if items]


def line_counts(added: int, removed: int) -> str:
    parts = ([f"{added} line{'s' if added != 1 else ''} added"] if added else []) + \
            ([f"{removed} line{'s' if removed != 1 else ''} removed"] if removed else [])
    return " and ".join(parts) or "changed"


def parse_changed(text: str) -> dict | None:
    """'Changed by this session' as written by session.py end: the changed files (name, path, line counts,
    the debriefs whose ticks it applied, the diff) and a sentence for the unchanged ones. None if the text
    does not have that shape, so that the page shows it as it is."""
    files, diff, in_diff = [], [], False
    for line in text.splitlines():
        if in_diff:
            if line.strip().startswith("```"):
                in_diff = False
                files[-1]["diff"] += diff
                diff = []
            else:
                diff.append(("add" if line.startswith("+") else "del" if line.startswith("-") else "", line))
            continue
        if line.strip().startswith("```") and files:
            in_diff = True
            continue
        m = CHANGED_LINE_RE.match(line.strip())
        if m:
            path, added, removed, rest = m.groups()
            files.append({"path": path, "name": FILE_NAMES.get(path, path), "changed": added is not None,
                          "counts": line_counts(int(added or 0), int(removed or 0)),
                          "ticked": re.findall(r"as you ticked in (S\d+)", rest), "diff": []})
    if not files:
        return None
    same = [f["name"] for f in files if not f["changed"]]
    unchanged = (joined([same[0]] + [n.lower() for n in same[1:]]) + ": unchanged.") if same else ""
    return {"files": [f for f in files if f["changed"]], "unchanged": unchanged}


def answered(debrief) -> bool:
    """The researcher has written an answer or a note, or ticked a line, in this debrief."""
    return bool(debrief.note.strip() or any(q.answer.strip() for q in debrief.questions)
                or any(t.checked for t in debrief.ticks))


def long_date(stamp) -> str:
    """A time stamp such as '2026-11-06T15:56:48Z' as '6 November 2026' ('' if there is none)."""
    try:
        day = dt.date.fromisoformat(str(stamp or "")[:10])
    except ValueError:
        return ""
    return f"{day.day} {day:%B %Y}"


def is_session_pr(pr: dict) -> bool:
    """A session's pull request is titled `[S12] …`, 12 being its own number; just after the claim, `[draft] session by …`."""
    return pr["title"].startswith((f"[S{pr['num']}]", "[draft] session"))


# ----- the method copy -----


def method_scripts(root: Path) -> Path:
    """The scripts of the workspace's method copy, or the fallback ones for a toy workspace."""
    for folder in (root / ".physics-hive" / "scripts", REPO_SCRIPTS):
        if (folder / "cards.py").is_file() and (folder / "human.py").is_file():
            return folder
    raise SpaceError("The workspace has no method copy (.physics-hive/scripts/) that this Space can read. "
                     "It may use an earlier format of the method.")


def load_method(scripts: Path) -> SimpleNamespace:
    """Import the method's modules from `scripts`, leaving other imports untouched.

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
        return SimpleNamespace(**{name: importlib.import_module(name) for name in METHOD_MODULES})
    finally:
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_bytecode
        for name in METHOD_MODULES:
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


# ----- where the workspace lives -----


def run_git(cwd: Path, *args: str, env: dict | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {}), "GIT_TERMINAL_PROMPT": "0"})
    if proc.returncode != 0:
        raise SpaceError(f"git {' '.join(args[:2])} failed: {(proc.stderr or proc.stdout).strip()[:500]}")
    return proc.stdout.strip()


class LocalStore:
    """A workspace folder on this machine. Writes are plain files, committed later by session.py start."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.label = str(self.root)

    def snapshot(self) -> tuple[Path, str | None]:
        if not (self.root / "project.toml").is_file():
            raise SpaceError(f"{self.root} is not a PhysicsHive workspace (it has no project.toml).")
        return self.root, None

    def commit(self, files: dict[str, str], message: str, parent: str | None = None) -> None:
        """Write the files; there is no commit to point to."""
        for rel, content in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def pull_requests(self) -> list[dict]:
        return []


class HubStore:
    """The workspace as a private dataset repository on the Hub: read from a git clone, written through the API."""

    def __init__(self, repo_id: str, token: str, api: HfApi | None = None, remote: str | None = None,
                 cache: Path | None = None):
        self.repo_id, self.token = repo_id, token
        self.api = api or HfApi(token=token)
        self.label = repo_id
        self.remote = remote or f"{HUB}/datasets/{repo_id}"
        self.cache = Path(cache or Path(tempfile.gettempdir()) / "physics-hive-space") / repo_id.replace("/", "--")
        self._env: dict | None = None

    def git_env(self) -> dict:
        """Git sends the token in a header for each command; it is never written to a config file."""
        if self._env is None:
            if not self.remote.startswith("http"):
                self._env = {}
            else:
                auth = base64.b64encode(f"hf:{self.token}".encode()).decode()
                self._env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"http.{HUB}/.extraHeader",
                             "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}"}
        return self._env

    def snapshot(self) -> tuple[Path, str]:
        """main as it is now, checked out in its own worktree (one folder per commit, the last few kept)."""
        try:
            clone = self.cache / "clone"
            if not (clone / "HEAD").is_file():
                self.cache.mkdir(parents=True, exist_ok=True)
                run_git(self.cache, "clone", "-q", "--bare", self.remote, str(clone), env=self.git_env())
            run_git(clone, "fetch", "-q", "--prune", "origin", "+refs/heads/main:refs/heads/main", env=self.git_env())
            sha = run_git(clone, "rev-parse", "main")
            tree = self.cache / sha[:12]
            if not (tree / ".git").exists():
                run_git(clone, "worktree", "prune")
                run_git(clone, "worktree", "add", "-q", "--detach", str(tree), sha)
            self._prune(clone, keep=tree)
        except SpaceError as exc:
            raise SpaceError(f"The Space could not read the workspace {self.repo_id} from the Hub ({exc}). Check "
                             "that the Space secret HF_TOKEN is a token that can read and write this repository.") from exc
        return tree, sha

    def _prune(self, clone: Path, keep: Path) -> None:
        trees = sorted((p for p in self.cache.iterdir() if p.is_dir() and p.name != "clone" and p != keep),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in trees[KEEP_WORKTREES - 1:]:
            subprocess.run(["git", "worktree", "remove", "--force", str(old)], cwd=clone, capture_output=True)
            shutil.rmtree(old, ignore_errors=True)

    def commit(self, files: dict[str, str], message: str, parent: str | None = None) -> str | None:
        """Commit the files to main; returns the address of the commit on the Hub."""
        operations = [CommitOperationAdd(path_in_repo=rel, path_or_fileobj=content.encode("utf-8"))
                      for rel, content in files.items()]
        info = self.api.create_commit(self.repo_id, operations, commit_message=message, repo_type=DATASET,
                                      parent_commit=parent)
        return getattr(info, "commit_url", None)

    def pull_requests(self) -> list[dict]:
        rows = []
        for d in self.api.get_repo_discussions(self.repo_id, repo_type=DATASET, discussion_type="pull_request"):
            rows.append({"num": d.num, "title": d.title, "status": d.status, "author": d.author,
                         "date": d.created_at.strftime("%Y-%m-%d") if d.created_at else "", "url": d.url})
        return sorted(rows, key=lambda r: -r["num"])


# ----- the backend -----


def timed(write):
    """Log how long a write took in all; its steps (git, reading, commit) are logged as they happen."""

    @functools.wraps(write)
    def run(*args, **kwargs):
        start = time.perf_counter()
        try:
            return write(*args, **kwargs)
        finally:
            log.info("%s took %.2f s in all", write.__name__, time.perf_counter() - start)

    return run


@dataclass
class Snapshot:
    """One loaded state of the workspace, with the method modules that interpret it."""

    root: Path
    revision: str | None  # commit of main (Hub), None for a local folder
    m: SimpleNamespace  # the method's modules, from the workspace's own copy
    ws: object  # cards.Workspace
    loaded_at: float


class Backend:
    """The data of the pages, and every write the Space makes."""

    def __init__(self, store: LocalStore | HubStore | None = None, *, local_user: str | None = None,
                 error: str | None = None):
        self.store = store
        self.local_user = local_user
        self.snap: Snapshot | None = None
        self.error = error  # why the workspace cannot be shown, if it cannot
        self.pull_requests: list[dict] = []
        self.notes: list[str] = []  # things that failed without blocking the pages
        self._lock = threading.RLock()
        self._renders: dict[str, latex.Rendered] = {}

    @classmethod
    def from_env(cls, env: dict | None = None) -> Backend:
        env = os.environ if env is None else env
        if env.get("PHYSICS_HIVE_LOCAL"):
            return cls(LocalStore(env["PHYSICS_HIVE_LOCAL"]), local_user=env.get("PHYSICS_HIVE_LOCAL_USER") or None)
        repo = env.get("PHYSICS_HIVE_WORKSPACE", "").strip()
        token = env.get("HF_TOKEN", "").strip()
        if not repo:
            return cls(error="This Space does not know which workspace to show: the Space variable "
                             "PHYSICS_HIVE_WORKSPACE (org/name) is not set.")
        if not token:
            return cls(error=f"This Space cannot read the workspace {repo}: the Space secret HF_TOKEN is not set. "
                             f"Add it in the Space settings (a token that can read and write {repo}).")
        return cls(HubStore(repo, token))

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
        start = time.perf_counter()
        root, revision = self.store.snapshot()
        fetched = time.perf_counter()
        m = load_method(method_scripts(root))
        self.snap = Snapshot(root, revision, m, m.cards.Workspace(root), time.time())
        log.info("Loaded the workspace%s: git %.2f s, reading it %.2f s", f" at {revision[:7]}" if revision else "",
                 fetched - start, time.perf_counter() - fetched)
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
        """Load the latest workspace and pull requests. Shows problems instead of raising."""
        if self.store is None:
            return
        with self._lock:
            try:
                self._fresh()
            except SpaceError as exc:
                self.error = str(exc)
                return
            self.error, self.notes = None, []
            try:
                start = time.perf_counter()
                self.pull_requests = self.store.pull_requests()
                log.info("Listed the pull requests: %.2f s", time.perf_counter() - start)
            except Exception as exc:
                self.notes.append(f"the pull requests could not be listed ({type(exc).__name__})")

    def refresh_if_stale(self, max_age: float = MAX_AGE) -> None:
        if self.snap is None or time.time() - self.snap.loaded_at > max_age:
            self.refresh()

    def current(self) -> Snapshot:
        """The loaded workspace, or a SpaceError saying why there is none."""
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
        except (FileNotFoundError, IsADirectoryError):
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

    # --- the frame of every page ---

    def status_line(self) -> str:
        if self.snap is None:
            return f"**{self.error}**" if self.error else "Loading…"
        ws = self.snap.ws
        version = (ws.project.get("method") or {}).get("physics_hive_version", "?")
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
        """The project's name: the workspace repository org/physics-hive-x, or the local folder, gives x."""
        label = self.store.label if self.store is not None else "PhysicsHive"
        return label.rstrip("/").rsplit("/", 1)[-1].removeprefix("physics-hive-")

    def hub_url(self, kind: str, *parts: str) -> str | None:
        """A page on the Hub for one of the project's repositories (None in local mode)."""
        repo = self.current().ws.hub.get(kind)
        if self.local or not repo:
            return None
        return "/".join([f"{HUB}/datasets/{repo}", *parts])

    def awaiting_count(self) -> int:
        """Open debriefs in which the researcher has not answered, ticked or written anything yet."""
        try:
            snap = self.current()
            readers = snap.m.human.read_by(snap.ws.sessions.values())
            return sum(1 for s in snap.ws.sessions.values()
                       if s.debrief is not None and s.id not in readers and not answered(s.debrief))
        except SpaceError:
            return 0

    # --- Review ---

    def debriefs(self) -> list[dict]:
        """Every debrief, newest first, with its state: open until a later session has read it.

        `answered`: the researcher has written an answer or a note, or ticked a line, in it."""
        snap = self.current()
        readers = snap.m.human.read_by(snap.ws.sessions.values())
        return [self._debrief(session, readers.get(session.id))
                for session in sorted(snap.ws.sessions.values(), key=lambda s: -s.number) if session.debrief is not None]

    def _debrief(self, session, reader) -> dict:
        rel = f"{session.path}/debrief.md"
        d = session.debrief
        # The template's "Read the full note: `sessions/S<n>/note.tex`." line: the note is on the same page.
        summary = re.sub(r"^Read the full note: `sessions/S\d+/note\.tex`\.?[ \t]*$", "", d.summary, flags=re.M).strip()
        return {"id": session.id, "number": session.number, "path": rel, "text": self.read(rel), "d": d,
                "summary_text": summary, "answered": answered(d), "groups": tick_groups(d.ticks),
                "changes": parse_changed(d.changed) if d.changed else None,
                "open": reader is None, "read_by": reader[0] if reader else None,
                "read_on": reader[1] if reader else None, "summary": first_sentence(d.summary)}

    def review(self, card_footer=None) -> dict:
        """The Review page: the newest debrief still open, as its session's page, and the other open ones.

        With none open, the newest debrief, which the researcher may still add to."""
        rows = self.debriefs()
        waiting = [r for r in rows if r["open"]]
        ws = self.current().ws
        return {"any": bool(rows), "running": self.running(),
                "view": self.session_page(waiting[0]["id"], card_footer) if waiting else None,
                "also": [{"id": r["id"], "number": r["number"], "title": self.title_of(ws.sessions[r["id"]])}
                         for r in waiting[1:]],
                "latest": rows[0] if rows and not waiting else None}

    def review_session(self) -> str | None:
        """The session the Review page shows: the newest one whose debrief is still open."""
        return next((r["id"] for r in self.debriefs() if r["open"]), None)

    def running(self) -> list[dict]:
        """Sessions running now: open session pull requests (Hub), or the active session of a local folder."""
        if self.local:
            path = self.current().root / ".active-session"
            if path.is_file():
                import json

                info = json.loads(path.read_text(encoding="utf-8"))
                return [{"id": info.get("id"), "title": f"{info.get('id')} started {info.get('started', '')[:16]}",
                         "url": None}]
            return []
        return [{"id": f"S{pr['num']}", "title": pr["title"], "url": pr["url"]}
                for pr in self.pull_requests if is_session_pr(pr) and pr["status"] in ("draft", "open")]

    # --- Project ---

    def project(self) -> dict:
        snap = self.current()
        doc = snap.ws.project_doc
        return {"project": self.read("project.md"), "conventions": self.read("conventions.md"),
                "title": doc.title if doc and not doc.is_template else None,
                "no_next_step": doc is not None and not doc.next_steps}

    # --- LaTeX: the draft and the notes ---

    def bib(self) -> dict:
        snap = self.current()
        return latex.parse_bib(snap.m.regen.render_bib(snap.ws))

    def card_href(self, card_id: str) -> str | None:
        return f"/card/{card_id}" if card_id in self.current().ws.cards else None

    def paper_href(self, paper_id: str) -> str | None:
        return f"/paper/{paper_id}" if paper_id in self.current().ws.papers else None

    def card_note(self, card_id: str) -> str | None:
        """A warning on a card named in the draft: refuted, revised, missing, or to re-check."""
        ws = self.current().ws
        status = ws.status(card_id)
        if status == "refuted":
            return f"{card_id} was refuted by {', '.join(ws.refuters(card_id))}."
        if status == "revised":
            return f"{card_id} was revised by {', '.join(ws.revisers(card_id))}."
        if status == "missing":
            return f"There is no card {card_id}."
        if ws.needs_recheck(card_id):
            return f"{card_id} needs a re-check: it depends on {', '.join(ws.needs_recheck(card_id))}."
        return None

    def render_tex(self, tex: str, flags: bool = False, card_footer=None) -> latex.Rendered:
        """A LaTeX text as HTML, with card links, flags on cards in doubt (for the draft), references, and
        under each result the HTML that card_footer gives for its cards (for the session page)."""
        snap = self.current()
        footer = getattr(card_footer, "__qualname__", "") if card_footer else ""
        key = hashlib.sha256(f"{snap.revision}|{snap.loaded_at}|{flags}|{footer}|{tex}".encode()).hexdigest()
        if key not in self._renders:
            if len(self._renders) > 64:
                self._renders.clear()
            self._renders[key] = latex.render(tex, bib=self.bib(), card_href=self.card_href,
                                              card_note=self.card_note if flags else None, paper_href=self.paper_href,
                                              card_footer=card_footer)
        return self._renders[key]

    def draft(self) -> dict:
        ws = self.current().ws
        tex = self.read("draft.tex")
        return {"tex": tex, "html": self.render_tex(tex, flags=True), "flags": ws.draft_flags(),
                "results": sum(1 for b in ws.draft if b.kind == "result"),
                "conjectures": sum(1 for b in ws.draft if b.kind == "conjecture")}

    def state_of(self, session, readers: dict, running: set) -> str:
        """Where a session stands: running, without a debrief, read by a later session, or waiting for the researcher."""
        if session.id in running:
            return "Running now"
        if session.debrief is None:
            return "No debrief"
        if session.id in readers:
            return f"Read by {readers[session.id][0]}"
        return "Answered, waiting for the next session" if answered(session.debrief) else "Awaiting your response"

    def title_of(self, session) -> str:
        """The title of a session's note, as HTML, or '' if it has none."""
        return self.render_tex(self.read(f"{session.path}/note.tex")).title if session.has_note else ""

    def sessions(self) -> list[dict]:
        """One row per session, newest first, with the title and abstract of its note."""
        snap = self.current()
        readers = snap.m.human.read_by(snap.ws.sessions.values())
        running = {r["id"] for r in self.running()}
        rows = []
        for session in sorted(snap.ws.sessions.values(), key=lambda s: -s.number):
            rendered = self.render_tex(self.read(f"{session.path}/note.tex")) if session.has_note else None
            rows.append({"id": session.id, "number": session.number, "goal": session.goal,
                         "state": self.state_of(session, readers, running),
                         "date": long_date((session.received or {}).get("started")), "has_note": session.has_note,
                         "title": rendered.title if rendered else "",
                         "abstract": first_sentence(re.sub(r"<[^>]+>", "", rendered.abstract), 300) if rendered else ""})
        return rows

    def session_page(self, session_id: str, card_footer=None) -> dict:
        """One session on one page: its note, cut to the abstract and the results until the researcher asks for
        all of it, the cards that no result of the note names, its debrief, and its record.

        card_footer(card_id) gives the HTML shown under a result of the note that names the card."""
        snap = self.current()
        ws = snap.ws
        session = ws.sessions.get(session_id)
        if session is None:
            raise SpaceError(f"There is no session {session_id} in this workspace.")
        readers = snap.m.human.read_by(ws.sessions.values())
        running = {r["id"] for r in self.running()}
        note = (self.render_tex(self.read(f"{session.path}/note.tex"), card_footer=card_footer)
                if session.has_note else None)
        named = {c for block in note.blocks for c in block.cards} if note else set()
        return {"id": session.id, "number": session.number, "session": session, "goal": session.goal,
                "date": long_date((session.received or {}).get("started")),
                "state": self.state_of(session, readers, running),
                "read_on": readers[session.id][1] if session.id in readers else None,
                "note": note, "note_path": f"{session.path}/note.tex",
                "other_cards": [self.row(c.id) for c in ws.sorted_cards() if c.session == session.id and c.id not in named],
                "debrief": self._debrief(session, readers.get(session.id)) if session.debrief is not None else None,
                "record": self.record(session)}

    def pdf(self, rel: str) -> tuple[bytes, str]:
        """The PDF of the draft or of a note, compiled now. Raises a SpaceError with the LaTeX errors."""
        snap = self.current()
        if rel != "draft.tex" and not re.match(r"^sessions/S\d+/note\.tex$", rel):
            raise SpaceError(f"{rel} is not the draft or a note.")
        tex = self.read(rel)
        if not tex:
            raise SpaceError(f"There is no {rel}.")
        data, log = snap.m.pdf.build_pdf(tex, snap.m.regen.render_bib(snap.ws), Path(rel).stem)
        if data is None:
            raise SpaceError(f"{rel} did not compile to PDF:\n\n```\n{log}\n```")
        name = "draft.pdf" if rel == "draft.tex" else f"note-{rel.split('/')[1]}.pdf"
        return data, name

    # --- Literature ---

    def literature(self) -> dict:
        snap = self.current()
        ws, human = snap.ws, snap.m.human
        overview = self.read("literature/overview.md")
        topics = [t.strip() for t in re.findall(r"^## (.+)$", overview, flags=re.M)]
        groups: dict[str, list[dict]] = {t: [] for t in topics}
        for paper_id in sorted(ws.papers, key=snap.m.cards.natural_key):
            paper = ws.papers[paper_id]
            authors = paper.meta.get("authors") or []
            first = str(authors[0]) if isinstance(authors, list) and authors else str(authors or "")
            byline = (first.split(",")[0] if "," in first else first) + (" et al." if isinstance(authors, list)
                                                                          and len(authors) > 1 else "")
            mine = ws.ratings.get(paper_id)
            row = {"id": paper_id, "title": paper.title or paper_id, "by": byline, "year": paper.year,
                   "why": paper.why, "mine": mine, "agent": paper.rating, "rating": mine or paper.rating or ""}
            groups.setdefault(paper.topic if paper.topic in groups else "Other papers", []).append(row)
        return {"overview": overview, "groups": [(t, rows) for t, rows in groups.items() if rows],
                "count": len(ws.papers), "ratings": human.RATINGS,
                "seeds": self.read("literature/seeds.md")}

    def paper(self, paper_id: str) -> dict:
        ws = self.current().ws
        paper = ws.papers.get(paper_id)
        if paper is None:
            raise SpaceError(f"There is no paper card {paper_id}.")
        authors = paper.meta.get("authors") or []
        return {"paper": paper, "authors": ", ".join(map(str, authors)) if isinstance(authors, list) else str(authors),
                "arxiv": paper.meta.get("arxiv"), "doi": paper.meta.get("doi"), "body": self.body(paper.path),
                "mine": ws.ratings.get(paper_id), "ratings": self.current().m.human.RATINGS}

    # --- the session record ---

    def row(self, card_id: str) -> dict:
        """What a list shows of a card."""
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        card = ws.cards.get(card_id)
        if card is None:
            return {"id": card_id, "kind": None, "status": "missing", "status_text": "missing", "recheck": [],
                    "statement": "", "evidence": None, "draft": None}
        recheck = [] if ws.status(card_id) in ("refuted", "revised") else ws.needs_recheck(card_id)
        claim = card.kind == "claim"
        evidence, tone = evidence_text(ws, card.id) if claim else (None, None)
        return {"id": card.id, "kind": card.kind, "status": ws.status(card.id),
                "status_text": regen.status_text(ws, card.id), "recheck": [(c, ws.status(c)) for c in recheck],
                "statement": card.statement, "draft": ws.in_draft(card.id),
                "evidence": regen.evidence_parts(ws, card.id) if claim else None,
                "evidence_text": evidence, "tone": tone, "place": place_text(ws, card.id) if claim else None,
                "warning": warning_text(ws, card.id) if claim else None, "refutes": card.refutes}

    def card(self, card_id: str) -> dict:
        snap = self.current()
        ws, regen = snap.ws, snap.m.regen
        card = ws.cards.get(card_id)
        if card is None:
            raise SpaceError(f"There is no card {card_id} in this workspace.")
        dependents = [c.id for c in ws.sorted_cards() if card_id in c.depends_on]
        related = [("Depends on", card.depends_on), ("Cards that depend on it", dependents),
                   ("Supersedes", card.supersedes), ("Revised by", ws.revisers(card_id)),
                   ("Refutes", card.refutes), ("Refuted by", ws.refuters(card_id))]
        evidence = []
        for ev in ws.evidence(card_id):
            art = ws.artefacts[ev.artefact]
            title = f"{art.id} ({art.kind})" + (f", attached by the review {ev.attached_by}" if ev.attached_by else "")
            files = [{"path": p, "text": clip(self.read(p))} for p in art.full]
            reviews = [{"title": f"Review {regen.review_label(r)}: {r.verdict}", "body": self.body(r.path) or "(no text)"}
                       for r in ev.reviews]
            evidence.append({"title": title, "summary": self.body(art.path), "files": files, "reviews": reviews})
        produced = card.produced_by
        origin = (f"from {produced.get('user', '?')}" if produced.get("kind") == "human" else
                  f"agent ({produced.get('model', '?')}), operator {produced.get('operator', '?')}")
        return {"card": card, "row": self.row(card_id), "origin": origin + (f", session {card.session}" if card.session else ""),
                "related": [(label, [self.row(i) for i in ids]) for label, ids in related if ids],
                "evidence": evidence, "trace": self.hub_url("traces", "tree/main", card.session) if card.session else None}

    def record(self, session) -> dict:
        """What a session's page folds away: what it received, its brief, its artefacts and critiques, its log,
        its debrief as written, its pull request and its trace."""
        snap = self.current()
        received = self.body(f"{session.path}/received.md").strip().strip("`").removeprefix("text").strip()
        artefacts = [a for a in sorted(snap.ws.artefacts.values(), key=lambda a: snap.m.cards.natural_key(a.id))
                     if snap.m.cards.session_of(a.id) == session.id]
        critiques = sorted(p.relative_to(snap.root).as_posix() for p in (snap.root / "critiques").glob(f"CR-{session.id}-*.md"))
        return {"brief": self.body(f"{session.path}/brief.md"), "received": received,
                "log": f"{session.path}/log.md" if session.has_log else None, "artefacts": artefacts,
                "critiques": critiques, "debrief": f"{session.path}/debrief.md" if session.debrief is not None else None,
                "pr": self.hub_url("workspace", "discussions", str(session.number)),
                "trace": self.hub_url("traces", "tree/main", session.id)}

    def file_path(self, rel: str) -> Path | None:
        parts = Path(rel or "").parts
        if not parts or rel.startswith("/") or ".." in parts or parts[0] in (".git",):
            return None
        path = self.current().root / rel
        return path if path.is_file() else None

    def file(self, rel: str) -> dict:
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

    # ----- writes -----

    def _require(self, user: str | None, action: str) -> None:
        if not user:
            raise SpaceError(f"Sign in with your Hugging Face account to {action}.")

    def _commit(self, snap: Snapshot, files: dict[str, str], message: str) -> str:
        """Commit on the snapshot, then reload. Returns the commit as the confirmation names it (empty in local mode)."""
        start = time.perf_counter()
        try:
            url = self.store.commit(files, message, snap.revision)
        except SpaceError:
            raise
        except Exception as exc:
            raise SpaceError(f"The Hub refused the commit ({type(exc).__name__}: {exc}). If main moved meanwhile, "
                             "reload the page and save again.") from exc
        log.info("Committed %r: %.2f s", message, time.perf_counter() - start)
        self.refresh()
        return f" (commit [{url.rstrip('/').rsplit('/', 1)[-1][:7]}]({url}))" if url else ""

    def _unchanged_since(self, rel: str, base: str | None) -> str:
        """The file's current text, after checking that it is still the text the editor started from."""
        current = self.read(rel)
        if base is not None and normalise(current).strip() != normalise(base).strip():
            raise SpaceError(f"{rel} changed since you opened it (a session may have ended). Copy your text, reload "
                             "the page, and apply your change again.")
        return current

    def editable(self, rel: str) -> bool:
        return rel in EDITABLE or bool(DEBRIEF_RE.match(rel))

    @timed
    def save_file(self, user: str | None, rel: str, content: str, base: str | None = None) -> str:
        """Save one of the researcher's files as they typed it."""
        self._require(user, "save")
        if not self.editable(rel):
            raise SpaceError(f"{rel} is not one of the files you edit here.")
        content = normalise(content)
        with self._lock:
            snap = self._fresh()
            current = self._unchanged_since(rel, base)
            if content.strip() == current.strip():
                raise SpaceError("Nothing to save: the text is the same.")
            if rel == "draft.tex":
                self._check_draft(snap, current, content)
            commit = self._commit(snap, {rel: content}, f"Edit {rel} ({user}, from the Space)")
        return f"Saved {rel}{commit}."

    def _check_draft(self, snap: Snapshot, old: str, new: str) -> None:
        """Refuse a draft that adds a result the workspace's check refuses (or names a card that does not exist)."""
        draft_problems = snap.m.check.draft_problems
        before = {(card, kind) for card, kind, _ in draft_problems(snap.ws, old)}
        added = [msg for card, kind, msg in draft_problems(snap.ws, new) if (card, kind) not in before]
        if added:
            raise SpaceError("The draft was not saved: " + "; ".join(added) + ". A result needs a claim with a "
                             "confirming review; put the others in a conjecture environment, or say in a debrief "
                             "that you checked the work by hand.")

    @timed
    def save_debrief(self, user: str | None, session_id: str, answers: dict[int, str], ticked: set[int],
                     note: str, base: str | None = None) -> str:
        """Write the researcher's answers, ticks and note into a debrief. The next session applies what is ticked."""
        self._require(user, "answer")
        rel = f"sessions/{session_id}/debrief.md"
        with self._lock:
            snap = self._fresh()
            human = snap.m.human
            if not DEBRIEF_RE.match(rel) or not (snap.root / rel).is_file():
                raise SpaceError(f"There is no debrief for {session_id}.")
            text = self._unchanged_since(rel, base)
            parsed = human.parse_debrief(text)
            new = text
            for q in parsed.questions:
                answer = (answers.get(q.number) or "").replace("\r\n", "\n").strip()
                if answer != q.answer:
                    new = human.set_answer(new, q.number, answer)
            new = human.set_ticks(new, {i: i in ticked for i in range(len(parsed.ticks))})
            note = (note or "").replace("\r\n", "\n").strip()
            if note != parsed.note:
                new = human.set_note(new, note)
            new = normalise(new)
            if new == normalise(text):
                return "Nothing changed."
            commit = self._commit(snap, {rel: new}, f"Answer the {session_id} debrief ({user}, from the Space)")
        return f"Saved your answers to the {session_id} debrief{commit}. The next session reads them."

    @timed
    def rate(self, user: str | None, paper_id: str, rating: str) -> str:
        """Set (or clear, with '') the researcher's rating of a paper, in literature/ratings.yaml."""
        self._require(user, "rate papers")
        rating = (rating or "").strip().lower()
        with self._lock:
            snap = self._fresh()
            human = snap.m.human
            if paper_id not in snap.ws.papers:
                raise SpaceError(f"There is no paper card {paper_id}.")
            if rating and rating not in human.RATINGS:
                raise SpaceError(f"A rating is one of: {', '.join(human.RATINGS)}.")
            ratings = dict(snap.ws.ratings)
            if ratings.get(paper_id, "") == rating:
                return "Nothing changed."
            if rating:
                ratings[paper_id] = rating
            else:
                ratings.pop(paper_id, None)
            commit = self._commit(snap, {human.RATINGS_FILE: human.dump_ratings(ratings)},
                                  f"Rate {paper_id} {rating or 'unrated'} ({user}, from the Space)")
        return f"Rated {paper_id} **{rating}**{commit}." if rating else f"Removed your rating of {paper_id}{commit}."
