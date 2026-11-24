# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "huggingface_hub>=1.16"]
# ///
"""Build the public demonstration Space of PhysicsHive, and with --push upload it to the Hub.

The demonstration is the Space app showing the example workspace examples/pendulum/
read-only: a visitor opens every page and types in every form, and nothing is
saved. The built folder holds:

  README.md    the Space's card (a public Docker Space, without sign-in)
  Dockerfile   space/Dockerfile, with PHYSICS_HIVE_LOCAL set to the example and
               PHYSICS_HIVE_READONLY=1
  space/       the app
  scripts/     the method modules the app imports for a workspace without a
               method copy (backend.METHOD_MODULES), and nothing else
  pendulum/    the example workspace, without hidden files

Without --push it only builds the folder (in --dir, or a new temporary folder)
and says how to try it on this machine. With --push it also creates the Space
if needed (public, Docker) and uploads the folder, with your Hugging Face login:

  uv run examples/deploy_demo.py                       # build only
  uv run examples/deploy_demo.py --push --repo <owner>/<name>
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import common  # noqa: E402,F401  (first: it sets up the Hub's certificates on macOS)
import hub  # noqa: E402

EXAMPLE = REPO / "examples" / "pendulum"
# What the app imports from scripts/ when the workspace has no method copy: backend.METHOD_MODULES
# (tests/test_demo_space.py checks that the two lists are the same).
METHOD_MODULES = ("cards", "common", "human", "regen", "check", "pdf")
APP_FOLDER, WORKSPACE_FOLDER = "space", "pendulum"
HIDDEN_AND_CACHES = (".*", "__pycache__", "*.pyc")  # hidden files (.env, .DS_Store), caches
DESCRIPTION = "A real PhysicsHive project after two sessions, read-only"  # the Hub allows 60 characters

CARD = f"""---
title: PhysicsHive demo
emoji: ⚛️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: {DESCRIPTION}
tags: [{hub.CARD_TAG}]
---

# PhysicsHive demo

PhysicsHive lets a small team of scientists steer AI coding agents on one problem in theoretical physics or
mathematics. The agents work in sessions in a terminal; the project's leads read what the agents found
and answer them in a web app like this one.

This is that app on a real workspace, after two sessions on a textbook question: what is the period of a pendulum
to second order in the amplitude? The first session answered it; the lead read its debrief and ticked its result
for the draft, which the second session copied there before it looked for a paper to cite. The second session's
debrief is waiting for the lead's response. You can open every page, follow the result to its derivation,
computation and reviews, and type in the forms. This demonstration is read-only: nothing you type is saved.

To install PhysicsHive and use it on your own problem: {hub.PROJECT_URL}
"""


def dockerfile() -> str:
    """space/Dockerfile, changed to run the app in space/ on the bundled example, read-only."""
    text = (REPO / "space" / "Dockerfile").read_text(encoding="utf-8")
    changes = [
        ("COPY --chown=user requirements.txt .", f"COPY --chown=user {APP_FOLDER}/requirements.txt ."),
        ("ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1",
         "ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1\n"
         f"ENV PHYSICS_HIVE_LOCAL=/home/user/app/{WORKSPACE_FOLDER} PHYSICS_HIVE_READONLY=1"),
        ("COPY --chown=user . .", f"COPY --chown=user . .\nWORKDIR $HOME/app/{APP_FOLDER}"),
    ]
    for old, new in changes:
        if text.count(old) != 1:
            raise SystemExit(f"ERROR: space/Dockerfile no longer has the line `{old}`; update deploy_demo.py.")
        text = text.replace(old, new)
    return ("# The PhysicsHive demonstration Space: the app in space/ shows the example workspace pendulum/ read-only.\n"
            "# Built by examples/deploy_demo.py from space/Dockerfile.\n" + text)


def skipping(*patterns: str):
    """An `ignore` for shutil.copytree: the patterns, and every symbolic link, which would otherwise upload the
    content of its target. Each link skipped is printed."""
    by_pattern = shutil.ignore_patterns(*patterns)

    def ignore(folder: str, names: list[str]) -> set[str]:
        links = {name for name in names if (Path(folder) / name).is_symlink()}
        for name in sorted(links):
            print(f"Skipped the symbolic link {Path(folder) / name}: links are not uploaded.")
        return set(by_pattern(folder, names)) | links

    return ignore


def build(target: Path) -> Path:
    """Write the Space's folder into `target`, which must not exist or be empty."""
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"ERROR: {target} is not empty. Name a new folder with --dir.")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / "space", target / APP_FOLDER, dirs_exist_ok=True,
                    ignore=skipping(*HIDDEN_AND_CACHES, "README.md", "Dockerfile"))
    (target / "scripts").mkdir()
    for name in METHOD_MODULES:
        source = REPO / "scripts" / f"{name}.py"
        if source.is_symlink():
            raise SystemExit(f"ERROR: {source} is a symbolic link; the demonstration needs the file itself.")
        shutil.copy2(source, target / "scripts" / f"{name}.py")
    shutil.copytree(EXAMPLE, target / WORKSPACE_FOLDER, ignore=skipping(*HIDDEN_AND_CACHES))
    (target / "Dockerfile").write_text(dockerfile(), encoding="utf-8")
    (target / "README.md").write_text(CARD, encoding="utf-8")
    return target


