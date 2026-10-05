# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "huggingface_hub>=1.0"]
# ///
"""Create, join or refresh a PhysicsIntern workspace.

Run without options, it asks a few questions in the terminal, each with a
default: what to do (start a local workspace, create a shared space on the
Hugging Face Hub, or join one), which harnesses will be used on this machine,
and where. Every question also has a flag, so the plugin bootstraps can ask in
the chat and pass the answers.

Run inside an existing workspace, it renders the harness files again (to add a
harness or refresh them) from the workspace's own copy of the method. With
--upgrade it replaces that copy with this one.

Usage:
  uv run scripts/init.py [--mode local|create|join] [--harness claude,codex,opencode,pi]
                         [--dir PATH] [--org ORG --name NAME] [--repo ORG/NAME]
                         [--chat-model ID] [--yes] [--list-orgs] [--upgrade]
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ScriptError, git, git_out, is_git_repo, rendered_harnesses, rerender, say  # noqa: E402

METHOD_ROOT = Path(__file__).resolve().parents[1]  # holds commons/, hosts/, scripts/, VERSION
METHOD_PARTS = ("commons", "hosts", "scripts", "space", "VERSION")
HARNESSES = {
    "claude": ("Claude Code", "claude"),
    "codex": ("Codex CLI", "codex"),
    "opencode": ("OpenCode", "opencode"),
    "pi": ("Pi", "pi"),
}
DEFAULT_CHAT_MODEL = "openai/gpt-oss-120b"
WORKSPACE_DIRS = ("claims", "derivations/.briefs", "computations/.briefs", "critiques", "literature", "sessions", "feedback")
ALLOWED_IN_NEW_DIR = {"problem.md", ".DS_Store"}


def method_version() -> str:
    return (METHOD_ROOT / "VERSION").read_text().strip()


# ----- questions -----


def interactive() -> bool:
    return sys.stdin.isatty()


def ask(question: str, default: str) -> str:
    reply = input(f"{question} [{default}]: ").strip()
    return reply or default


def ask_choice(question: str, options: list[tuple[str, str]], default: str) -> str:
    say(question)
    for i, (key, label) in enumerate(options, 1):
        say(f"  {i}) {label}")
    keys = [k for k, _ in options]
    while True:
        reply = input(f"Choose 1-{len(options)} [{keys.index(default) + 1}]: ").strip()
        if not reply:
            return default
        if reply.isdigit() and 1 <= int(reply) <= len(options):
            return keys[int(reply) - 1]
        if reply in keys:
            return reply
        say("Please type one of the numbers.")


def installed_harnesses() -> list[str]:
    return [name for name, (_, cmd) in HARNESSES.items() if shutil.which(cmd)]


def ask_harnesses(default: list[str]) -> list[str]:
    names = list(HARNESSES)
    ticked = set(default)
    while True:
        say("Which harnesses will you use on this machine?")
        for i, name in enumerate(names, 1):
            mark = "x" if name in ticked else " "
            installed = "" if shutil.which(HARNESSES[name][1]) else "  (not found on this machine)"
            say(f"  [{mark}] {i}. {HARNESSES[name][0]}{installed}")
        reply = input("Type numbers to tick or untick (for example 2 4), or press Enter to accept: ").strip()
        if not reply:
            if ticked:
                return [n for n in names if n in ticked]
            say("Tick at least one harness.")
            continue
        for token in re.split(r"[\s,]+", reply):
            if token.isdigit() and 1 <= int(token) <= len(names):
                ticked ^= {names[int(token) - 1]}
            elif token in names:
                ticked ^= {token}


def parse_harnesses(value: str) -> list[str]:
    names = [v.strip() for v in value.split(",") if v.strip()]
    unknown = [n for n in names if n not in HARNESSES]
    if unknown or not names:
        raise ScriptError(f"--harness takes a comma-separated list from: {', '.join(HARNESSES)}")
    return [n for n in HARNESSES if n in names]


# ----- workspace files -----


def copy_method(target: Path) -> None:
    """Copy the method (commons/, hosts/, scripts/, space/, VERSION) into .physics-intern/."""
    dest = target / ".physics-intern"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    for part in METHOD_PARTS:
        src = METHOD_ROOT / part
        if src.is_dir():
            shutil.copytree(src, dest / part, ignore=ignore)
        elif src.is_file():
            shutil.copy2(src, dest / part)
    (dest / "README.md").write_text(
        "# Method copy\n\n"
        f"This folder is a copy of the PhysicsIntern method, version {method_version()}: the prompts\n"
        "(`commons/`, `hosts/`), the workspace scripts (`scripts/`) and the Space app (`space/`).\n"
        "Every operator renders their harness files from it, so everyone runs the same prompts and\n"
        "scripts, and the prompts that produced a result sit in the git history next to it.\n\n"
        "Do not edit it. Sessions may not touch it; an upgrade replaces it as a whole\n"
        "(`uv run .physics-intern/scripts/init.py --upgrade`, run from a newer copy of the method).\n"
    )


def toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def project_toml(version: str, hub: dict | None, leads: list[str], chat_model: str) -> str:
    lines = [
        "# PhysicsIntern project file. Written by init; edit [people] and [models] by hand if needed.",
        "",
        "[method]",
        f"physics_intern_version = {toml_string(version)}   # version of the method copy in .physics-intern/",
        "",
        "[hub]                                  # empty in local mode",
    ]
    for key in ("workspace", "traces", "sources", "chat_debug", "space"):
        if hub and hub.get(key):
            lines.append(f"{key:<10} = {toml_string(hub[key])}")
    lines += [
        "",
        "[people]                               # shared mode: leads may promote claims and own the lead's files",
        "leads = [" + ", ".join(toml_string(u) for u in leads) + "]",
        "",
        "[models]",
        f"chat = {toml_string(chat_model)}        # explainer chat in the Space",
        "",
    ]
    return "\n".join(lines)


def write_skeleton(target: Path) -> None:
    templates = METHOD_ROOT / "commons" / "templates"
    for name, dest in (("problem.md", "problem.md"), ("plan.md", "plan.md"), ("conventions.md", "conventions.md"),
                       ("seeds.md", "literature/seeds.md"), ("gitignore", ".gitignore")):
        path = target / dest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            shutil.copy2(templates / name, path)
    for folder in WORKSPACE_DIRS:
        (target / folder).mkdir(parents=True, exist_ok=True)
        (target / folder / ".gitkeep").touch()


def render(target: Path, harnesses: list[str]) -> None:
    """Render harness files from the workspace's own method copy."""
    rerender(target, harnesses)


