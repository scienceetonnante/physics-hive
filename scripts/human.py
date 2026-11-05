"""The human view of a workspace: the files the researcher reads and writes.

The researcher works with a handful of files, never with the record:

- `project.md`: the question in one line as its title, then Goal, Approach
  and Next steps;
- `conventions.md`;
- `draft.tex`: the draft paper; a claim is established when a `result`
  environment in it names its card with `\\card{CL-...}`;
- `sessions/S<n>/note.tex`: what a session found (written by an agent);
- `sessions/S<n>/debrief.md`: what a session asks of the researcher (questions
  with an answer line, tick lines, a free note), and the researcher's answers;
- `literature/seeds.md` and `literature/ratings.yaml`.

This module parses those files, writes answers, ticks and notes back into a
debrief, and computes what a new session receives from the researcher: what
they wrote in debriefs and their edits of the human files since the previous
session started. That last part reads git history through a small `History`
object, so that `session.py` (on a checkout) and the Space (on its clone of the
workspace) compute the same thing. Stdlib and PyYAML only; imported by cards.py.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Files the researcher writes and agents may change only as the design says
# (apply a ticked line, remove a finished step, fix a convention). Every
# change a session makes to them is listed in its debrief.
HUMAN_FILES = ("project.md", "conventions.md", "draft.tex")
# Files only the researcher writes.
RESEARCHER_FILES = ("literature/seeds.md", "literature/ratings.yaml")
RATINGS = ("high", "medium", "low", "not relevant")
RATINGS_FILE = "literature/ratings.yaml"

TITLE_PLACEHOLDER = "<the question in one line>"


def one_line(text: str, limit: int = 0) -> str:
    text = " ".join(str(text or "").split())
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def strip_comments(markdown: str) -> str:
    """Markdown without its HTML comments (the templates' instructions)."""
    return re.sub(r"<!--.*?-->", "", markdown, flags=re.S)


# ----- project.md -----


@dataclass
class Project:
    title: str
    sections: dict[str, str]
    next_steps: list[str]

    @property
    def is_template(self) -> bool:
        """True while the title or the goal has not been written yet."""
        title = self.title.strip()
        return not title or title == TITLE_PLACEHOLDER or not self.sections.get("Goal", "").strip()


def list_items(text: str) -> list[str]:
    """The items of the first-level list in a Markdown section, each as one line of text."""
    items: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^(?:\d+[.)]|[-*+])\s+(.*)$", line)
        if m:
            items.append(m.group(1).strip())
        elif items and line.startswith((" ", "\t")) and line.strip():
            items[-1] += " " + line.strip()
    return items


def parse_project(text: str) -> Project:
    text = strip_comments(text)
    title, sections, current, lines = "", {}, None, []
    for line in text.splitlines():
        if line.startswith("# ") and not title and current is None:
            title = line[2:].strip()
        elif line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current, lines = line[3:].strip(), []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return Project(title=title, sections=sections, next_steps=list_items(sections.get("Next steps", "")))


# ----- debriefs -----

QUESTION_RE = re.compile(r"^\*\*Question\s+(\d+)\.?\*\*\.?\s*(.*)$")
ANSWER_RE = re.compile(r"^>\s?\*\*Answer:?\*\*:?\s?(.*)$")
NOTE_RE = re.compile(r"^>\s?\*\*Note:?\*\*:?\s?(.*)$")
TICK_RE = re.compile(r"^([-*+])\s+\[([ xX])\]\s+(.*)$")
CHANGED_HEADING = "#### Changed by this session"
NOTE_HEADING = "#### Anything else for the next session"


@dataclass
class Question:
    number: int
    text: str
    answer: str  # "" when unanswered
    line: int  # index of the question line


@dataclass
class Tick:
    text: str
    checked: bool
    line: int  # index of the tick line


@dataclass
class Debrief:
    summary: str
    changed: str  # the text of "Changed by this session" ("" when absent)
    questions: list[Question]
    ticks: list[Tick]
    note: str
    has_note: bool
    has_changed: bool


def _quote_block(lines: list[str], start: int, first: str) -> tuple[str, int]:
    """The text of a blockquote that starts at `start` (its first line's text is `first`); returns (text, end)."""
    parts = [first]
    end = start + 1
    while end < len(lines) and lines[end].startswith(">"):
        parts.append(re.sub(r"^>\s?", "", lines[end]))
        end += 1
    return "\n".join(parts).strip(), end


