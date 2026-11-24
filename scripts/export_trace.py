# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Export the harness's record of a session as JSON Lines.

Each harness keeps its own record of a conversation and its sub-agents:
OpenCode in a SQLite database, Claude Code, Codex and Pi in JSONL files. This
script collects, for one workspace and one time window, every record the
harness wrote, and writes them to <out>/trace.jsonl, one JSON object per line
with its source. It keeps the model's reasoning text when the harness stores
it. It returns the models it found in the record, the tokens each model used
(when the harness writes the counts), and the number of secrets it removed.

Secrets: before a record is written, every text in it that looks like a known
kind of token (Hugging Face, Anthropic, OpenAI, GitHub, AWS, private keys,
JWTs, signatures in URLs), or that equals the value of an environment variable
whose name contains TOKEN, KEY or SECRET, is replaced with a marker such as
[REDACTED:huggingface-token]. This lowers the risk that a trace leaks a
secret; it cannot rule it out. These pass through: a secret of another format
or printed in pieces, a secret used as a dictionary key, base64-encoded
credentials outside an HTTP Authorization header, and a password in a URL
(user:password@host) that has no known token format.

A record that cannot be written (for instance a value that is not JSON) is
replaced by a placeholder record that says so, and counted; the rest of the
trace is kept.

The window starts a few minutes before the session started, so that the
command that opened the session is included; it may therefore also include the
end of an earlier conversation in the same harness session.

