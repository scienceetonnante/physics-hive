"""Helpers shared by the workspace scripts: git calls and the active-session file.

The active session of a checkout is recorded in `.active-session` (JSON,
git-ignored) at the workspace root, so that it survives a context clear and
stays private to the checkout.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ACTIVE_SESSION = ".active-session"


class ScriptError(SystemExit):
    """A failure the script reports to its caller and stops on."""

    def __init__(self, message: str):
        super().__init__(f"ERROR: {message}")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git(root: Path, *args: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run git in `root`. Raises ScriptError with git's message on failure when `check`."""
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        env={**os.environ, **(env or {}), "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise ScriptError(f"git {' '.join(args)} failed: {message}")
    return proc


def git_out(root: Path, *args: str, env: dict | None = None) -> str:
    return git(root, *args, env=env).stdout.strip()


def is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def dirty_paths(root: Path) -> list[str]:
    """Uncommitted changes, including untracked files that are not git-ignored."""
    out = git(root, "status", "--porcelain", "--untracked-files=all").stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def changes_since(root: Path, base: str) -> list[tuple[str, str]]:
    """(status, path) for every file changed between `base` and the working tree.

    Status is A (added), M (modified) or D (deleted). Untracked files count as added.
    """
    changes = []
    out = git(root, "diff", "--name-status", "--no-renames", base, "--").stdout
    for line in out.splitlines():
        if not line.strip():
            continue
        status, path = line.split("\t", 1)
        changes.append((status[0], path))
    untracked = git(root, "ls-files", "--others", "--exclude-standard").stdout
    changes.extend(("A", path) for path in untracked.splitlines() if path.strip())
    return changes


def session_paths(root: Path, base: str, session: str) -> set[str]:
    """Files changed by the session itself since `base`: its `[S<n>]` commits and uncommitted changes.

    In local mode the researcher may commit edits on the same branch while a session runs; those are
    theirs, not the session's.
    """
    out = git(root, "log", "--no-renames", "--name-only", "--format=\x1e%s", f"{base}..HEAD", check=False).stdout
    paths: set[str] = set()
    for chunk in out.split("\x1e")[1:]:
        subject, _, names = chunk.partition("\n")
        if subject.startswith(f"[{session}]"):
            paths |= {n.strip() for n in names.splitlines() if n.strip()}
    paths |= set(dirty_paths(root))
    return paths


def load_active(root: Path) -> dict | None:
    path = root / ACTIVE_SESSION
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_active(root: Path, info: dict) -> None:
    (root / ACTIVE_SESSION).write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


def clear_active(root: Path) -> None:
    (root / ACTIVE_SESSION).unlink(missing_ok=True)


def detect_harness() -> str:
    """Best guess of the harness running this script, from its environment."""
    env = os.environ
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if env.get("OPENCODE") or any(k.startswith("OPENCODE_") for k in env):
        return "opencode"
    if any(k.startswith("CODEX_") for k in env):
        return "codex"
    if any(k.startswith("PI_") for k in env):
        return "pi"
    return "unknown"


def operator_name(root: Path) -> str:
    """Local-mode operator: the git user name, else the login name."""
    if shutil.which("git") and is_git_repo(root):
        name = git(root, "config", "user.name", check=False).stdout.strip()
        if name:
            return name
    return os.environ.get("USER", "unknown")


RENDER_MARKS = {"claude": ".claude/agents", "codex": ".codex/agents", "opencode": ".opencode/agents", "pi": ".pi/agents"}


def rendered_harnesses(root: Path) -> list[str]:
    """Harnesses whose files are rendered in this checkout."""
    return [name for name, folder in RENDER_MARKS.items() if (root / folder).is_dir()]


def rendered_version(root: Path) -> str | None:
    """Method version the harness files were rendered from (stamp at the top of AGENTS.md)."""
    doc = root / "AGENTS.md"
    if not doc.is_file():
        return None
    match = re.search(r"Rendered from the PhysicsHive method (\S+) in", doc.read_text(encoding="utf-8")[:300])
    return match.group(1) if match else None


def rerender(root: Path, harnesses: list[str] | None = None) -> None:
    """Render the harness files again from the workspace's method copy."""
    harnesses = harnesses or rendered_harnesses(root)
    if not harnesses:
        return
    renderer = root / ".physics-hive" / "commons" / "render.py"
    proc = subprocess.run([sys.executable, str(renderer), f"--hosts={','.join(harnesses)}", f"--target={root}"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise ScriptError(f"rendering the harness files failed:\n{proc.stderr.strip()}")


def say(message: str = "") -> None:
    print(message, flush=True)


def warn(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
