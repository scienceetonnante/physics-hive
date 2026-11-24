# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Compile the draft or a session note to PDF.

Builds in a temporary folder, with references.bib generated from the paper
cards, so that the workspace stays clean, and writes draft.pdf or
sessions/S<n>/note.pdf (both git-ignored). Needs latexmk (TeX Live or MacTeX).
The Space calls build_pdf() for its PDF buttons.

Usage: uv run .physics-hive/scripts/pdf.py [draft.tex | sessions/S3/note.tex | S3]
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def latexmk() -> str | None:
    return shutil.which("latexmk")


def build_pdf(tex: str, bib: str, name: str = "document", timeout: int = 120) -> tuple[bytes | None, str]:
    """Compile a LaTeX text with a bibliography. Returns (the PDF, or None on failure; the end of the log)."""
    if not latexmk():
        return None, "latexmk is not installed (it comes with TeX Live or MacTeX)."
    with tempfile.TemporaryDirectory(prefix="physics-hive-pdf-") as tmp:
        folder = Path(tmp)
        (folder / f"{name}.tex").write_text(tex, encoding="utf-8")
        (folder / "references.bib").write_text(bib, encoding="utf-8")
        if "\\cite" not in tex:  # BibTeX fails on a document that cites nothing
            tex = re.sub(r"\\bibliography\{[^}]*\}|\\bibliographystyle\{[^}]*\}", "", tex)
            (folder / f"{name}.tex").write_text(tex, encoding="utf-8")
        try:
            proc = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                                   f"{name}.tex"], cwd=folder, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, f"latexmk did not finish within {timeout} seconds."
        log = folder / f"{name}.log"
        tail = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else proc.stdout + proc.stderr
        errors = [line for line in tail.splitlines() if line.startswith("!") or ":error:" in line.lower()
                  or re.match(r"^[^:]+:\d+: ", line)]
        summary = "\n".join(errors[:20]) or "\n".join(tail.splitlines()[-30:])
        pdf = folder / f"{name}.pdf"
        if proc.returncode != 0 or not pdf.is_file():
            return None, summary
        return pdf.read_bytes(), summary


def main() -> int:
    from cards import find_root
    from common import ScriptError, say
    from regen import regenerate

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", nargs="?", default="draft.tex", help="draft.tex (default), a note's path, or a session")
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.root.resolve() if args.root else find_root()
    rel = f"sessions/{args.what}/note.tex" if re.match(r"^S\d+$", args.what) else args.what
    source = root / rel
    if source.suffix != ".tex":
        raise ScriptError(f"{rel} is not a LaTeX file; name draft.tex, a note's path, or a session such as S3")
    if not source.is_file():
        raise ScriptError(f"{rel} does not exist in this workspace")
    if not latexmk():
        raise ScriptError("latexmk is not installed, so the PDF cannot be built on this machine. It comes with a "
                          "TeX distribution: TeX Live, or MacTeX on a Mac. The Space of a shared space builds the "
                          "PDFs itself.")
    regenerate(root)
    pdf, log = build_pdf(source.read_text(encoding="utf-8"), (root / "references.bib").read_text(encoding="utf-8"),
                         source.stem)
    if pdf is None:
        raise ScriptError(f"{rel} did not compile:\n{log}")
    out = source.with_suffix(".pdf")
    out.write_bytes(pdf)
    say(f"Wrote {out.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
