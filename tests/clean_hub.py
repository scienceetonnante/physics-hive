# /// script
# requires-python = ">=3.11"
# dependencies = ["huggingface_hub>=1.0"]
# ///
"""Delete the Hub repositories of test projects. Not run by pytest.

A shared project owns four private datasets on the Hub (the workspace and its
-traces, -sources and -chat-debug companions) and a private Space. PhysicsHive
names them <owner>/physics-hive-<name>[-suffix] and gives the Space the
workspace's name (see repo_names in scripts/hub.py). Projects created with
Physics Intern have no prefix, and their Space may be named <name>-space; the
script finds those too.

For each project it lists the repositories that exist, then asks before
deleting them. Deletion cannot be undone.

Usage:
  uv run tests/clean_hub.py TARGET... [--local] [--yes]
  uv run tests/clean_hub.py --owner OWNER [--yes]

TARGET is a local workspace folder (its repositories are read from the [hub]
table of its project.toml) or a workspace repository id of the form
<owner>/physics-hive-<name>. --owner lists every project under a user or an
organisation: a dataset X-chat-debug, or any dataset named physics-hive-*.
--local also deletes the workspace folders given as targets. --yes deletes
without asking; without it, and without a terminal to ask in, the script only
lists.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tomllib
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError

SUFFIXES = ("-traces", "-sources", "-chat-debug")
PREFIX = "physics-hive-"


def candidates(base: str) -> list[tuple[str, str]]:
    """The repositories a project whose workspace is `base` may have, as (repo id, repo type)."""
    return ([(base, "dataset")] + [(base + s, "dataset") for s in SUFFIXES]
            + [(base, "space"), (base + "-space", "space")])


def from_folder(folder: Path) -> list[tuple[str, str]]:
    toml = folder / "project.toml"
    if not toml.is_file():
        raise SystemExit(f"{folder} has no project.toml: it is not a PhysicsHive workspace")
    hub = tomllib.loads(toml.read_text(encoding="utf-8")).get("hub", {})
    if not hub.get("workspace"):
        raise SystemExit(f"{folder} is a local workspace: it has nothing on the Hub")
    repos = [(hub[k], "dataset") for k in ("workspace", "traces", "sources", "chat_debug") if hub.get(k)]
    return repos + ([(hub["space"], "space")] if hub.get("space") else [])


def strip_suffix(repo_id: str) -> str:
    for s in SUFFIXES:
        if repo_id.endswith(s):
            return repo_id[: -len(s)]
    return repo_id


def find_projects(api: HfApi, owner: str) -> list[str]:
    """The workspace ids of the projects under `owner`."""
    found = {d.id for term in ("-chat-debug", PREFIX) for d in api.list_datasets(author=owner, search=term)}
    bases = {strip_suffix(i) for i in found
             if i.endswith("-chat-debug") or i.split("/", 1)[1].startswith(PREFIX)}
    return sorted(bases)


def existing(api: HfApi, repos: list[tuple[str, str]]) -> list[tuple[str, str, object]]:
    out = []
    for repo_id, kind in repos:
        try:
            out.append((repo_id, kind, api.repo_info(repo_id, repo_type=kind)))
        except RepositoryNotFoundError:
            pass
    return out


def confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        print("  Not deleted: run with --yes, or from a terminal to be asked.")
        return False
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def clean(api: HfApi, label: str, repos: list[tuple[str, str]], folder: Path | None, yes: bool) -> None:
    found = existing(api, repos)
    print(f"\n{label}")
    if not found and folder is None:
        print("  Nothing on the Hub.")
        return
    for repo_id, kind, info in found:
        visibility = "private" if info.private else "PUBLIC"
        print(f"  {kind:<8} {repo_id}  (created {str(info.created_at)[:10]}, {visibility})")
    if folder is not None:
        print(f"  folder   {folder}")
    if not confirm(f"Delete these {len(found) + (folder is not None)} items?", yes):
        return
    # The Space first, so that it stops using its token before the workspace goes.
    for repo_id, kind, _ in sorted(found, key=lambda r: r[1] != "space"):
        try:
            api.delete_repo(repo_id, repo_type=kind, missing_ok=True)
            print(f"  Deleted {kind} {repo_id}")
        except HfHubHTTPError as exc:
            print(f"  Could not delete {kind} {repo_id}: {exc}")
    if folder is not None:
        shutil.rmtree(folder)
        print(f"  Deleted folder {folder}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="workspace folders or workspace repository ids")
    parser.add_argument("--owner", help="list every project under this user or organisation")
    parser.add_argument("--local", action="store_true", help="also delete the workspace folders given as targets")
    parser.add_argument("--yes", action="store_true", help="delete without asking")
    args = parser.parse_args()
    if not args.targets and not args.owner:
        parser.error("give workspace folders, repository ids, or --owner")
    api = HfApi()
    jobs = []  # (label, repositories, folder to delete or None)
    for target in args.targets:
        path = Path(target).expanduser()
        if path.is_dir():
            jobs.append((f"Workspace {path}", from_folder(path), path.resolve() if args.local else None))
        elif target.count("/") == 1:
            jobs.append((f"Project {target}", candidates(target), None))
        else:
            raise SystemExit(f"{target} is neither a folder nor a repository id (owner/name)")
    if args.owner:
        projects = find_projects(api, args.owner)
        print(f"{len(projects)} projects under {args.owner}")
        jobs += [(f"Project {base}", candidates(base), None) for base in projects]
    for label, repos, folder in jobs:
        clean(api, label, repos, folder, args.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