def regen(target: Path) -> None:
    subprocess.run(
        [sys.executable, str(target / ".physics-intern" / "scripts" / "regen.py"), "--root", str(target), "--quiet"],
        check=False,
    )


def check_new_dir(target: Path) -> None:
    if not target.exists():
        return
    names = {p.name for p in target.iterdir()}
    for doc in ("CLAUDE.md", "AGENTS.md"):
        if (target / doc).is_file() and "PhysicsIntern workspace" in (target / doc).read_text(errors="ignore"):
            raise ScriptError(
                f"{target} holds a PhysicsIntern workspace in the earlier format. It keeps working as it is "
                "and is not converted. Create the new workspace in an empty folder."
            )
    extra = sorted(names - ALLOWED_IN_NEW_DIR)
    if extra:
        raise ScriptError(
            f"{target} is not empty ({', '.join(extra[:6])}{', …' if len(extra) > 6 else ''}). "
            "Use an empty folder (it may already contain problem.md)."
        )


def first_commit(target: Path, message: str) -> None:
    if not is_git_repo(target):
        git(target, "init", "-q", "-b", "main")
    paths = [".gitignore", ".physics-intern", "project.toml", "problem.md", "plan.md", "conventions.md", *WORKSPACE_DIRS]
    git(target, "add", "--", *paths)
    git(target, "commit", "-q", "-m", message, "-m", f"Bootstrapped by init (method {method_version()}).")


