# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "huggingface_hub>=1.0"]
# ///
"""Record the promotion of a claim to established.

Writes a small record in feedback/ naming the card, who promoted it and when,
after checking what a script can check: in shared mode the author is a lead;
the claim is neither refuted nor revised; and it has a supporting artefact with
a confirming review, or a human verification. Whether the evidence is robust
enough is the judgment of the person promoting.

Shared mode: run by a lead. The record is committed to main on the Hub
directly (checked against the latest main), never inside a session.
Local mode: run by the coordinator (--by-agent, after asking the operator or,
under /autoresearch, after logging the decision) or by the operator.

Usage: uv run .physics-intern/scripts/promote.py <card id> [--reason TEXT] [--by-agent]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import Workspace, dump_front_matter, find_root, promotion_problems, utc_stamp  # noqa: E402
from common import ScriptError, git, load_active, now_iso, operator_name, say  # noqa: E402


def promotion_record(card_id: str, by: dict, session: str | None, reason: str) -> tuple[str, str]:
    """Return (path, content) of a promotion record."""
    who = by.get("user") or "agent"
    path = f"feedback/promotion-{card_id}-{who}-{utc_stamp()}.md"
    meta = {"kind": "promotion", "target": card_id, "by": by, "date": now_iso(), "session": session}
    return path, dump_front_matter(meta, (reason.strip() + "\n") if reason.strip() else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("card")
    parser.add_argument("--reason", default="", help="the evidence that justifies the promotion")
    parser.add_argument("--by-agent", action="store_true", help="local mode: the coordinator records the promotion")
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.root.resolve() if args.root else find_root()
    ws = Workspace(root)

    if ws.mode == "shared":
        if args.by_agent:
            raise ScriptError("in shared mode only a lead promotes; propose the promotion in the session report")
        import hub

        hub.promote_shared(root, args.card, args.reason, promotion_record)
        return 0

    active = load_active(root) or {}
    if args.by_agent:
        by = {"kind": "agent", "model": active.get("model", "unknown"), "operator": active.get("operator", operator_name(root))}
    else:
        by = {"kind": "human", "user": operator_name(root)}
    reasons = promotion_problems(ws, args.card, by)
    if reasons:
        raise ScriptError(f"promotion of {args.card} refused: " + "; ".join(reasons))
    path, content = promotion_record(args.card, by, active.get("id"), args.reason)
    (root / path).write_text(content, encoding="utf-8")
    if active:
        say(f"Wrote {path}. Commit it with the current integration step.")
    else:
        git(root, "add", "--", path)
        git(root, "commit", "-q", "-m", f"Promote {args.card}")
        say(f"Wrote and committed {path}.")
    from regen import regenerate

    regenerate(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