def _is_marker(line: str) -> bool:
    return bool(line.startswith("#### ") or QUESTION_RE.match(line) or line.startswith("**Tick")
                or TICK_RE.match(line) or ANSWER_RE.match(line) or NOTE_RE.match(line))


def parse_debrief(text: str) -> Debrief:
    lines = text.replace("\r\n", "\n").split("\n")
    summary_end = next((i for i, line in enumerate(lines) if _is_marker(line)), len(lines))
    summary = "\n".join(lines[:summary_end]).strip()
    questions: list[Question] = []
    ticks: list[Tick] = []
    note, has_note, changed, has_changed = "", False, "", False
    i = summary_end
    while i < len(lines):
        line = lines[i]
        if line.strip() == CHANGED_HEADING:
            has_changed = True
            j = i + 1
            while j < len(lines) and not _is_marker(lines[j]):
                j += 1
            changed = "\n".join(lines[i + 1:j]).strip()
            i = j
            continue
        m = QUESTION_RE.match(line)
        if m:
            parts, j = [m.group(2)], i + 1
            while j < len(lines) and not _is_marker(lines[j]):
                parts.append(lines[j])
                j += 1
            answer = ""
            if j < len(lines) and ANSWER_RE.match(lines[j]):
                answer, j = _quote_block(lines, j, ANSWER_RE.match(lines[j]).group(1))
            questions.append(Question(int(m.group(1)), "\n".join(parts).strip(), answer, i))
            i = j
            continue
        m = TICK_RE.match(line)
        if m:
            parts, j = [m.group(3)], i + 1
            while j < len(lines) and lines[j].startswith(("  ", "\t")) and lines[j].strip():
                parts.append(lines[j].strip())
                j += 1
            ticks.append(Tick(" ".join(parts).strip(), m.group(2) != " ", i))
            i = j
            continue
        m = NOTE_RE.match(line)
        if m:
            note, i = _quote_block(lines, i, m.group(1))
            has_note = True
            continue
        i += 1
    return Debrief(summary, changed, questions, ticks, note, has_note, has_changed)


def debrief_problems(text: str) -> list[str]:
    """What is wrong with the shape of a debrief, in words the coordinator can act on."""
    problems = []
    d = parse_debrief(text)
    if not d.summary:
        problems.append("it has no summary before its first section")
    numbers = [q.number for q in d.questions]
    if len(set(numbers)) != len(numbers):
        problems.append("two questions have the same number")
    lines = text.splitlines()
    for q in d.questions:
        following = [ln for ln in lines[q.line + 1:] if ln.strip()]
        if not any(ANSWER_RE.match(ln) for ln in following[:12]):
            problems.append(f"question {q.number} has no answer line (> **Answer:**)")
    if not d.has_note:
        problems.append(f"it has no note box ({NOTE_HEADING}, then > **Note:**)")
    return problems


def _quote(prefix: str, text: str) -> list[str]:
    """`text` as a blockquote whose first line starts with `prefix` (for example '**Answer:**')."""
    rows = (text or "").replace("\r\n", "\n").strip().split("\n")
    out = [f"> {prefix} {rows[0]}".rstrip()]
    out += [f"> {row}".rstrip() for row in rows[1:]]
    return out


def set_answer(text: str, number: int, answer: str) -> str:
    """Write the answer to question `number`, replacing any earlier answer."""
    lines = text.replace("\r\n", "\n").split("\n")
    question = next((q for q in parse_debrief(text).questions if q.number == number), None)
    if question is None:
        raise ValueError(f"the debrief has no question {number}")
    j = question.line + 1
    while j < len(lines) and not _is_marker(lines[j]):
        j += 1
    if j < len(lines) and ANSWER_RE.match(lines[j]):
        _, end = _quote_block(lines, j, "")
        lines[j:end] = _quote("**Answer:**", answer)
    else:
        lines[j:j] = _quote("**Answer:**", answer) + [""]
    return "\n".join(lines)


def set_ticks(text: str, checked: dict[int, bool]) -> str:
    """Tick or untick tick lines, by their index among the debrief's tick lines."""
    lines = text.replace("\r\n", "\n").split("\n")
    for index, tick in enumerate(parse_debrief(text).ticks):
        if index in checked:
            m = TICK_RE.match(lines[tick.line])
            lines[tick.line] = f"{m.group(1)} [{'x' if checked[index] else ' '}] {m.group(3)}"
    return "\n".join(lines)