# ----- modes -----


def create_local(target: Path, harnesses: list[str], chat_model: str, hub: dict | None = None,
                 leads: list[str] | None = None) -> None:
    check_new_dir(target)
    target.mkdir(parents=True, exist_ok=True)
    copy_method(target)
    (target / "project.toml").write_text(project_toml(method_version(), hub, leads or [], chat_model))
    write_skeleton(target)
    render(target, harnesses)


def refresh(target: Path, harnesses: list[str] | None) -> None:
    """Render the selected harnesses, keeping those already rendered here (AGENTS.md covers all)."""
    selected = set(harnesses or []) | set(rendered_harnesses(target))
    harnesses = [h for h in HARNESSES if h in selected] or installed_harnesses()
    if not harnesses:
        raise ScriptError("no harness selected; pass --harness")
    render(target, harnesses)
    regen(target)
    names = ", ".join(HARNESSES[h][0] for h in harnesses)
    say(f"Rendered the harness files for {names} from this workspace's method copy.")
    say_launch(harnesses)


def upgrade(target: Path, harnesses: list[str] | None) -> None:
    import tomllib

    project = tomllib.loads((target / "project.toml").read_text())
    old = project.get("method", {}).get("physics_intern_version", "?")
    new = method_version()
    if is_git_repo(target) and git_out(target, "status", "--porcelain"):
        raise ScriptError("the workspace has uncommitted changes; commit or discard them before an upgrade")
    if (target / ".active-session").exists():
        raise ScriptError("a session is active in this checkout; end or abort it before an upgrade")
    if project.get("hub", {}).get("workspace"):
        from hub import upgrade_shared

        upgrade_shared(target, old, new, copy_method, harnesses or rendered_harnesses(target))
        return
    copy_method(target)
    text = (target / "project.toml").read_text()
    text = re.sub(r'(physics_intern_version\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{new}"', text)
    (target / "project.toml").write_text(text)
    render(target, harnesses or rendered_harnesses(target))
    git(target, "add", "-A", "--", ".physics-intern", "project.toml")
    git(target, "commit", "-q", "-m", f"Upgrade the method copy from {old} to {new}")
    regen(target)
    say(f"Upgraded the method copy from {old} to {new} and re-rendered the harness files.")


def say_launch(harnesses: list[str], prefix: str = "") -> None:
    hints = {
        "claude": "claude",
        "codex": "codex        (accept the trust prompt on first launch, so .codex/config.toml applies)",
        "opencode": "opencode",
        "pi": "pi           (installs pi-subagents and pi-web-access on first launch)",
    }
    say(f"{prefix}Launch a harness in this folder:")
    for h in harnesses:
        say(f"{' ' * len(prefix)}     {hints[h]}")


def say_next_steps(harnesses: list[str], mode: str) -> None:
    say("")
    say("Next steps:")
    if mode in ("local", "create"):
        say("  1. Write the question and its definition of done in problem.md, and seed papers in")
        say("     literature/seeds.md if you have some (or ask the coordinator to write them with you).")
    else:
        say("  1. Read problem.md and plan.md, written by the lead.")
    say_launch(harnesses, prefix="  2. ")
    codex = " ($session-run in Codex)" if "codex" in harnesses else ""
    bench = " For a benchmark run, use /autoresearch instead." if mode == "local" else ""
    say(f"  3. Run /session-run{codex} to start a session.{bench}")
    say("")