Usage: uv run .physics-hive/scripts/export_trace.py --harness H --since ISO --out DIR [--workspace PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

MARGIN = dt.timedelta(minutes=5)


# ----- secrets -----

# Known token formats. Each needs a fixed prefix or structure, so that ordinary text (a git hash, a path,
# base64 data) does not match. Anthropic comes before OpenAI: both start with sk-.
# A private key's body: base64, header lines (Proc-Type: 4,ENCRYPTED), and line breaks, real or escaped as
# \n or \r (a key inside a JSON string, once or several times), up to its END line or the first other character.
KEY_BODY = r"(?:[A-Za-z0-9+/=\s:,-]|\\+[nr])"
SECRET_PATTERNS = [
    ("private-key", rf"-----BEGIN[A-Z ]*PRIVATE KEY-----{KEY_BODY}*?(?:-----END[A-Z ]*PRIVATE KEY-----|(?!{KEY_BODY}))"),
    ("huggingface-token", r"\bhf_[A-Za-z0-9]{30,}"),
    ("anthropic-key", r"\bsk-ant-[A-Za-z0-9_-]{32,}"),
    ("openai-key", r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}"),
    ("github-token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})"),
    ("aws-access-key", r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
]
KNOWN_SECRETS = re.compile("|".join(f"(?P<p{i}>{pattern})" for i, (_, pattern) in enumerate(SECRET_PATTERNS)))
# Secrets recognised by what precedes them, which is kept: the value of a query parameter that signs or
# authorises a URL (S3, Google Cloud Storage, CloudFront, Azure), and the credentials of an HTTP
# Authorization header (git sends the Hub token in one, base64-encoded).
PREFIXED_SECRETS = [
    ("signed-url", re.compile(r"(?i)([?&](?:x-amz-signature|x-amz-credential|x-amz-security-token|"
                              r"x-goog-signature|x-goog-credential|signature|sig|token|access_token|api_key|"
                              r"apikey)=)([^&\s\"'<>#\\]+)")),
    ("authorization-header", re.compile(r"(?i)(\bauthorization:\s*(?:basic|bearer|token)\s+)([A-Za-z0-9+/=._~-]{8,})")),
]
SECRET_NAME_WORDS = ("TOKEN", "KEY", "SECRET")
NOT_SECRET_NAME = re.compile(r"GIT_CONFIG_KEY_\d+")  # holds the name of a git setting; its value is in GIT_CONFIG_VALUE_<n>
MIN_SECRET_LENGTH = 12  # shorter values of such variables (flags, small numbers) would match ordinary text


def is_secret_value(value: str) -> bool:
    """A value worth searching for: long enough, one word, and not a path that exists."""
    if len(value) < MIN_SECRET_LENGTH or any(c.isspace() for c in value):
        return False
    try:
        return not os.path.exists(value)
    except (OSError, ValueError):
        return True


class Redactor:
    """Replaces secrets in the texts of a record with a marker that names their kind, and counts them."""

    def __init__(self, secrets=()):
        self.counts: Counter = Counter()
        values: dict[str, str] = {}
        for name, value in os.environ.items():
            if (any(word in name.upper() for word in SECRET_NAME_WORDS) and not NOT_SECRET_NAME.fullmatch(name)
                    and is_secret_value(value)):
                values.setdefault(value, f"env:{name}")
        for value in secrets:
            if value and is_secret_value(value):
                values.setdefault(value, "hub-token")
        self.kinds = values
        ordered = sorted(values, key=len, reverse=True)  # a longer value first, when one contains another
        self.literal = re.compile("|".join(map(re.escape, ordered))) if ordered else None

    def _known(self, match: re.Match) -> str:
        kind = SECRET_PATTERNS[int(match.lastgroup[1:])][0]
        self.counts[kind] += 1
        return f"[REDACTED:{kind}]"

    def _literal(self, match: re.Match) -> str:
        kind = self.kinds[match.group(0)]
        self.counts[kind] += 1
        return f"[REDACTED:{kind}]"

    def text(self, text: str) -> str:
        text = KNOWN_SECRETS.sub(self._known, text)
        for kind, pattern in PREFIXED_SECRETS:
            text = pattern.sub(lambda m, kind=kind: self._prefixed(kind, m), text)
        return self.literal.sub(self._literal, text) if self.literal else text

    def _prefixed(self, kind: str, match: re.Match) -> str:
        if match.group(2).startswith("[REDACTED:"):  # already replaced as a known format
            return match.group(0)
        self.counts[kind] += 1
        return match.group(1) + f"[REDACTED:{kind}]"

    def clean(self, value):
        """A copy of a JSON value with every string cleaned (dictionary keys are left as they are)."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        if isinstance(value, dict):
            return {key: self.clean(item) for key, item in value.items()}
        return value


# ----- token counts -----


def number(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class Usage:
    """Tokens used per model, from the counts the harness writes in its records.

    Every harness's counts are brought to four numbers: `input` (input tokens not read from the cache),
    `cache_read`, `cache_write` and `output` (including reasoning tokens). Claude Code repeats an API
    message's usage on each of its content blocks, and copies messages into a resumed session's file, so its
    counts are taken once per message ID. Codex writes running totals per session file, so its counts are
    the differences between successive totals.
    """

    def __init__(self, harness: str):
        self.harness = harness
        self.totals: dict[str, Counter] = {}
        self.claude: dict[str, tuple[str, dict]] = {}  # message id -> (model, counts)
        self.codex_model: dict[str, str] = {}  # source file -> model of the current turn
        self.codex_total: dict[str, dict] = {}  # source file -> last running total

    def add(self, model, input=0, output=0, cache_read=0, cache_write=0) -> None:
        counts = {"input": max(input, 0), "cache_read": cache_read, "cache_write": cache_write, "output": output}
        if not isinstance(model, str) or not model or model == "<synthetic>" or not any(counts.values()):
            return
        self.totals.setdefault(model, Counter()).update(counts)

    def record(self, source: str, record: dict, in_window: bool = True) -> None:
        """Count one record; records before the window only matter for Codex's running totals."""
        try:
            if self.harness == "codex":
                self._codex(source, record, in_window)
            elif in_window:
                getattr(self, f"_{self.harness}", lambda r: None)(record)
        except (AttributeError, TypeError, ValueError, KeyError):
            pass  # a record of an unexpected shape is not counted; the export goes on

    def _claude(self, record: dict) -> None:
        message = record.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
            return
        u = message["usage"]
        counts = {"input": number(u.get("input_tokens")), "output": number(u.get("output_tokens")),
                  "cache_read": number(u.get("cache_read_input_tokens")),
                  "cache_write": number(u.get("cache_creation_input_tokens"))}
        key = message.get("id") or f"line-{len(self.claude)}"
        self.claude[key] = (message.get("model"), counts)

    def _codex(self, source: str, record: dict, in_window: bool) -> None:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return
        if record.get("type") == "turn_context" and payload.get("model"):
            self.codex_model[source] = payload["model"]
            return
        if record.get("type") != "event_msg" or payload.get("type") != "token_count":
            return
        info = payload.get("info") or {}
        total = info.get("total_token_usage")
        if not isinstance(total, dict):
            return
        previous = self.codex_total.get(source, {})
        self.codex_total[source] = total
        if not in_window:
            return
        delta = {key: number(total.get(key)) - number(previous.get(key)) for key in total}
        if any(value < 0 for value in delta.values()):  # the running total restarted
            delta = {key: number(value) for key, value in (info.get("last_token_usage") or {}).items()}
        cached, written = delta.get("cached_input_tokens", 0), delta.get("cache_write_input_tokens", 0)
        self.add(self.codex_model.get(source, "unknown"), input=delta.get("input_tokens", 0) - cached - written,
                 output=delta.get("output_tokens", 0), cache_read=cached, cache_write=written)

    def _pi(self, record: dict) -> None:
        message = record.get("message")
        if record.get("type") != "message" or not isinstance(message, dict) or message.get("role") != "assistant":
            return
        u = message.get("usage")
        if isinstance(u, dict):
            self.add(message.get("model"), input=number(u.get("input")), output=number(u.get("output")),
                     cache_read=number(u.get("cacheRead")), cache_write=number(u.get("cacheWrite")))

    def _opencode(self, record: dict) -> None:
        info = record.get("message")
        tokens = info.get("tokens") if isinstance(info, dict) else None
        if isinstance(tokens, dict):
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            self.add(info.get("modelID"), input=number(tokens.get("input")),
                     output=number(tokens.get("output")) + number(tokens.get("reasoning")),
                     cache_read=number(cache.get("read")), cache_write=number(cache.get("write")))

    def result(self) -> dict:
        for model, counts in self.claude.values():
            self.add(model, **counts)
        self.claude = {}
        return {model: dict(counts) for model, counts in sorted(self.totals.items())}


class TraceWriter:
    """Writes records to trace.jsonl with their secrets replaced, and counts their tokens."""

    def __init__(self, out, harness: str, secrets=()):
        self.out = out
        self.redactor = Redactor(secrets)
        self.usage = Usage(harness)
        self.records = 0
        self.omitted = 0  # records replaced by a placeholder because they could not be written

    def write(self, source: str, record) -> None:
        try:
            if isinstance(record, dict):
                self.usage.record(source, record)
            line = json.dumps({"source": source, "record": self.redactor.clean(record)}, ensure_ascii=False)
            try:
                line.encode("utf-8")
            except UnicodeEncodeError:  # a lone surrogate, from a text cut in the middle of an emoji: escape it
                line = json.dumps({"source": source, "record": self.redactor.clean(record)})
        except Exception as exc:  # noqa: BLE001 - one bad record must not cost the rest of the trace
            self.omit(source, type(exc).__name__)
            return
        self.out.write(line + "\n")
        self.records += 1

    def omit(self, source: str, reason: str) -> None:
        """Keep the place of a record that could not be written, and say why (never with its content)."""
        placeholder = {"omitted": f"this record could not be written to the trace ({reason})"}
        self.out.write(json.dumps({"source": source, "record": placeholder}) + "\n")
        self.records += 1
        self.omitted += 1


def parse_time(value) -> dt.datetime | None:
    """Accept ISO strings and epoch seconds or milliseconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        return dt.datetime.fromtimestamp(seconds, dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def record_time(record: dict) -> dt.datetime | None:
    for key in ("timestamp", "time", "created_at", "ts"):
        if key in record:
            return parse_time(record[key])
    return None


def models_in(record: dict, found: set[str]) -> None:
    """Collect model identifiers from the usual places in a record."""
    stack = [record]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if key in ("model", "modelID", "model_id") and isinstance(value, str) and value and value != "<synthetic>":
                    found.add(value)
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(i for i in item if isinstance(i, (dict, list)))


def jsonl_lines(path: Path):
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ----- per harness -----


def claude_files(workspace: Path, start: dt.datetime) -> list[Path]:
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(workspace))
    folder = Path(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")).expanduser() / "projects" / encoded
    if not folder.is_dir():
        return []
    files = list(folder.glob("*.jsonl")) + list(folder.glob("*/subagents/*.jsonl"))
    return sorted(p for p in files if dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc) >= start)


def codex_files(workspace: Path, start: dt.datetime) -> list[Path]:
    root = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "sessions"
    if not root.is_dir():
        return []
    picked = []
    for path in root.rglob("rollout-*.jsonl"):
        if dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc) < start:
            continue
        for record in jsonl_lines(path):
            cwd = (record.get("payload") or {}).get("cwd") or (record.get("item") or {}).get("cwd")
            if cwd:
                if Path(cwd).resolve() == workspace:
                    picked.append(path)
                break
    return sorted(picked)


def pi_files(workspace: Path, start: dt.datetime) -> list[Path]:
    root = Path("~/.pi/agent/sessions").expanduser()
    if not root.is_dir():
        return []
    encoded = re.sub(r"[/\\]", "-", str(workspace)).strip("-")
    picked = []
    for folder in root.iterdir():
        if folder.is_dir() and folder.name.strip("-") == encoded:
            picked += [p for p in folder.rglob("*.jsonl")
                       if dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc) >= start]
    return sorted(picked)


def export_jsonl_files(files: list[Path], start: dt.datetime, out: TraceWriter, models: set[str]) -> None:
    for path in files:
        for record in jsonl_lines(path):
            when = record_time(record) if isinstance(record, dict) else None
            if when is not None and when < start:
                out.usage.record(str(path), record, in_window=False)
                continue
            if isinstance(record, dict):
                models_in(record, models)
            out.write(str(path), record)


def export_opencode(workspace: Path, start: dt.datetime, out: TraceWriter, models: set[str]) -> None:
    data = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser() / "opencode"
    db = data / "opencode.db"
    if not db.is_file():
        return
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    start_ms = int(start.timestamp() * 1000)
    sessions = con.execute(
        "SELECT * FROM session WHERE directory = ? AND time_updated >= ? ORDER BY time_created",
        (str(workspace), start_ms),
    ).fetchall()
    for session in sessions:
        row = dict(session)
        try:
            model = json.loads(row.get("model") or "null")
            if isinstance(model, dict) and model.get("id"):
                models.add(f"{model.get('providerID', '')}/{model['id']}".strip("/"))
        except (ValueError, TypeError):  # not JSON: the row is still written (or replaced by a placeholder)
            pass
        out.write("opencode.db/session", row)
        messages = con.execute(
            "SELECT * FROM message WHERE session_id = ? AND time_created >= ? ORDER BY time_created",
            (row["id"], start_ms),
        ).fetchall()
        for message in messages:
            parts = con.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created, id", (message["id"],)
            ).fetchall()
            try:
                info = json.loads(message["data"])
                record = {
                    "session_id": row["id"],
                    "parent_session_id": row.get("parent_id"),
                    "agent": row.get("agent"),
                    "time_created": message["time_created"],
                    "message": info,
                    "parts": [json.loads(p["data"]) for p in parts],
                }
            except (ValueError, TypeError) as exc:  # data that is not JSON
                out.omit("opencode.db/message", type(exc).__name__)
                continue
            if isinstance(info, dict):
                models_in({"modelID": info.get("modelID")}, models)
            out.write("opencode.db/message", record)
    con.close()


def export(harness: str, workspace: Path, since: str, out_dir: Path, secrets=()) -> dict:
    """Write out_dir/trace.jsonl, with secrets replaced by markers.

    `secrets` are values to remove besides the recognised formats and the environment's tokens (the Hub
    token the scripts use). Returns {records, omitted, models, tokens, redactions, note}: `omitted` is the
    number of records replaced by a placeholder, `tokens` maps each model to its token counts, and
    `redactions` each kind of secret removed to the number of replacements. If reading the harness's record
    stops with an error, the records written so far are kept and the note says the trace is incomplete.
    """
    start = parse_time(since) - MARGIN
    workspace = workspace.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    models: set[str] = set()
    notes = []
    with (out_dir / "trace.jsonl").open("w", encoding="utf-8") as out:
        writer = TraceWriter(out, harness, secrets)
        try:
            if harness == "opencode":
                export_opencode(workspace, start, writer, models)
            elif harness in ("claude", "codex", "pi"):
                finder = {"claude": claude_files, "codex": codex_files, "pi": pi_files}[harness]
                export_jsonl_files(finder(workspace, start), start, writer, models)
                if harness in ("codex", "pi"):
                    notes.append(f"best-effort {harness} export: raw records of the session files found for "
                                 "this folder")
            else:
                notes.append(f"no exporter for harness {harness!r}")
        except Exception as exc:  # noqa: BLE001 - keep what was written; the note says what is missing
            notes.append(f"the export stopped with an error ({type(exc).__name__}: {exc}), so the trace is "
                         f"incomplete: it holds only the {writer.records} records written before it")
    if writer.records == 0 and not notes:
        notes.append(f"no {harness} records found for {workspace} since {start.isoformat()}")
    if writer.omitted:
        notes.append(f"{writer.omitted} records could not be written and were replaced by a placeholder")
    return {"records": writer.records, "omitted": writer.omitted, "models": sorted(models),
            "tokens": writer.usage.result(), "redactions": dict(sorted(writer.redactor.counts.items())),
            "note": "; ".join(notes)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--harness", required=True, choices=["claude", "codex", "opencode", "pi"])
    parser.add_argument("--since", required=True, help="ISO time the session started")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = export(args.harness, args.workspace, args.since, args.out)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