def set_note(text: str, note: str) -> str:
    """Write the free note at the end of a debrief, replacing the earlier one."""
    lines = text.replace("\r\n", "\n").rstrip("\n").split("\n")
    at = next((i for i, line in enumerate(lines) if NOTE_RE.match(line)), None)
    if at is None:
        if not any(line.strip() == NOTE_HEADING for line in lines):
            lines += ["", NOTE_HEADING]
        lines += ["", *_quote("**Note:**", note)]
    else:
        _, end = _quote_block(lines, at, "")
        lines[at:end] = _quote("**Note:**", note)
    return "\n".join(lines) + "\n"


def set_changed(text: str, changed: str) -> str:
    """Write the section 'Changed by this session' (after the summary), replacing an earlier one."""
    lines = text.replace("\r\n", "\n").rstrip("\n").split("\n")
    block = [CHANGED_HEADING, "", *changed.strip().split("\n"), ""]
    at = next((i for i, line in enumerate(lines) if line.strip() == CHANGED_HEADING), None)
    if at is not None:
        end = at + 1
        while end < len(lines) and not _is_marker(lines[end]):
            end += 1
        lines[at:end] = block
    else:
        at = next((i for i, line in enumerate(lines) if _is_marker(line)), len(lines))
        if at and lines[at - 1].strip():
            block = [""] + block
        lines[at:at] = block
    return "\n".join(lines) + "\n"


# ----- LaTeX: the draft and the notes -----

CARD_RE = re.compile(r"\\card\{([^}]*)\}")
BLOCK_RE = re.compile(r"\\begin\{(result|conjecture)\}(\[[^\]]*\])?(.*?)\\end\{\1\}", re.S)


def strip_tex_comments(tex: str) -> str:
    """LaTeX without its comments (a `%` not escaped as `\\%`)."""
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in tex.splitlines())


def tex_cards(tex: str) -> list[str]:
    """The card IDs named with \\card{...} in a LaTeX text, in order, without repeats."""
    seen: list[str] = []
    for m in CARD_RE.finditer(strip_tex_comments(tex)):
        for card_id in (part.strip() for part in m.group(1).split(",")):
            if card_id and card_id not in seen:
                seen.append(card_id)
    return seen


@dataclass
class DraftBlock:
    kind: str  # "result" or "conjecture"
    title: str
    cards: list[str]
    line: int  # 1-based line of \begin in draft.tex


def parse_draft(tex: str) -> list[DraftBlock]:
    """The result and conjecture environments of the draft, with the cards each one names."""
    clean = strip_tex_comments(tex)
    blocks = []
    for m in BLOCK_RE.finditer(clean):
        blocks.append(DraftBlock(kind=m.group(1), title=(m.group(2) or "")[1:-1].strip(),
                                 cards=tex_cards(m.group(3)), line=clean.count("\n", 0, m.start()) + 1))
    return blocks


# ----- ratings -----


def parse_ratings(text: str) -> dict[str, str]:
    """The researcher's ratings of papers: paper card ID -> high, medium, low or not relevant."""
    try:
        data = yaml.safe_load(text or "") or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip().lower().replace("-", " ") for k, v in data.items()
            if str(v).strip().lower().replace("-", " ") in RATINGS}


def dump_ratings(ratings: dict[str, str]) -> str:
    head = ("# Your ratings of papers (high, medium, low, not relevant), written by the Space.\n"
            "# Agents read this file and never write it. The next survey favours what you rated high.\n")
    body = "".join(f"{paper}: {ratings[paper]}\n" for paper in sorted(ratings))
    return head + body


# ----- what a new session receives -----


@dataclass
class Commit:
    sha: str
    subject: str
    date: str
    files: dict[str, tuple[int, int]]  # path -> (lines added, lines removed)


def is_session_commit(subject: str) -> bool:
    """Commits made by sessions start with their session: `[S12] ...` (also the squash merge on the Hub)."""
    return bool(re.match(r"^\[S\d+\]", subject))


def is_method_commit(subject: str) -> bool:
    """Commits made by init: the workspace's first commit (with the templates) and upgrades of the method copy."""
    return subject.startswith(("Initialize PhysicsHive workspace", "Upgrade the method copy"))