# ----- entry point -----


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dir_arg", nargs="?", metavar="DIR", help="target folder (same as --dir)")
    parser.add_argument("--mode", choices=["local", "create", "join"])
    parser.add_argument("--harness", "--harnesses", dest="harness", help="comma-separated: " + ", ".join(HARNESSES))
    parser.add_argument("--host", help=argparse.SUPPRESS)  # earlier name of --harness
    parser.add_argument("--dir", help="target folder (default: the current folder)")
    parser.add_argument("--org", help="create: Hugging Face organisation that will own the repositories")
    parser.add_argument("--name", help="create: project name")
    parser.add_argument("--repo", help="join: the workspace repository, org/name")
    parser.add_argument("--chat-model", default=None, help=f"model of the Space's explainer chat (default {DEFAULT_CHAT_MODEL})")
    parser.add_argument("--space-token", choices=["mine", "none"], default=None,
                        help="create: give the Space your token (mine) or set it yourself later (none)")
    parser.add_argument("--yes", action="store_true", help="do not ask; use defaults for anything not given")
    parser.add_argument("--list-orgs", action="store_true", help="print the organisations you belong to and exit")
    parser.add_argument("--upgrade", action="store_true", help="replace the workspace's method copy with this one")
    args = parser.parse_args()

    if args.list_orgs:
        from hub import list_orgs

        for org in list_orgs():
            say(org)
        return 0

    asking = interactive() and not args.yes
    harness_flag = args.harness or args.host
    harnesses = parse_harnesses(harness_flag) if harness_flag else None
    dir_value = args.dir or args.dir_arg

    # Inside an existing workspace: refresh or upgrade.
    probe = Path(dir_value or ".").expanduser().resolve()
    if (probe / "project.toml").is_file() and (probe / ".physics-intern").is_dir():
        if args.upgrade:
            upgrade(probe, harnesses)
        else:
            if harnesses is None and asking:
                harnesses = ask_harnesses(rendered_harnesses(probe) or installed_harnesses())
            refresh(probe, harnesses)
        return 0
    if args.upgrade:
        raise ScriptError(f"{probe} is not a PhysicsIntern workspace (no project.toml)")

    mode = args.mode
    if mode is None:
        mode = ask_choice(
            "What do you want to do?",
            [("local", "Start a local workspace (one person, this machine)"),
             ("create", "Create a shared space on the Hugging Face Hub"),
             ("join", "Join an existing shared space")],
            "local",
        ) if asking else "local"
    if harnesses is None:
        default = installed_harnesses() or ["claude"]
        harnesses = ask_harnesses(default) if asking else default

    chat_model = args.chat_model or DEFAULT_CHAT_MODEL
    if mode == "join":
        from hub import join

        repo = args.repo or (ask("Workspace repository to join (org/name)", "") if asking else "")
        if not repo:
            raise ScriptError("join needs the workspace repository: --repo org/name")
        default_dir = "." if not any(Path(".").iterdir()) else repo.split("/")[-1]
        target = Path(dir_value or (ask("Folder to clone into", default_dir) if asking else default_dir))
        target = target.expanduser().resolve()
        join(target, repo, harnesses, render, regen, check_new_dir)
        say_next_steps(harnesses, mode)
        return 0

    target = Path(dir_value or (ask("Folder for the workspace", ".") if asking else ".")).expanduser().resolve()
    if mode == "local":
        create_local(target, harnesses, chat_model)
        first_commit(target, "Initialize PhysicsIntern workspace (local mode)")
        regen(target)
        say(f"PhysicsIntern workspace created at {target} (local mode, method {method_version()}).")
    else:
        from hub import create_shared, list_orgs

        org = args.org
        if org is None and asking:
            orgs = list_orgs()
            if not orgs:
                raise ScriptError("you belong to no Hugging Face organisation; create one, or ask to join your team's")
            org = ask_choice("Which organisation will own the project?", [(o, o) for o in orgs], orgs[0])
        name = args.name or (ask("Project name", target.name) if asking else None)
        if not org or not name:
            raise ScriptError("create needs --org and --name")
        space_token = args.space_token or ("mine" if not asking else
                                           ("mine" if ask("Give the Space your Hugging Face token so it can commit feedback? (y/n)", "y").lower().startswith("y") else "none"))
        create_shared(target, org, name, harnesses, chat_model, space_token,
                      create_local=create_local, first_commit=first_commit, regen=regen, version=method_version())
    say_next_steps(harnesses, mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
