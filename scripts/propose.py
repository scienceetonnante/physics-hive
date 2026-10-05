# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "huggingface_hub>=1.0"]
# ///
"""Propose a new version of a lead's file as a pull request (shared mode).

The lead's files (problem.md, plan.md, conventions.md, literature/seeds.md)
change only by a lead's own commit or by a pull request that a lead merges,
edits or closes. This script opens such a pull request with the content of a
draft file, based on the current main; it touches only that one file.
/research-plan uses it for plan proposals.

Usage: uv run .physics-intern/scripts/propose.py plan.md --from sessions/S12/plan-proposal.md [--title TEXT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import LEAD_FILES, Workspace, find_root  # noqa: E402
from common import ScriptError, load_active, say  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="the lead's file to change, e.g. plan.md")
    parser.add_argument("--from", dest="source", required=True, help="file holding the proposed content")
    parser.add_argument("--title", help="pull request title")
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.root.resolve() if args.root else find_root()
    if args.path not in LEAD_FILES:
        raise ScriptError(f"{args.path} is not a lead's file ({', '.join(LEAD_FILES)})")
    if Workspace(root).mode != "shared":
        raise ScriptError("local mode has no pull requests; /research-plan writes plan.md directly")
    source = (root / args.source) if not Path(args.source).is_absolute() else Path(args.source)
    if not source.is_file():
        raise ScriptError(f"{args.source} does not exist")
    active = load_active(root) or {}
    session = active.get("id")
    title = args.title or (f"[{session}] Proposal: {args.path}" if session else f"Proposal: {args.path}")
    description = (f"Proposed by session {session} ({active.get('pr_url', '')}); the draft is {args.source}.\n\n"
                   if session else "") + "A lead merges, edits or closes this pull request."
    import hub

    number, url = hub.propose_file(root, args.path, source.read_bytes(), title, description)
    say(f"Opened pull request #{number} for {args.path}: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
