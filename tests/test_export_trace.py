"""Tests of the trace exporter on fake OpenCode and Claude Code records."""

from __future__ import annotations

import json
import re
import sqlite3

from export_trace import export

SCHEMA = """
CREATE TABLE session (id text PRIMARY KEY, parent_id text, directory text NOT NULL, agent text, model text,
                      time_created integer NOT NULL, time_updated integer NOT NULL);
CREATE TABLE message (id text PRIMARY KEY, session_id text NOT NULL, time_created integer NOT NULL, data text NOT NULL);
CREATE TABLE part (id text PRIMARY KEY, message_id text NOT NULL, session_id text NOT NULL,
                   time_created integer NOT NULL, data text NOT NULL);
"""
T0 = 1_791_200_000_000  # milliseconds, the session start used below
SINCE = "2026-10-05T11:33:20Z"  # = T0


def test_opencode_export_keeps_the_window_and_the_models(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    data = tmp_path / "data"
    (data / "opencode").mkdir(parents=True)
    con = sqlite3.connect(data / "opencode" / "opencode.db")
    con.executescript(SCHEMA)
    model = json.dumps({"id": "Kimi-K2", "providerID": "huggingface"})
    con.execute("INSERT INTO session VALUES ('main', NULL, ?, 'build', ?, ?, ?)", (str(ws), model, T0 - 3_600_000, T0 + 60_000))
    con.execute("INSERT INTO session VALUES ('sub', 'main', ?, 'deriver', ?, ?, ?)", (str(ws), model, T0 + 10_000, T0 + 50_000))
    con.execute("INSERT INTO session VALUES ('other', NULL, '/elsewhere', 'build', ?, ?, ?)", (model, T0, T0 + 1))
    # An old message (before the window) and two in the window.
    con.execute("INSERT INTO message VALUES ('m0', 'main', ?, ?)", (T0 - 3_000_000, json.dumps({"role": "user"})))
    con.execute("INSERT INTO message VALUES ('m1', 'main', ?, ?)", (T0 + 1_000, json.dumps({"role": "assistant", "modelID": "Kimi-K2"})))
    con.execute("INSERT INTO message VALUES ('m2', 'sub', ?, ?)", (T0 + 20_000, json.dumps({"role": "assistant"})))
    con.execute("INSERT INTO part VALUES ('p1', 'm1', 'main', ?, ?)", (T0 + 1_000, json.dumps({"type": "reasoning", "text": "think"})))
    con.execute("INSERT INTO part VALUES ('p2', 'm2', 'sub', ?, ?)", (T0 + 20_000, json.dumps({"type": "text", "text": "## Summary"})))
    con.commit()
    con.close()
    monkeypatch.setenv("XDG_DATA_HOME", str(data))

    result = export("opencode", ws, SINCE, tmp_path / "out")
    lines = [json.loads(l) for l in (tmp_path / "out" / "trace.jsonl").read_text().splitlines()]
    sessions = [l["record"]["id"] for l in lines if l["source"].endswith("/session")]
    messages = [l["record"]["message"] for l in lines if l["source"].endswith("/message")]
    assert sessions == ["main", "sub"]
    assert len(messages) == 2  # the message from an hour earlier is outside the window
    parts = [p for l in lines if l["source"].endswith("/message") for p in l["record"]["parts"]]
    assert {"type": "reasoning", "text": "think"} in parts
    assert result["models"] == ["Kimi-K2", "huggingface/Kimi-K2"]
    assert result["note"] == ""


def test_claude_export_reads_main_and_subagent_files(tmp_path, monkeypatch):
    ws = tmp_path / "my.ws"
    ws.mkdir()
    config = tmp_path / "claude"
    folder = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(ws.resolve()))
    (folder / "abc" / "subagents").mkdir(parents=True)
    early = {"type": "user", "timestamp": "2026-10-05T10:00:00Z", "message": {"content": "old"}}
    main = {"type": "assistant", "timestamp": "2026-10-05T11:40:00Z", "message": {"model": "claude-opus-5-5"}}
    sub = {"type": "assistant", "timestamp": "2026-10-05T11:45:00Z", "message": {"model": "claude-sonnet-5-5"}}
    (folder / "abc.jsonl").write_text(json.dumps(early) + "\n" + json.dumps(main) + "\n")
    (folder / "abc" / "subagents" / "agent-1.jsonl").write_text(json.dumps(sub) + "\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    result = export("claude", ws, SINCE, tmp_path / "out")
    assert result["records"] == 2
    assert result["models"] == ["claude-opus-5-5", "claude-sonnet-5-5"]


def test_missing_records_are_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "none"))
    result = export("opencode", tmp_path, SINCE, tmp_path / "out")
    assert result["records"] == 0 and "no opencode records" in result["note"]
