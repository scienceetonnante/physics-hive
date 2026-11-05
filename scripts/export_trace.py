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
it. It returns the models it found in the record.

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
from pathlib import Path

MARGIN = dt.timedelta(minutes=5)


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


def export_jsonl_files(files: list[Path], start: dt.datetime, out, models: set[str]) -> int:
    count = 0
    for path in files:
        for record in jsonl_lines(path):
            when = record_time(record)
            if when is not None and when < start:
                continue
            models_in(record, models)
            out.write(json.dumps({"source": str(path), "record": record}, ensure_ascii=False) + "\n")
            count += 1
    return count


def export_opencode(workspace: Path, start: dt.datetime, out, models: set[str]) -> int:
    data = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser() / "opencode"
    db = data / "opencode.db"
    if not db.is_file():
        return 0
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    start_ms = int(start.timestamp() * 1000)
    sessions = con.execute(
        "SELECT * FROM session WHERE directory = ? AND time_updated >= ? ORDER BY time_created",
        (str(workspace), start_ms),
    ).fetchall()
    count = 0
    for session in sessions:
        row = dict(session)
        try:
            model = json.loads(row.get("model") or "null")
            if isinstance(model, dict) and model.get("id"):
                models.add(f"{model.get('providerID', '')}/{model['id']}".strip("/"))
        except json.JSONDecodeError:
            pass
        out.write(json.dumps({"source": "opencode.db/session", "record": row}, ensure_ascii=False) + "\n")
        count += 1
        messages = con.execute(
            "SELECT * FROM message WHERE session_id = ? AND time_created >= ? ORDER BY time_created",
            (row["id"], start_ms),
        ).fetchall()
        for message in messages:
            info = json.loads(message["data"])
            models_in({"modelID": info.get("modelID")}, models)
            parts = con.execute(
                "SELECT data FROM part WHERE message_id = ? ORDER BY time_created, id", (message["id"],)
            ).fetchall()
            record = {
                "session_id": row["id"],
                "parent_session_id": row.get("parent_id"),
                "agent": row.get("agent"),
                "time_created": message["time_created"],
                "message": info,
                "parts": [json.loads(p["data"]) for p in parts],
            }
            out.write(json.dumps({"source": "opencode.db/message", "record": record}, ensure_ascii=False) + "\n")
            count += 1
    con.close()
    return count


def export(harness: str, workspace: Path, since: str, out_dir: Path) -> dict:
    """Write out_dir/trace.jsonl. Returns {records, models, note}."""
    start = parse_time(since) - MARGIN
    workspace = workspace.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    models: set[str] = set()
    note = ""
    with (out_dir / "trace.jsonl").open("w", encoding="utf-8") as out:
        if harness == "opencode":
            records = export_opencode(workspace, start, out, models)
        elif harness in ("claude", "codex", "pi"):
            finder = {"claude": claude_files, "codex": codex_files, "pi": pi_files}[harness]
            records = export_jsonl_files(finder(workspace, start), start, out, models)
            if harness in ("codex", "pi"):
                note = f"best-effort {harness} export: raw records of the session files found for this folder"
        else:
            records = 0
            note = f"no exporter for harness {harness!r}"
    if records == 0 and not note:
        note = f"no {harness} records found for {workspace} since {start.isoformat()}"
    return {"records": records, "models": sorted(models), "note": note}


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
