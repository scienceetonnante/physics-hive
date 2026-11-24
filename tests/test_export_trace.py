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
    assert result["tokens"] == {} and result["redactions"] == {}


# ----- secrets -----

# Fake secrets of each kind, assembled at run time so that this file holds no string shaped like a token.
PLANTED = {
    "huggingface-token": "hf_" + "Ab3x" * 9,
    "anthropic-key": "sk-ant-" + "api03-" + "Zq9_" * 10,
    "openai-key": "sk-" + "proj-" + "Xy7-" * 10,
    "github-token": "gh" + "p_" + "R2d2" * 9,
    "aws-access-key": "AK" + "IA" + "QWERTYUIOP123456",
    "jwt": "ey" + "JhbGciOiJIUzI1NiJ9" + ".ey" + "JzdWIiOiIxMjM0In0" + ".dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk",
}
KEY_BODY = "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAAB"
PRIVATE_KEY = "-----BEGIN " + f"OPENSSH PRIVATE KEY-----\n{KEY_BODY}\n{KEY_BODY}\n-----END OPENSSH PRIVATE KEY-----"
SIGNATURE = "0f1e2d3c4b5a69788796a5b4c3d2e1f0" * 2
SIGNED_URL = f"https://bucket.s3.amazonaws.com/a.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature={SIGNATURE}"
BASIC = "bWU6c2VjcmV0LWNyZWRlbnRpYWxzLWhlcmU="
ENV_SECRET = "plain-service-credential-42"
HUB_SECRET = "the-token-the-scripts-use-77"


def claude_folder(tmp_path, monkeypatch, ws):
    config = tmp_path / "claude"
    folder = config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(ws.resolve()))
    (folder / "abc" / "subagents").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return folder


def tool_result(text: str, when: str = "2026-10-05T11:40:00Z") -> dict:
    return {"type": "user", "timestamp": when,
            "message": {"role": "user", "content": [{"type": "tool_result", "content": text}]}}