def push(folder: Path, repo: str, hf=None) -> str:
    """Create the public Space if it does not exist, and upload the folder. Returns the Space's page."""
    hf = hf or hub.api()
    hf.create_repo(repo, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    # Files of an earlier upload that this one no longer has are removed from the three folders.
    hf.upload_folder(repo_id=repo, repo_type="space", folder_path=str(folder),
                     commit_message="Deploy the PhysicsHive demonstration",
                     delete_patterns=[f"{APP_FOLDER}/**", "scripts/**", f"{WORKSPACE_FOLDER}/**"])
    return f"https://huggingface.co/spaces/{repo}"


def main(argv: list[str] | None = None, hf=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", help="the folder to build in (new or empty; default: a new temporary folder)")
    parser.add_argument("--push", action="store_true", help="upload the folder to the Space named by --repo")
    parser.add_argument("--repo", help="the Space to create or update, as <owner>/<name>")
    args = parser.parse_args(argv)
    if args.push and (not args.repo or args.repo.count("/") != 1):
        parser.error("--push needs --repo <owner>/<name>")

    folder = build(Path(args.dir).expanduser().resolve() if args.dir else Path(tempfile.mkdtemp(prefix="physics-hive-demo-")))
    print(f"Built the demonstration Space in {folder}:")
    for path in sorted(folder.iterdir()):
        count = sum(1 for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0
        print(f"  {path.name}/  ({count} files)" if path.is_dir() else f"  {path.name}")
    if not args.push:
        print("\nTo try it on this machine, then open http://127.0.0.1:7860/:")
        print(f"  cd {folder / APP_FOLDER} && PHYSICS_HIVE_LOCAL=../{WORKSPACE_FOLDER} PHYSICS_HIVE_READONLY=1 \\")
        print("    uv run --with-requirements requirements.txt uvicorn app:app --port 7860")
        print(f"or with Docker: docker build -t physics-hive-demo {folder} && docker run -p 7860:7860 physics-hive-demo")
        print("\nTo upload it: uv run examples/deploy_demo.py --push --repo <owner>/<name>")
        return 0
    # Untracked files in examples/pendulum would be uploaded too: show what will be.
    workspace = folder / WORKSPACE_FOLDER
    print(f"\nThe example workspace to upload ({WORKSPACE_FOLDER}/):")
    for path in sorted(p for p in workspace.rglob("*") if p.is_file()):
        print(f"  {path.relative_to(workspace).as_posix()}")
    page = push(folder, args.repo, hf)
    print(f"\nUploaded to {page}. The Hub builds the image, which takes a few minutes; the page shows the build log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(common.run_main(main))