class History:
    """Read-only access to the git history of a workspace checkout (or of the Space's clone)."""

    def __init__(self, root: Path, since: str | None):
        self.root = Path(root)
        self.since = since

    def _git(self, *args: str) -> str:
        proc = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
        return proc.stdout if proc.returncode == 0 else ""

    def available(self) -> bool:
        return bool(self._git("rev-parse", "--verify", "-q", "HEAD").strip())

    def old_text(self, path: str) -> str | None:
        """The file as it was at `since` (None if it did not exist, or there is no `since`)."""
        if not self.since:
            return None
        proc = subprocess.run(["git", "-C", str(self.root), "show", f"{self.since}:{path}"], capture_output=True,
                              text=True)
        return proc.stdout if proc.returncode == 0 else None

    def commits(self, paths: tuple[str, ...], since: str | None = None, until: str = "HEAD") -> list[Commit]:
        """Commits after `since` (default: self.since) that touch `paths`, oldest first, with line counts."""
        since = since if since is not None else self.since
        rng = f"{since}..{until}" if since else until
        out = self._git("log", "--reverse", "--no-renames", "--numstat", "--format=\x1e%H\x1f%s\x1f%cI", rng, "--",
                        *paths)
        commits = []
        for chunk in out.split("\x1e")[1:]:
            head, _, rest = chunk.partition("\n")
            sha, subject, date = (head.split("\x1f") + ["", ""])[:3]
            files = {}
            for row in rest.splitlines():
                parts = row.split("\t")
                if len(parts) == 3:
                    added, removed, path = parts
                    files[path] = (int(added) if added.isdigit() else 0, int(removed) if removed.isdigit() else 0)
            commits.append(Commit(sha, subject, date, files))
        return commits

    def patch(self, sha: str, path: str) -> str:
        return self._git("show", "--format=", "--no-color", "-U1", sha, "--", path).strip()

    def uncommitted(self, paths: tuple[str, ...]) -> dict[str, tuple[int, int]]:
        """Line counts of changes not committed yet (a local researcher's edits), by path."""
        out = self._git("diff", "--numstat", "HEAD", "--", *paths)
        files = {}
        for row in out.splitlines():
            parts = row.split("\t")
            if len(parts) == 3 and parts[0].isdigit():
                files[parts[2]] = (int(parts[0]), int(parts[1]))
        return files

    def uncommitted_patch(self, path: str) -> str:
        return self._git("diff", "--no-color", "-U1", "HEAD", "--", path).strip()


@dataclass
class DebriefNews:
    session: str
    path: str
    full: bool  # an open debrief, read for the first time: everything in it counts
    answers: list[tuple[int, str, str]]  # (number, question, answer or "")
    ticked: list[str]  # lines to apply
    unticked: list[str]  # lines not ticked (open debriefs only)
    note: str
    note_changed: bool


@dataclass
class Received:
    previous: str | None  # the session whose start we count from, or None before the first session
    since: str | None  # the commit it started from
    debriefs: list[DebriefNews] = field(default_factory=list)
    edits: dict[str, tuple[int, int]] = field(default_factory=dict)  # researcher's edits of HUMAN_FILES
    patches: list[tuple[str, str, str]] = field(default_factory=list)  # (path, where it comes from, diff)
    ratings: list[tuple[str, str | None, str | None]] = field(default_factory=list)  # (paper, old, new)
    next_step: str | None = None
    unanswered: list[tuple[str, int, str]] = field(default_factory=list)  # (session, number, question)

    @property
    def debrief_ids(self) -> list[str]:
        return [d.session for d in self.debriefs]


def previous_start(sessions) -> tuple[str | None, str | None]:
    """The session that started last (from the `received.md` files), and the commit it started from."""
    best = None
    for session in sessions:
        meta = session.received or {}
        if meta.get("base") and (best is None or str(meta.get("started", "")) > str(best[2])):
            best = (session.id, str(meta["base"]), str(meta.get("started", "")))
    return (best[0], best[1]) if best else (None, None)


def _received_records(sessions) -> list[tuple[str, str, dict]]:
    """(reading session, its start, {debrief session: what it received}) for every received.md, oldest first."""
    rows = []
    for session in sessions:
        meta = session.received or {}
        debriefs = meta.get("debriefs") or {}
        if isinstance(debriefs, list):  # tolerate a bare list of sessions
            debriefs = {str(s): {} for s in debriefs}
        rows.append((session.id, str(meta.get("started", "")), {str(k): v or {} for k, v in debriefs.items()}))
    return sorted(rows, key=lambda row: row[1])


