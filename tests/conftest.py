"""Fixtures for the workspace-script tests: a toy workspace written file by file."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


DRAFT_HEAD = "\\documentclass{article}\n\\begin{document}\n\\section{Results}\n"
DRAFT_TAIL = "\n\\end{document}\n"


def result(card_id: str, kind: str = "result") -> str:
    return f"\\begin{{{kind}}}[A title]\nStatement.\\footnote{{Evidence.}}\\card{{{card_id}}}\n\\end{{{kind}}}\n"


def conjecture(card_id: str) -> str:
    return result(card_id, "conjecture")


DEBRIEF = """Summary of what the session found.

Read the full note: `sessions/{s}/note.tex`.

#### Changed by this session

(Written by session.py end, from git.)

**Question 1.** Must the method use walks only?

> **Answer:**

**Question 2.** I assumed Dirichlet walls; no answer means you agree.

> **Answer:**

**Tick what you accept.** The next session applies the ticked lines.

- [ ] Set the approach in the project: correlation matrices.
- [ ] Next step: check the weights by sampling exit times.
- [ ] Copy Result 1 of note {s} into the draft, as a result.

#### Anything else for the next session

> **Note:**
"""


class ToyWorkspace:
    """A temporary workspace with helpers to add cards, artefacts and records."""

    def __init__(self, root: Path, shared: bool = False, leads: tuple[str, ...] = ("lead",)):
        self.root = root
        hub = '[hub]\nworkspace = "org/toy"\ntraces = "org/toy-traces"\n' if shared else "[hub]\n"
        people = f"[people]\nleads = {list(leads)!r}\n".replace("'", '"')
        (root / "project.toml").write_text(f'[method]\nphysics_intern_version = "test"\n\n{hub}\n{people}')
        for folder in ("claims", "derivations", "computations", "critiques", "literature", "sessions"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        (root / "project.md").write_text("# Toy question?\n\n## Goal\n\nAnswer it.\n\n## Next steps\n\n1. Derive X.\n")
        (root / "conventions.md").write_text("# Conventions\n")
        (root / "draft.tex").write_text(DRAFT_HEAD + DRAFT_TAIL)

    def write(self, rel: str, meta: dict, body: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        header = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
        path.write_text(f"---\n{header}\n---\n{body}")
        return path

    def card(self, card_id: str, kind: str = "claim", statement: str = "", **fields) -> Path:
        session = card_id.split("-")[1] if card_id.split("-")[1].startswith("S") else None
        meta = {
            "id": card_id,
            "kind": kind,
            "statement": statement or f"statement of {card_id}",
            "depends_on": fields.pop("depends_on", []),
            "produced_by": fields.pop("produced_by", {"kind": "agent", "model": "m", "operator": "op"}),
            "session": fields.pop("session", session),
            "supersedes": fields.pop("supersedes", []),
            "refutes": fields.pop("refutes", []),
            **fields,
        }
        return self.write(f"claims/{card_id}.md", meta, "Body.\n")

    def derivation(self, art_id: str, supports: list[str]) -> None:
        self.write(f"derivations/{art_id}.summary.md", {"id": art_id, "kind": "derivation", "supports": supports}, "Summary.\n")
        (self.root / f"derivations/{art_id}.tex").write_text("\\documentclass{article}\n")

    def computation(self, art_id: str, supports: list[str]) -> None:
        self.write(f"computations/{art_id}.md", {"id": art_id, "kind": "computation", "supports": supports}, "Summary.\n")
        (self.root / f"computations/{art_id}.py").write_text("print(1)\n")

    def review(self, review_id: str, verdict: str, supports: list[str], human: str | None = None) -> None:
        target, rest = review_id.split("_R-")
        folder = "derivations" if target.startswith("D-") else "computations"
        meta = {
            "id": review_id,
            "kind": "review",
            "target": target,
            "supports": supports,
            "claim": "the claim",
            "verdict": verdict,
            "by": {"kind": "human", "user": human} if human else {"kind": "agent"},
            "session": rest.split("-")[0],
            "date": "2026-10-05",
        }
        self.write(f"{folder}/{review_id}.md", meta, "Review.\n")

    def draft(self, *blocks: str) -> None:
        """Write draft.tex with the given blocks, e.g. result("CL-S1-1") or conjecture("CL-S1-2")."""
        (self.root / "draft.tex").write_text(DRAFT_HEAD + "\n".join(blocks) + DRAFT_TAIL)

    def debrief(self, session: str, text: str) -> Path:
        path = self.root / "sessions" / session / "debrief.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def received(self, session: str, base: str, started: str, debriefs: dict) -> None:
        self.write(f"sessions/{session}/received.md", {"session": session, "started": started, "base": base,
                                                      "debriefs": debriefs}, "```text\n```\n")

    def git_init(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "tester"], cwd=self.root, check=True)
        self.commit("init")

    def commit(self, message: str) -> str:
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", message], cwd=self.root, check=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def toy(tmp_path):
    return ToyWorkspace(tmp_path)


@pytest.fixture
def shared_toy(tmp_path):
    return ToyWorkspace(tmp_path, shared=True)
