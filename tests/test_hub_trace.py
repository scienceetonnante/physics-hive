"""The trace that `session.py end` uploads to the traces dataset: its meta.json records the token counts and
the number of secrets replaced, and no uploaded file (trace.jsonl or meta.json) holds the planted secrets,
the Hub token included."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import hub

SINCE = "2026-10-05T11:33:20Z"
# The Hub token of the scripts, in no known format and in no environment variable: only the value that
# end_session passes to the export (secrets=[get_token()]) lets it be found.
HUB_TOKEN = "scripts-own-hub-credential-" + "x9" * 6
OTHER = "sk-" + "ant-" + "api03-" + "Zq9_" * 10  # assembled at run time: this file holds no token-shaped string


class FakeHub:
    uploaded: list = []  # {path in the folder: text} of each upload_folder call

    def get_discussion_details(self, repo_id, number, repo_type=None):
        return SimpleNamespace(status="open")

    def upload_folder(self, repo_id, folder_path, **kwargs):
        FakeHub.uploaded.append({p.name: p.read_text() for p in Path(folder_path).rglob("*") if p.is_file()})

    def merge_pull_request(self, *args, **kwargs):
        pass


COMMITS = f"aaa111 [S3] derive the period\nbbb222 [S3] fix the login with {HUB_TOKEN} and {OTHER}\n"


@pytest.fixture
def ending(shared_toy, monkeypatch):
    """end_session with every Hub and git operation faked; the session made the two COMMITS."""
    root = shared_toy.root
    (root / ".physics-hive").mkdir()
    (root / ".physics-hive" / "VERSION").write_text("test\n")
    FakeHub.uploaded = []
    monkeypatch.delenv("HF_TOKEN", raising=False)
    for name, value in (("api", lambda: FakeHub()), ("get_token", lambda: HUB_TOKEN), ("git_env", lambda: {}),
                        ("git", lambda *a, **k: None),
                        ("git_out", lambda root, *a: COMMITS if a[0] == "log" else "abc123"),
                        ("fetch", lambda *a: None), ("rebase_on_main", lambda *a: False),
                        ("push_pr", lambda *a: None), ("sync_sources_up", lambda *a: None)):
        monkeypatch.setattr(hub, name, value)
    return root


def end(root: Path, harness: str = "claude") -> None:
    active = {"pr": 3, "id": "S3", "harness": harness, "model": "opus", "operator": "me", "started": SINCE,
              "pr_url": "https://hf.co/x/discussions/3", "branch": "session/S3"}
    hub.end_session(root, active, True, lambda *args: None)


def test_the_uploaded_trace_holds_no_secret_and_meta_counts_them(ending, tmp_path, monkeypatch):
    folder = tmp_path / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(ending.resolve()))
    folder.mkdir(parents=True)
    records = [
        {"type": "user", "timestamp": "2026-10-05T11:40:00Z",
         "message": {"content": [{"type": "tool_result", "content": f"login {HUB_TOKEN}\nKEY={OTHER}"}]}},
        {"type": "assistant", "timestamp": "2026-10-05T11:41:00Z",
         "message": {"id": "m1", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "done"}],
                     "usage": {"input_tokens": 5, "output_tokens": 9, "cache_read_input_tokens": 70,
                               "cache_creation_input_tokens": 30}}},
    ]
    (folder / "abc.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    end(ending)

    first, last = FakeHub.uploaded  # uploaded before the merge, then again with the merge commit
    for files in (first, last):
        assert set(files) == {"trace.jsonl", "meta.json"}
        for name, text in files.items():
            assert HUB_TOKEN not in text and OTHER not in text, name
    meta = json.loads(last["meta.json"])
    # One of each in the trace, one of each in a commit subject of meta.json.
    assert meta["trace_redactions_by_kind"] == {"anthropic-key": 2, "hub-token": 2}
    assert meta["trace_redactions"] == 4
    assert meta["commits"] == [
        {"sha": "aaa111", "subject": "[S3] derive the period"},
        {"sha": "bbb222", "subject": "[S3] fix the login with [REDACTED:hub-token] and [REDACTED:anthropic-key]"}]
    assert meta["tokens_by_model"] == {"claude-opus-5-5": {"input": 5, "cache_read": 70, "cache_write": 30, "output": 9}}
    assert meta["models_in_trace"] == ["claude-opus-5-5"] and meta["merge_commit"] == "abc123"
    assert meta["trace_records"] == 2 and meta["trace_records_omitted"] == 0


def test_a_failed_export_says_the_trace_is_missing_and_the_session_still_ends(ending, monkeypatch):
    import export_trace

    def broken(*args, **kwargs):
        raise OSError(f"cannot open the record of {OTHER}")

    monkeypatch.setattr(export_trace, "export", broken)
    end(ending, harness="opencode")
    meta = json.loads(FakeHub.uploaded[-1]["meta.json"])
    assert meta["trace_records"] == 0 and meta["merge_commit"] == "abc123"
    assert meta["trace_note"].startswith("the trace of this session is missing: the export failed (OSError")
    assert OTHER not in FakeHub.uploaded[-1]["meta.json"]  # the note is cleaned like the rest
    assert meta["tokens_by_model"] == {}