def read_by(sessions) -> dict[str, tuple[str, str]]:
    """For each session whose debrief a later session read: (the first session that read it, the date)."""
    result: dict[str, tuple[str, str]] = {}
    for reader, started, debriefs in _received_records(sessions):
        for session_id in debriefs:
            result.setdefault(session_id, (reader, started[:10]))
    return result


def already_received(sessions, debrief_session: str) -> tuple[dict[int, str], set[str], str | None]:
    """What earlier sessions received from one debrief: answers by question, ticked lines, the note."""
    answers: dict[int, str] = {}
    ticked: set[str] = set()
    note = None
    for _, _, debriefs in _received_records(sessions):
        got = debriefs.get(debrief_session)
        if got is None:
            continue
        for number, answer in (got.get("answers") or {}).items():
            answers[int(number)] = str(answer)
        ticked |= {str(t) for t in got.get("ticked") or []}
        if "note" in got:
            note = str(got.get("note") or "")
    return answers, ticked, note


def received(ws, history: History) -> Received:
    """What a session started now receives from the researcher, computed from the files and git.

    `ws` is a cards.Workspace; `history.since` must be the commit the previous
    session started from (see `previous_start`), or None before the first one.
    A debrief counts for what no earlier session received from it (each
    session records what it received in its received.md): in full when no
    session has read it yet, otherwise only the new answers, the newly ticked
    lines and a changed note. Edits of the human files are the commits since
    the previous start that sessions did not make, and uncommitted changes.
    """
    previous, _ = previous_start(ws.sessions.values())
    news = Received(previous=previous, since=history.since)
    readers = read_by(ws.sessions.values())
    for session in sorted(ws.sessions.values(), key=lambda s: s.number):
        if session.debrief is None:
            continue
        path = f"{session.path}/debrief.md"
        now = session.debrief
        if session.id not in readers:
            news.debriefs.append(DebriefNews(
                session=session.id, path=path, full=True,
                answers=[(q.number, q.text, q.answer) for q in now.questions],
                ticked=[t.text for t in now.ticks if t.checked],
                unticked=[t.text for t in now.ticks if not t.checked],
                note=now.note, note_changed=bool(now.note)))
            news.unanswered += [(session.id, q.number, q.text) for q in now.questions if not q.answer]
            continue
        got_answers, got_ticked, got_note = already_received(ws.sessions.values(), session.id)
        answers = [(q.number, q.text, q.answer) for q in now.questions
                   if q.answer and q.answer != got_answers.get(q.number, "")]
        ticked = [t.text for t in now.ticks if t.checked and t.text not in got_ticked]
        note_changed = now.note != (got_note or "")
        if answers or ticked or note_changed:
            news.debriefs.append(DebriefNews(session=session.id, path=path, full=False, answers=answers,
                                             ticked=ticked, unticked=[], note=now.note, note_changed=note_changed))

    if history.available():
        for commit in history.commits(HUMAN_FILES):
            if is_session_commit(commit.subject) or is_method_commit(commit.subject):
                continue
            for path, (added, removed) in commit.files.items():
                a, r = news.edits.get(path, (0, 0))
                news.edits[path] = (a + added, r + removed)
                news.patches.append((path, f"{commit.subject} ({commit.date[:16].replace('T', ' ')})",
                                     history.patch(commit.sha, path)))
        for path, (added, removed) in history.uncommitted(HUMAN_FILES).items():
            a, r = news.edits.get(path, (0, 0))
            news.edits[path] = (a + added, r + removed)
            news.patches.append((path, "not committed yet", history.uncommitted_patch(path)))

    old_ratings = parse_ratings(history.old_text(RATINGS_FILE) or "")
    for paper in sorted(set(old_ratings) | set(ws.ratings)):
        if old_ratings.get(paper) != ws.ratings.get(paper):
            news.ratings.append((paper, old_ratings.get(paper), ws.ratings.get(paper)))
    steps = ws.project_doc.next_steps if ws.project_doc else []
    news.next_step = steps[0] if steps else None
    return news


