# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6", "huggingface_hub>=1.0"]
# ///
"""Create, join or refresh a PhysicsHive workspace.

It is launched by install.sh, from a downloaded release of the method, or by
init-physics-hive.sh, from a clone of the method repository. HELP below is what
--help prints; README.md describes the same steps for users.

The Space of a new shared space holds a copy of a token, its secret HF_TOKEN. By
default it is the token in the environment variable PHYSICS_HIVE_SPACE_TOKEN
if that is set (or in the .env at the root of this method repository, when run
from a clone of it), else your login token (`hf auth login`).
"""

from __future__ import annotations

import argparse
import functools
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ScriptError, git, git_out, is_git_repo, rendered_harnesses, rerender, run_main, say  # noqa: E402
from human import TITLE_PLACEHOLDER, parse_project  # noqa: E402

METHOD_ROOT = Path(__file__).resolve().parents[1]  # holds commons/, hosts/, scripts/, VERSION
METHOD_PARTS = ("commons", "hosts", "scripts", "space", "VERSION")
DOTENV = METHOD_ROOT / ".env"  # in a clone of the method repository; read only for the Space's token
HARNESSES = {
    "claude": ("Claude Code", "claude"),
    "codex": ("Codex CLI", "codex"),
    "opencode": ("OpenCode", "opencode"),
    "pi": ("Pi", "pi"),
}
DEFAULT_CHAT_MODEL = "openai/gpt-oss-20b"
WORKSPACE_DIRS = ("claims", "derivations/.briefs", "computations/.briefs", "critiques", "literature", "sessions")
ALLOWED_IN_NEW_DIR = {"project.md", ".DS_Store"}
GOAL_HINT = "<!-- The question in full, and what would count as an answer. -->"  # in commons/templates/project.md
HELP = """\
Create a PhysicsHive workspace, join a shared one, or refresh one.

Without options, it asks a few questions in the terminal, each with a default:
what to do, which harnesses you will use on this machine, the folder, and for a
new workspace the question of the project and its goal, which it writes into
project.md. Every question also has an option, listed below. With --yes, or
without a terminal, anything not given takes its default. With the installer,
put the options after `sh -s --`.

What to do (--mode):
  create  a shared space on the Hugging Face Hub: private dataset repositories
          and a private Space, owned by an organisation, or by your own account
          to try it alone. Needs a Hugging Face login; it offers to log you in.
  join    a checkout of an existing shared space, for a second machine or a
          second contributor.
  local   a workspace on this machine only, without the Hub or an account.

Run inside an existing workspace, it renders the harness files again from the
workspace's own copy of the method (to add a harness, or to refresh them). With
--upgrade, it first replaces that copy with the version of the method it runs
from.
"""
EPILOG = """\
examples:
  --mode local --harness claude --question "<one line>" --goal "<the goal>"
  --mode create --org our-lab --name x-correction --harness claude,codex
  --mode join --repo our-lab/physics-hive-x-correction
  --harness codex                  (inside a workspace: add a harness)

The Space of a new shared space keeps a copy of a token, to read the workspace
and save your edits: by default the one in the environment variable
PHYSICS_HIVE_SPACE_TOKEN if it is set, else your login token.
"""
README_SETUP = "https://github.com/scienceetonnante/physics-hive/blob/master/docs/harness-setup.md"


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


def ask_optional(question: str) -> str:
    return input(f"{question}\n(press Enter to write it later): ").strip()


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
    """Copy the method (commons/, hosts/, scripts/, space/, VERSION) into .physics-hive/."""
    dest = target / ".physics-hive"
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
        f"This folder is a copy of the PhysicsHive method, version {method_version()}: the prompts\n"
        "(`commons/`, `hosts/`), the workspace scripts (`scripts/`) and the Space app (`space/`).\n"
        "Every contributor renders their harness files from it, so everyone runs the same prompts and\n"
        "scripts, and the prompts that produced a result sit in the git history next to it.\n\n"
        "Do not edit it. Sessions may not touch it; an upgrade replaces it as a whole\n"
        "(`uv run .physics-hive/scripts/init.py --upgrade`, run from a newer copy of the method).\n"
    )


def toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def project_toml(version: str, hub: dict | None, leads: list[str], chat_model: str) -> str:
    lines = [
        "# PhysicsHive project file. Written by init; edit [people] and [models] by hand if needed.",
        "",
        "[method]",
        f"physics_hive_version = {toml_string(version)}   # version of the method copy in .physics-hive/",
        "",
        "[hub]                                  # empty in local mode",
    ]
    for key in ("workspace", "traces", "sources", "chat_debug", "space"):
        if hub and hub.get(key):
            lines.append(f"{key:<10} = {toml_string(hub[key])}")
    lines += [
        "",
        "[people]                               # the lead; more people later (see the design, section 4)",
        "leads = [" + ", ".join(toml_string(u) for u in leads) + "]",
        "",
        "[models]",
        f"chat = {toml_string(chat_model)}        # the Space's assistant, when it has one",
        "",
    ]
    return "\n".join(lines)


def write_skeleton(target: Path) -> None:
    templates = METHOD_ROOT / "commons" / "templates"
    for name, dest in (("project.md", "project.md"), ("conventions.md", "conventions.md"), ("draft.tex", "draft.tex"),
                       ("seeds.md", "literature/seeds.md"), ("gitignore", ".gitignore")):
        path = target / dest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            shutil.copy2(templates / name, path)
    for folder in WORKSPACE_DIRS:
        (target / folder).mkdir(parents=True, exist_ok=True)
        (target / folder / ".gitkeep").touch()


def fill_project(target: Path, question: str, goal: str) -> None:
    """Write the question (the title) and the goal into project.md, where it still shows the template's placeholders."""
    path = target / "project.md"
    text = path.read_text(encoding="utf-8")
    if question:
        text = text.replace(f"# {TITLE_PLACEHOLDER}\n", f"# {question}\n", 1)
    if goal:
        text = text.replace(GOAL_HINT, goal, 1)
    path.write_text(text, encoding="utf-8")


def project_missing(target: Path) -> list[str]:
    """What project.md still lacks before a session can start: the question (its title), the goal, or neither."""
    path = target / "project.md"
    if not path.is_file():
        return ["question", "goal"]
    doc = parse_project(path.read_text(encoding="utf-8"))
    missing = []
    if doc.title.strip() in ("", TITLE_PLACEHOLDER):
        missing.append("question")
    if not doc.sections.get("Goal", "").strip():
        missing.append("goal")
    return missing


def render(target: Path, harnesses: list[str]) -> None:
    """Render harness files from the workspace's own method copy."""
    rerender(target, harnesses)


def regen(target: Path) -> None:
    subprocess.run(
        [sys.executable, str(target / ".physics-hive" / "scripts" / "regen.py"), "--root", str(target), "--quiet"],
        check=False,
    )


def warm_up(target: Path) -> None:
    """Install the literature tools' dependencies once, so that the harnesses' first start of the
    MCP server does not spend its startup timeout installing them. Failures are not fatal."""
    if os.environ.get("PHYSICS_HIVE_NO_WARMUP") or not shutil.which("uv"):
        return
    say("Preparing the literature tools (installing their dependencies once)…")
    try:
        subprocess.run(["uv", "run", "--quiet", ".physics-hive/scripts/literature.py", "--help"], cwd=target,
                       capture_output=True, timeout=300, check=False)
    except subprocess.TimeoutExpired:
        say("  (not finished; the first literature call will finish it)")


def check_new_dir(target: Path) -> None:
    if not target.exists():
        return
    if not target.is_dir():
        raise ScriptError(f"{target} is a file, not a folder. Name a new or empty folder, for example with --dir.")
    names = {p.name for p in target.iterdir()}
    for doc in ("CLAUDE.md", "AGENTS.md"):
        if (target / doc).is_file() and "PhysicsHive workspace" in (target / doc).read_text(errors="ignore"):
            raise ScriptError(
                f"{target} holds a PhysicsHive workspace in the earlier format. It keeps working as it is "
                "and is not converted. Create the new workspace in an empty folder."
            )
    extra = sorted(names - ALLOWED_IN_NEW_DIR)
    if extra:
        raise ScriptError(
            f"{target} is not empty ({', '.join(extra[:6])}{', …' if len(extra) > 6 else ''}). A new workspace "
            "needs an empty or new folder (one that holds only project.md is fine). Name another folder, for "
            "example with --dir my-project."
        )


def first_commit(target: Path, message: str) -> None:
    if not is_git_repo(target):
        git(target, "init", "-q", "-b", "main")
    paths = [".gitignore", ".physics-hive", "project.toml", "project.md", "conventions.md", "draft.tex", *WORKSPACE_DIRS]
    git(target, "add", "--", *paths)
    git(target, "commit", "-q", "-m", message, "-m", f"Bootstrapped by init (method {method_version()}).")


# ----- modes -----


