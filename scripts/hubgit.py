# /// script
# requires-python = ">=3.11"
# dependencies = ["huggingface_hub>=1.0"]
# ///
"""Run a git command against the Hub with your Hugging Face token.

The workspace repository is private, so `git pull` and `git push` need
credentials. This passes the token of `hf auth login` in an HTTP header for
this one command, without storing it. It is for git commands a person runs by
hand; to publish the lead's edits, `session.py save` is simpler (it
commits them as theirs and pushes them to main).

Usage: uv run .physics-hive/scripts/hubgit.py <git arguments>
  e.g. uv run .physics-hive/scripts/hubgit.py pull origin main
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import run_main  # noqa: E402
from hub import git_env  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    return subprocess.call(["git", *sys.argv[1:]], env={**os.environ, **git_env()})


if __name__ == "__main__":
    raise SystemExit(run_main(main))