def format_received(news: Received, max_patch_lines: int = 60) -> str:
    """The text `session.py start` prints for what a new session receives."""
    since = f"since {news.previous} started" if news.previous else "since the project began"
    out = [f"From you {since}"]
    if not news.debriefs:
        out.append("  Debriefs: nothing new")
    for d in news.debriefs:
        out.append(f"  Debrief {d.session} ({d.path})" + ("" if d.full else ", changed since it was read"))
        for number, question, answer in d.answers:
            out.append(f"    Question {number}: {one_line(question, 110)}")
            out.append(f"      Answer: {one_line(answer)}" if answer else "      No answer yet.")
        if d.ticked:
            out.append("    Ticked, to apply before the brief:")
            out += [f"      ✓ {one_line(t)}" for t in d.ticked]
        if d.unticked:
            out.append("    Not ticked, so not applied:")
            out += [f"      · {one_line(t)}" for t in d.unticked]
        if d.full or d.note_changed:
            out.append(f"    Your note: {one_line(d.note) if d.note else 'none'}")
    out.append(f"  Your edits {since}")
    for path in HUMAN_FILES:
        if path in news.edits:
            added, removed = news.edits[path]
            out.append(f"    {path:<16} +{added} −{removed} lines")
        else:
            out.append(f"    {path:<16} unchanged")
    count = len(news.ratings)
    out.append(f"    {'literature':<16} " + (f"{count} rating{'s' if count != 1 else ''} changed" if count
                                              else "no rating changed"))
    for paper, old, new in news.ratings:
        out.append(f"      {paper}: {old or 'not rated'} → {new or 'not rated'}")
    out.append("First next step in project.md:")
    out.append(f"  {one_line(news.next_step)}" if news.next_step else "  (none: project.md lists no next step)")
    if news.patches:
        out.append("")
        out.append("Your edits, as diffs:")
        for path, where, patch in news.patches:
            rows = patch.splitlines()
            out.append(f"--- {path}: {where}")
            out += rows[:max_patch_lines]
            if len(rows) > max_patch_lines:
                out.append(f"… ({len(rows) - max_patch_lines} more lines; see git log -p -- {path})")
    return "\n".join(out)


def received_record(news: Received) -> dict:
    """What a session received, by debrief, as stored in its received.md (so that no later session gets it again)."""
    record = {}
    for d in news.debriefs:
        entry: dict = {}
        answers = {number: answer for number, _, answer in d.answers if answer}
        if answers:
            entry["answers"] = answers
        if d.ticked:
            entry["ticked"] = list(d.ticked)
        if d.full or d.note_changed:
            entry["note"] = d.note
        record[d.session] = entry
    return record


def handoff(log_text: str) -> str:
    """The `## Handoff` section a session writes at the end of its log, for the sessions after it."""
    m = re.search(r"^## Handoff[^\n]*\n(.*?)(?=^## |\Z)", log_text or "", flags=re.M | re.S)
    return m.group(1).strip() if m else ""


# ----- what a session changed in the human files -----


MAX_DRAFT_DIFF_LINES = 60


def changed_by_session(history: History, session: str, base: str) -> str:
    """The text of 'Changed by this session' for a debrief, from the session's own commits since `base`.

    It shows as a diff every change to conventions.md, and the changes to draft.tex that the session
    worded itself (those not made by an apply commit, which only copies what the researcher ticked).
    """
    commits = [c for c in history.commits(HUMAN_FILES, since=base) if c.subject.startswith(f"[{session}]")]
    lines = []
    for path in HUMAN_FILES:
        touching = [c for c in commits if path in c.files]
        if not touching:
            lines.append(f"- `{path}`: unchanged.")
            continue
        added = sum(c.files[path][0] for c in touching)
        removed = sum(c.files[path][1] for c in touching)
        reasons, own = [], []
        for c in touching:
            m = re.match(rf"^\[{re.escape(session)}\]\s*apply the lines ticked in the (S\d+) debrief", c.subject, re.I)
            reason = f"as you ticked in {m.group(1)}" if m else re.sub(r"^\[S\d+\]\s*", "", c.subject)
            if reason not in reasons:
                reasons.append(reason)
            if not m:
                own.append(c)
        lines.append(f"- `{path}` (+{added} −{removed} lines): " + "; ".join(reasons) + ".")
        shown = touching if path == "conventions.md" else own if path == "draft.tex" else []
        diff = [row for c in shown for row in history.patch(c.sha, path).splitlines()
                if row.startswith(("+", "-")) and not row.startswith(("+++", "---"))]
        if path == "draft.tex" and len(diff) > MAX_DRAFT_DIFF_LINES:
            more = len(diff) - MAX_DRAFT_DIFF_LINES
            diff = diff[:MAX_DRAFT_DIFF_LINES] + [f"… {more} more changed lines: read them in draft.tex."]
        if diff:
            if path == "draft.tex":
                lines += ["", "The session's own wording in the draft:"]
            lines += ["", "```diff", *diff, "```", ""]
    return "\n".join(lines).strip()