def create_local(target: Path, harnesses: list[str], chat_model: str, hub: dict | None = None,
                 leads: list[str] | None = None, question: str = "", goal: str = "") -> None:
    check_new_dir(target)
    target.mkdir(parents=True, exist_ok=True)
    copy_method(target)
    (target / "project.toml").write_text(project_toml(method_version(), hub, leads or [], chat_model))
    write_skeleton(target)
    fill_project(target, question, goal)
    render(target, harnesses)
    warm_up(target)


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
    say_launch(harnesses, target)
    say("Restart a harness that is already running in this folder, so that it reads the new files.")


def upgrade(target: Path, harnesses: list[str] | None) -> None:
    import tomllib

    project = tomllib.loads((target / "project.toml").read_text())
    old = project.get("method", {}).get("physics_hive_version", "?")
    new = method_version()
    if is_git_repo(target) and git_out(target, "status", "--porcelain"):
        raise ScriptError("the workspace has uncommitted changes; commit or discard them before an upgrade")
    if (target / ".active-session").exists():
        raise ScriptError("a session is active in this checkout; end or abort it before an upgrade")
    if (target / "problem.md").is_file() and not (target / "project.md").is_file():
        raise ScriptError(
            f"this workspace uses the earlier format of method {old} (problem.md, plan.md, question cards, session "
            f"reports, promotion records). Method {new} reads project.md, debriefs, notes and draft.tex instead, and "
            "does not convert a workspace. Keep this one on its own method copy, or start a new workspace."
        )
    if project.get("hub", {}).get("workspace"):
        from hub import upgrade_shared

        upgrade_shared(target, old, new, copy_method, harnesses or rendered_harnesses(target))
        return
    copy_method(target)
    text = (target / "project.toml").read_text()
    text = re.sub(r'(physics_hive_version\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{new}"', text)
    (target / "project.toml").write_text(text)
    render(target, harnesses or rendered_harnesses(target))
    git(target, "add", "-A", "--", ".physics-hive", "project.toml")
    if not git_out(target, "diff", "--cached", "--name-only"):
        say(f"This workspace already has this copy of the method ({new}); there is nothing to upgrade. "
            "The harness files were rendered again.")
        return
    git(target, "commit", "-q", "-m", f"Upgrade the method copy from {old} to {new}")
    regen(target)
    say(f"Upgraded the method copy from {old} to {new} and re-rendered the harness files.")


def place(target: Path) -> str:
    """The workspace folder as the user can type it: relative to the current folder when it is inside it."""
    rel = os.path.relpath(target, Path.cwd().resolve())
    return shlex.quote(rel if not rel.startswith("..") else str(target))


def say_launch(harnesses: list[str], target: Path, prefix: str = "") -> None:
    hints = {
        "claude": "claude       (accept the trust prompt on first launch)",
        "codex": "codex        (accept the trust prompt on first launch, so .codex/config.toml applies)",
        "opencode": "opencode",
        "pi": "pi           (installs pi-subagents and pi-web-access on first launch)",
    }
    pad = " " * len(prefix) + "     "
    if target == Path.cwd().resolve():
        say(f"{prefix}Launch a harness in this folder:")
    else:
        say(f"{prefix}Go to the workspace folder and launch a harness there:")
        say(f"{pad}cd {place(target)}")
    for h in harnesses:
        missing = "" if shutil.which(HARNESSES[h][1]) else f"   ({HARNESSES[h][0]} is not installed on this machine yet)"
        say(f"{pad}{hints[h]}{missing}")


def say_next_steps(harnesses: list[str], mode: str, target: Path, missing: list[str]) -> None:
    what = {
        ("question", "goal"): "the question in one line as the title of project.md, and the goal under Goal",
        ("question",): "the question in one line as the title of project.md",
        ("goal",): "the goal under Goal in project.md",
    }.get(tuple(missing), "")
    if mode == "create" and what:
        first = (f"In the Space (its address is above), on the Project page, write {what}. Add seed papers on the "
                 "Literature page if you have some.")
    elif mode == "create":
        first = "If you have seed papers, list them on the Space's Literature page (its address is above)."
    elif mode == "local" and what:
        them = "them" if len(missing) == 2 else "it"
        first = (f"Write {what} (the other sections can wait), or dictate {them} to the coordinator once your "
                 "harness is running. List seed papers in literature/seeds.md if you have some.")
    elif mode == "local":
        first = "If you have seed papers, list them in literature/seeds.md."
    else:
        first = "Read project.md and the latest debrief (the Space shows both)."
    codex = " ($session-run in Codex)" if "codex" in harnesses else ""
    third = (f"Run /session-run{codex}. The coordinator proposes a brief; once you confirm it, the session works on "
             "its own for up to a few hours, then writes a note and a debrief.")
    say("")
    say("Next steps:")
    say(textwrap.fill(first, width=100, initial_indent="  1. ", subsequent_indent="     "))
    say_launch(harnesses, target, prefix="  2. ")
    say(textwrap.fill(third, width=100, initial_indent="  3. ", subsequent_indent="     "))
    if mode == "local":
        say("  4. Read the note and answer the debrief in your browser. In the workspace folder, run")
        say("          uv run .physics-hive/scripts/serve.py")
        say("     and open the address it prints. You can also answer in sessions/S1/debrief.md with a text editor.")
    else:
        say("  4. Read the note and answer the debrief in the Space. The next /session-run starts from your answers.")
    say("")
    say(f"Before the first session, read how to set up your harness: {README_SETUP}")
    say("")