def test_secrets_of_every_kind_are_replaced_in_every_output_file(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    folder = claude_folder(tmp_path, monkeypatch, ws)
    monkeypatch.setenv("MY_SERVICE_TOKEN", ENV_SECRET)
    environment = "\n".join(f"VAR_{i}={value}" for i, value in enumerate(PLANTED.values()))
    main = [
        tool_result(f"$ env\n{environment}\nMY_SERVICE_TOKEN={ENV_SECRET}\n"),
        tool_result(f'{{"config": {{"key": "{PLANTED["huggingface-token"]}"}}}}\n{PRIVATE_KEY}\n'),
        tool_result(f"curl -o a.pdf '{SIGNED_URL}'\nAuthorization: Basic {BASIC}\nlogin {HUB_SECRET}"),
    ]
    (folder / "abc.jsonl").write_text("".join(json.dumps(r) + "\n" for r in main))
    sub = tool_result(f"cat ~/.cache/huggingface/token\n{PLANTED['huggingface-token']}")
    (folder / "abc" / "subagents" / "agent-1.jsonl").write_text(json.dumps(sub) + "\n")

    out = tmp_path / "out"
    result = export("claude", ws, SINCE, out, secrets=[HUB_SECRET])
    secrets = [*PLANTED.values(), KEY_BODY, SIGNATURE, BASIC, ENV_SECRET, HUB_SECRET]
    for path in out.rglob("*"):
        if path.is_file():
            text = path.read_text()
            assert [s for s in secrets if s in text] == [], path
    text = (out / "trace.jsonl").read_text()
    lines = [json.loads(line) for line in text.splitlines()]  # still valid JSON
    assert len(lines) == result["records"] == 4
    for kind in [*PLANTED, "private-key", "signed-url", "authorization-header", "env:MY_SERVICE_TOKEN", "hub-token"]:
        assert f"[REDACTED:{kind}]" in text, kind
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in text and "Authorization: Basic [REDACTED" in text
    assert result["redactions"]["huggingface-token"] == 3 and sum(result["redactions"].values()) == 13


def test_a_private_key_is_removed_whether_its_line_breaks_are_real_or_escaped(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    folder = claude_folder(tmp_path, monkeypatch, ws)
    crlf = PRIVATE_KEY.replace("\n", "\r\n")
    escaped = PRIVATE_KEY.replace("\n", "\\n")  # as printed from a JSON file or a .env file
    service_account = json.dumps({"type": "service_account", "private_key": PRIVATE_KEY + "\n", "client_id": "1"})
    texts = [
        crlf,
        escaped,
        crlf.replace("\r\n", "\\r\\n"),
        f'PRIVATE_KEY="{escaped}"',
        service_account,  # a JSON string inside the record: its line breaks are escaped once
        json.dumps({"stdout": service_account}),  # and twice
        PRIVATE_KEY.split("-----END")[0],  # cut before its END line
    ]
    (folder / "abc.jsonl").write_text("".join(json.dumps(tool_result(t)) + "\n" for t in texts))
    result = export("claude", ws, SINCE, tmp_path / "out")
    text = (tmp_path / "out" / "trace.jsonl").read_text()
    assert KEY_BODY not in text and "PRIVATE KEY" not in text.replace("[REDACTED:private-key]", "")
    assert result["redactions"] == {"private-key": len(texts)}
    lines = [json.loads(line)["record"]["message"]["content"][0]["content"] for line in text.splitlines()]
    assert json.loads(lines[4]) == {"type": "service_account", "private_key": "[REDACTED:private-key]\n",
                                    "client_id": "1"}  # the JSON around the key is intact


def test_a_record_that_cannot_be_written_is_replaced_by_a_placeholder(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    folder = claude_folder(tmp_path, monkeypatch, ws)
    cut = "a tool output cut in the middle of an emoji \ud83d"  # a lone surrogate, as JavaScript truncation leaves
    lines = [json.dumps(tool_result("before")), json.dumps(tool_result(cut)), json.dumps(tool_result("after"))]
    (folder / "abc.jsonl").write_text("\n".join(lines) + "\n")
    data = tmp_path / "data"
    (data / "opencode").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(data))

    result = export("claude", ws, SINCE, tmp_path / "out")
    written = [json.loads(line)["record"] for line in (tmp_path / "out" / "trace.jsonl").read_text().splitlines()]
    assert [r["message"]["content"][0]["content"] for r in written] == ["before", cut, "after"]  # kept, escaped
    assert result["records"] == 3 and result["omitted"] == 0 and result["note"] == ""

    # An OpenCode session whose row holds bytes (not JSON), and a message whose data is not JSON.
    con = sqlite3.connect(data / "opencode" / "opencode.db")
    con.executescript(SCHEMA)
    con.execute("INSERT INTO session VALUES ('main', NULL, ?, 'build', NULL, ?, ?)", (str(ws), b"\x00\xff", T0 + 60_000))
    con.execute("INSERT INTO message VALUES ('m1', 'main', ?, ?)", (T0 + 1_000, "{not json"))
    con.execute("INSERT INTO message VALUES ('m2', 'main', ?, ?)", (T0 + 2_000, json.dumps({"role": "assistant"})))
    con.commit()
    con.close()
    result = export("opencode", ws, SINCE, tmp_path / "out2")
    written = [json.loads(line) for line in (tmp_path / "out2" / "trace.jsonl").read_text().splitlines()]
    assert written[0] == {"source": "opencode.db/session",
                          "record": {"omitted": "this record could not be written to the trace (TypeError)"}}
    assert written[1]["record"] == {"omitted": "this record could not be written to the trace (JSONDecodeError)"}
    assert written[2]["record"]["message"] == {"role": "assistant"}
    assert result["records"] == 3 and result["omitted"] == 2
    assert "2 records could not be written and were replaced by a placeholder" in result["note"]


def test_an_error_while_reading_keeps_the_records_written_before_it(tmp_path, monkeypatch):
    import export_trace

    ws = tmp_path / "ws"
    ws.mkdir()
    folder = claude_folder(tmp_path, monkeypatch, ws)
    (folder / "abc.jsonl").write_text(json.dumps(tool_result("first")) + "\n")
    (folder / "abd.jsonl").write_text(json.dumps(tool_result("second")) + "\n")
    real = export_trace.jsonl_lines

    def failing(path):
        if path.name == "abd.jsonl":
            raise OSError("the file vanished")
        yield from real(path)

    monkeypatch.setattr(export_trace, "jsonl_lines", failing)
    result = export("claude", ws, SINCE, tmp_path / "out")
    assert result["records"] == 1 and "the trace is incomplete" in result["note"] and "OSError" in result["note"]
    assert len((tmp_path / "out" / "trace.jsonl").read_text().splitlines()) == 1


def test_ordinary_content_is_unchanged(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    folder = claude_folder(tmp_path, monkeypatch, ws)
    monkeypatch.setenv("SHORT_KEY", "1")  # too short to search for
    monkeypatch.setenv("SSH_KEY_PATH", str(tmp_path))  # a path, not a secret
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "http.https://huggingface.co/.extraHeader")  # a setting's name
    ordinary = [
        "commit 9fceb02d0ae598e95dc970b74767f19372d61af8 (HEAD -> main)",
        f"wrote {tmp_path}/notes.md with key=1 and http.https://huggingface.co/.extraHeader",
        "from huggingface_hub import hf_hub_download; import sklearn  # sk-learn, task-1",
        "https://arxiv.org/abs/2401.00001?context=hep-th&page=2 and AKIA is a prefix",
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
        "a.b.c and eyJ alone, Authorization: Bearer $HF_TOKEN",
    ]
    records = [tool_result(text) for text in ordinary]
    (folder / "abc.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    result = export("claude", ws, SINCE, tmp_path / "out")
    lines = [json.loads(line) for line in (tmp_path / "out" / "trace.jsonl").read_text().splitlines()]
    assert [line["record"] for line in lines] == records
    assert result["redactions"] == {}


# ----- token counts -----


def test_claude_tokens_are_counted_once_per_message(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    folder = claude_folder(tmp_path, monkeypatch, ws)
    usage = {"input_tokens": 3, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 50}

    def block(msg_id, model, when="2026-10-05T11:40:00Z", **counts):
        return {"type": "assistant", "timestamp": when,
                "message": {"id": msg_id, "model": model, "usage": {**usage, **counts}}}

    main = [block("m0", "claude-opus-5-5", when="2026-10-05T10:00:00Z"),  # before the window
            block("m1", "claude-opus-5-5"), block("m1", "claude-opus-5-5"),  # two content blocks of one message
            block("m2", "claude-opus-5-5", output_tokens=7),
            {"type": "assistant", "timestamp": "2026-10-05T11:41:00Z", "message": {"usage": "unexpected"}}]
    (folder / "abc.jsonl").write_text("".join(json.dumps(r) + "\n" for r in main))
    (folder / "abc" / "subagents" / "agent-1.jsonl").write_text(json.dumps(block("s1", "claude-sonnet-5-5")) + "\n")
    result = export("claude", ws, SINCE, tmp_path / "out")
    assert result["tokens"] == {
        "claude-opus-5-5": {"input": 6, "cache_read": 2000, "cache_write": 200, "output": 57},
        "claude-sonnet-5-5": {"input": 3, "cache_read": 1000, "cache_write": 100, "output": 50},
    }


def test_opencode_tokens_include_reasoning_in_the_output(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    data = tmp_path / "data"
    (data / "opencode").mkdir(parents=True)
    con = sqlite3.connect(data / "opencode" / "opencode.db")
    con.executescript(SCHEMA)
    con.execute("INSERT INTO session VALUES ('main', NULL, ?, 'build', NULL, ?, ?)", (str(ws), T0, T0 + 60_000))
    tokens = {"total": 1600, "input": 100, "output": 30, "reasoning": 20, "cache": {"read": 1400, "write": 50}}
    for i, when in enumerate((T0 - 3_000_000, T0 + 1_000, T0 + 2_000)):  # the first is before the window
        info = {"role": "assistant", "modelID": "GLM-5", "providerID": "huggingface", "tokens": tokens}
        con.execute("INSERT INTO message VALUES (?, 'main', ?, ?)", (f"m{i}", when, json.dumps(info)))
    con.commit()
    con.close()
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    result = export("opencode", ws, SINCE, tmp_path / "out")
    assert result["tokens"] == {"GLM-5": {"input": 200, "cache_read": 2800, "cache_write": 100, "output": 100}}


def test_codex_tokens_are_the_differences_of_its_running_totals(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "codex"
    (home / "sessions" / "2026" / "10" / "05").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(home))

    def total(n):  # the running total after n calls of 100 input tokens (60 cached) and 10 output tokens
        counts = {"input_tokens": 100 * n, "cached_input_tokens": 60 * n, "output_tokens": 10 * n,
                  "reasoning_output_tokens": 4 * n, "total_tokens": 110 * n}
        return {"type": "token_count", "info": {"total_token_usage": counts}}

    records = [
        {"timestamp": "2026-10-05T10:00:00Z", "type": "session_meta", "payload": {"cwd": str(ws.resolve())}},
        {"timestamp": "2026-10-05T10:00:01Z", "type": "turn_context", "payload": {"model": "gpt-a"}},
        {"timestamp": "2026-10-05T10:00:02Z", "type": "event_msg", "payload": total(1)},  # before the window
        {"timestamp": "2026-10-05T11:40:00Z", "type": "turn_context", "payload": {"model": "gpt-b"}},
        {"timestamp": "2026-10-05T11:40:01Z", "type": "event_msg", "payload": total(2)},
        {"timestamp": "2026-10-05T11:40:02Z", "type": "event_msg", "payload": total(2)},  # written twice
        {"timestamp": "2026-10-05T11:40:03Z", "type": "event_msg", "payload": total(4)},
        {"timestamp": "2026-10-05T11:40:04Z", "type": "event_msg", "payload": {"type": "token_count", "info": None}},
    ]
    path = home / "sessions" / "2026" / "10" / "05" / "rollout-x.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    result = export("codex", ws, SINCE, tmp_path / "out")
    assert result["tokens"] == {"gpt-b": {"input": 120, "cache_read": 180, "cache_write": 0, "output": 30}}


def test_pi_tokens_are_read_from_its_assistant_messages(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    encoded = "--" + re.sub(r"[/\\]", "-", str(ws.resolve())).strip("-") + "--"
    folder = tmp_path / ".pi" / "agent" / "sessions" / encoded
    folder.mkdir(parents=True)
    message = {"type": "message", "timestamp": "2026-10-05T11:40:00Z",
               "message": {"role": "assistant", "provider": "huggingface", "model": "Kimi-K2",
                           "usage": {"input": 10, "output": 5, "cacheRead": 70, "cacheWrite": 0, "totalTokens": 85}}}
    user = {"type": "message", "timestamp": "2026-10-05T11:40:01Z", "message": {"role": "user", "content": "hi"}}
    (folder / "s.jsonl").write_text(json.dumps(message) + "\n" + json.dumps(message) + "\n" + json.dumps(user) + "\n")
    result = export("pi", ws, SINCE, tmp_path / "out")
    assert result["tokens"] == {"Kimi-K2": {"input": 20, "cache_read": 140, "cache_write": 0, "output": 10}}