# ----- entry point -----


def load_from_dotenv(name: str) -> None:
    """Put `name` from DOTENV into the environment, unless the environment already has it."""
    if os.environ.get(name, "").strip() or not DOTENV.is_file():
        return
    for line in DOTENV.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip().removeprefix("export ").strip() == name:
            os.environ[name] = value.strip().strip("'\"")
            return


def main() -> int:
    parser = argparse.ArgumentParser(prog=os.environ.get("PHYSICS_HIVE_PROG") or None, description=HELP,
                                     epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dir_arg", nargs="?", metavar="DIR", help="the folder (same as --dir)")
    parser.add_argument("--mode", choices=["create", "join", "local"], help="what to do (default: create)")
    parser.add_argument("--harness", "--harnesses", dest="harness", metavar="LIST",
                        help="the harnesses you will use on this machine, comma-separated, from: "
                             f"{', '.join(HARNESSES)} (default: those installed, else claude)")
    parser.add_argument("--host", help=argparse.SUPPRESS)  # earlier name of --harness
    parser.add_argument("--dir", metavar="PATH", help="the folder of the workspace (default: the current folder). "
                        "A new workspace needs an empty or new folder.")
    parser.add_argument("--org", help="create: the Hugging Face organisation, or your own account, that will own "
                        "the project")
    parser.add_argument("--name", help="create: the project's name; its repositories are named "
                        "ORG/physics-hive-NAME")
    parser.add_argument("--repo", metavar="ORG/NAME", help="join: the workspace repository, as printed by create")
    parser.add_argument("--question", default="", metavar="TEXT", help="create and local: the question of the "
                        "project in one line, written as the title of project.md")
    parser.add_argument("--goal", default="", metavar="TEXT", help="create and local: the goal (the question in "
                        "full, and what would count as an answer), written under Goal in project.md")
    parser.add_argument("--chat-model", default=None, help=argparse.SUPPRESS)  # for the Space's assistant, not built yet
    parser.add_argument("--space-token", choices=["env", "mine", "none"], default=None,
                        help="create: the token the Space holds: the one in PHYSICS_HIVE_SPACE_TOKEN (env, the "
                             "default when it is set), your login token (mine, the default otherwise), or none "
                             "(you set it later in the Space's settings)")
    parser.add_argument("--yes", action="store_true", help="do not ask; use the defaults for anything not given")
    parser.add_argument("--upgrade", action="store_true", help="inside a workspace: replace its method copy with "
                        "this version of the method")
    args = parser.parse_args()

    if not shutil.which("git"):
        raise ScriptError("PhysicsHive needs git, which is not installed. Install it (on macOS: "
                          "xcode-select --install), then run this again.")
    asking = interactive() and not args.yes
    harness_flag = args.harness or args.host
    harnesses = parse_harnesses(harness_flag) if harness_flag else None
    dir_value = args.dir or args.dir_arg

    # Inside an existing workspace: refresh or upgrade.
    probe = Path(dir_value or ".").expanduser().resolve()
    if (probe / "project.toml").is_file() and (probe / ".physics-hive").is_dir():
        if args.upgrade:
            upgrade(probe, harnesses)
        else:
            if args.mode:
                say(f"{probe} is already a PhysicsHive workspace; nothing new was created.")
            if harnesses is None and asking:
                harnesses = ask_harnesses(rendered_harnesses(probe) or installed_harnesses())
            refresh(probe, harnesses)
        return 0
    if args.upgrade:
        raise ScriptError(f"{probe} is not a PhysicsHive workspace (it has no project.toml). Run --upgrade inside "
                          "a workspace, or name one with --dir.")

    mode = args.mode
    if mode is None:
        mode = ask_choice(
            "What do you want to do?",
            [("create", "Create a shared space on the Hugging Face Hub"),
             ("join", "Join an existing shared space"),
             ("local", "Start a local workspace (this machine only, without the Hub)")],
            "create",
        ) if asking else "create"
    if harnesses is None:
        default = installed_harnesses() or ["claude"]
        harnesses = ask_harnesses(default) if asking else default

    chat_model = args.chat_model or DEFAULT_CHAT_MODEL
    if mode == "join":
        from hub import join, project_name

        ensure_hub_login(asking)
        repo = args.repo or (ask("Workspace repository to join (org/name)", "") if asking else "")
        if not repo:
            raise ScriptError("join needs the workspace repository: --repo org/name")
        default_dir = "." if not any(Path(".").iterdir()) else project_name(repo)
        target = Path(dir_value or (ask("Folder to clone into", default_dir) if asking else default_dir))
        target = target.expanduser().resolve()
        join(target, repo, harnesses, render, regen, check_new_dir)
        warm_up(target)
        say_next_steps(harnesses, mode, target, missing=[])
        return 0

    target = choose_folder(dir_value, asking)
    if mode == "local":
        question, goal = ask_project(args, asking, target)
        create_local(target, harnesses, chat_model, question=question, goal=goal)
        first_commit(target, "Initialize PhysicsHive workspace (local mode)")
        regen(target)
        say(f"PhysicsHive workspace created at {target} (local mode, method {method_version()}).")
    else:
        from hub import SPACE_TOKEN_ENV, create_shared, owners

        ensure_hub_login(asking)
        org = args.org
        if org is None and asking:
            *orgs, me = owners()
            choices = [(o, o) for o in orgs] + [(me, f"{me} (your own account: only you can see the project)")]
            org = ask_choice("Which organisation, or your own account, will own the project?", choices,
                             orgs[0] if orgs else me)
        name = args.name or (ask("Project name", target.name) if asking else None)
        if not org or not name:
            raise ScriptError("create needs --org and --name (run without --yes in a terminal to be asked). "
                              "To try PhysicsHive without the Hub, use --mode local.")
        question, goal = ask_project(args, asking, target)
        load_from_dotenv(SPACE_TOKEN_ENV)
        space_token = args.space_token
        if space_token is None and os.environ.get(SPACE_TOKEN_ENV, "").strip():
            space_token = "env"
        elif space_token is None:
            space_token = "mine" if not asking else (
                "mine" if ask("Give the Space your Hugging Face token so it can save your answers and edits? (y/n)",
                              "y").lower().startswith("y") else "none")
        create_shared(target, org, name, harnesses, chat_model, space_token,
                      create_local=functools.partial(create_local, question=question, goal=goal),
                      first_commit=first_commit, regen=regen, version=method_version())
    say_next_steps(harnesses, mode, target, missing=project_missing(target))
    return 0


def choose_folder(dir_value: str | None, asking: bool) -> Path:
    """The folder of a new workspace, checked before anything else is asked; asked again while it is not usable."""
    if dir_value or not asking:
        target = Path(dir_value or ".").expanduser().resolve()
        check_new_dir(target)
        return target
    default = "."
    while True:
        target = Path(ask("Folder for the workspace", default)).expanduser().resolve()
        try:
            check_new_dir(target)
            return target
        except ScriptError as exc:
            say(str(exc.code).removeprefix("ERROR: "))
            default = "physics-hive-project"


def ensure_hub_login(asking: bool) -> None:
    """When no Hugging Face token is found, log in in the terminal rather than stop with an error."""
    from huggingface_hub import get_token, interpreter_login

    if get_token() or not asking:
        return
    say("You are not logged in to Hugging Face. Log in with a token that can write to the organisation that")
    say("will own the project (https://huggingface.co/settings/tokens); it is saved as `hf auth login` does.")
    interpreter_login()


def ask_project(args: argparse.Namespace, asking: bool, target: Path) -> tuple[str, str]:
    """The question and the goal for a new project.md, from the flags or asked in the terminal.

    Nothing is asked when the folder already holds a project.md written by the lead."""
    question, goal = args.question.strip(), args.goal.strip()
    if asking and not (target / "project.md").exists():
        say("The project's question and goal go into project.md; a session needs both to start.")
        question = question or ask_optional("The question of the project, in one line:")
        goal = goal or ask_optional("The goal: the question in full, and what would count as an answer:")
    return question, goal


if __name__ == "__main__":
    try:
        raise SystemExit(run_main(main))
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.", file=sys.stderr)
        raise SystemExit(130) from None
