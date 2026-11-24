"""Hugging Face Hub operations for shared spaces.

A shared space is a private dataset repository holding the research files
(the workspace), three more private dataset repositories (traces, sources,
chat_debug) and a private Space, all owned by one organisation. The
repositories of project <name> are named physics-hive-<name> (the workspace and
the Space, which the Hub keeps apart) and physics-hive-<name>-traces, -sources
and -chat-debug. The Space's card on the Hub is titled "[Physics Hive] <name>"
and shows the question of project.md, which `open_session` updates when the
lead changes it. Each dataset repository gets a card (its README.md) at
creation, which says what it holds and carries the tag physics-hive; nothing
in the method reads these cards, and spaces created without them work the
same. A session is a
pull request on the workspace repository: the scripts open it as a draft (its
number is the session number), push the session branch to `refs/pr/<n>`, mark
it ready and merge it. The Hub squashes a pull request into one commit when it
merges it, so the trace's meta.json records the pull request number, the
session's own commits (still reachable through `refs/pr/<n>`) and the merge
commit.

Git talks to the Hub with the token of `hf auth login`, passed in an HTTP
header for each command; it is never written to the repository's config.
The session commands never write that config at all, because a harness's
sandbox may refuse it (Claude Code's does): branches are created with
`--no-track`, and every push names its target.
The Space gets its own copy of a token, the secret HF_TOKEN: the one in the
environment variable PHYSICS_HIVE_SPACE_TOKEN if it is set, else the
creator's login token.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path

# common before huggingface_hub: importing common sets the environment that huggingface_hub reads on import.
from common import INSTALL_COMMAND, ScriptError, git, git_out, now_iso, rendered_version, rerender, say, warn
from huggingface_hub import HfApi, get_token  # isort: skip
from huggingface_hub import constants as hf_constants  # isort: skip
from huggingface_hub.errors import EntryNotFoundError  # isort: skip
from huggingface_hub.utils import HfHubHTTPError, disable_progress_bars  # isort: skip

DATASET = "dataset"
SPACE_TOKEN_ENV = "PHYSICS_HIVE_SPACE_TOKEN"  # token stored in a new Space, instead of the creator's login token
REPO_PREFIX = "physics-hive-"  # the repositories of project <name> are <org>/physics-hive-<name>[-traces, ...]
CARD_TITLE = "[Physics Hive] {name}"
CARD_DESCRIPTION_LIMIT = 60  # the Hub refuses a longer short_description
CARD_TAG = "physics-hive"  # in the metadata of every repository of a space, so that spaces can be found on the Hub
PROJECT_URL = "https://github.com/scienceetonnante/physics-hive"
SPACE_STAMP = "METHOD"  # in the Space repository: the stamp of the app it runs (space_app_stamp)

disable_progress_bars()  # the scripts' output is read by agents; keep it to what they need


# ----- identity and git authentication -----

# `hf` comes with huggingface_hub, which the scripts install for themselves; `uv tool run` runs it without installing it.
LOGIN_COMMAND = ("`hf auth login`, or `uv tool run --from huggingface_hub hf auth login` if the `hf` command is not "
                 "installed")
LOGIN_HINT = f"you are not logged in to Hugging Face. Log in first, in a terminal: {LOGIN_COMMAND}"


def api() -> HfApi:
    if not get_token():
        raise ScriptError(LOGIN_HINT)
    return HfApi()


def whoami() -> dict:
    try:
        return api().whoami()
    except HfHubHTTPError as exc:
        if os.environ.get("HF_TOKEN"):
            # huggingface_hub uses HF_TOKEN before the login token, so `hf auth login` alone changes nothing.
            raise ScriptError(
                f"the Hub refused the token in the environment variable HF_TOKEN ({exc}). It takes precedence over "
                "`hf auth login`: replace it with a valid token where your shell sets it, or remove it, then "
                "restart your harness so that it reads the new environment") from exc
        raise ScriptError(f"could not identify you on the Hub ({exc}). Log in again in a terminal: "
                          f"{LOGIN_COMMAND}") from exc


def username() -> str:
    return whoami()["name"]


def owners() -> list[str]:
    """Who can own a new project: the organisations you belong to, then your own account."""
    me = whoami()
    return sorted(org["name"] for org in me.get("orgs", [])) + [me["name"]]


def repo_url(repo_id: str) -> str:
    return f"{hf_constants.ENDPOINT}/datasets/{repo_id}"


def git_env() -> dict:
    """Environment that makes git send the Hub token, without storing it anywhere."""
    token = get_token()
    if not token:
        raise ScriptError(LOGIN_HINT)
    auth = base64.b64encode(f"{username()}:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"http.{hf_constants.ENDPOINT}/.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}",
    }


def hub_repos(ws) -> dict:
    hub = ws.hub
    if not hub.get("workspace"):
        raise ScriptError("project.toml has no [hub] workspace; this is a local workspace")
    return hub


def pr_url(repo_id: str, number: int) -> str:
    return f"{repo_url(repo_id)}/discussions/{number}"


# ----- create and join -----


def create_shared(target: Path, org: str, name: str, harnesses: list[str], chat_model: str, space_token: str,
                  *, create_local, first_commit, regen, version: str) -> None:
    me = whoami()
    user = me["name"]
    if org == user:
        warn("note: a private repository under a personal account cannot be shared with anyone else; use an "
             "organisation for a team. Creating the space under your account, for trying shared mode alone.")
    elif org not in {o["name"] for o in me.get("orgs", [])}:
        raise ScriptError(f"you are not a member of the organisation {org!r}; private repositories under a "
                          "personal account cannot be shared, so the project needs an organisation")
    secret = space_secret(space_token)
    repos = repo_names(org, name)
    hf = api()
    for key, repo_id in repos.items():
        kind = "space" if key == "space" else DATASET
        if hf.repo_exists(repo_id, repo_type=kind):
            raise ScriptError(f"{kind} {repo_id} already exists; choose another project name")

    create_local(target, harnesses, chat_model, hub=repos, leads=[user])
    for key in ("workspace", "traces", "sources", "chat_debug"):
        hf.create_repo(repos[key], repo_type=DATASET, private=True)
        say(f"Created private dataset {repos[key]}")
    upload_dataset_cards(repos)

    env = git_env()
    git(target, "init", "-q", "-b", "main")
    git(target, "remote", "add", "origin", repo_url(repos["workspace"]))
    git(target, "fetch", "-q", "origin", env=env)
    git(target, "reset", "-q", "origin/main")
    # The Hub's default .gitattributes routes many extensions to LFS; a workspace
    # holds small text files and plain git is simpler for every contributor.
    git(target, "rm", "-q", "--cached", "--ignore-unmatch", ".gitattributes")
    # The workspace's card on the Hub, staged so that the first commit includes it. No script reads it.
    (target / "README.md").write_text(dataset_card("workspace", repos), encoding="utf-8")
    git(target, "add", "--", "README.md")
    first_commit(target, f"Initialize PhysicsHive workspace (shared space {repos['workspace']})")
    git(target, "push", "-q", "origin", "HEAD:main", env=env)
    git(target, "branch", "-q", "--set-upstream-to=origin/main", check=False)
    regen(target)
    say(f"Pushed the first commit to {repo_url(repos['workspace'])}")

    deploy_space(target, repos, secret)
    say("")
    say(f"Shared space created: {repos['workspace']} (method {version}). You are its lead ([people] leads in project.toml).")
    say(f"  Workspace: {repo_url(repos['workspace'])}")
    say(f"  Space:     {hf_constants.ENDPOINT}/spaces/{repos['space']}")
    host = space_host(repos["space"])
    if host:
        say(f"             {host} (the Space alone, outside the Hub's page: sign-in stays in the same tab)")
    say("To run sessions from another machine (yours or a colleague's), join with:")
    say(f"  {INSTALL_COMMAND} -s -- --mode join --repo {repos['workspace']}")
    say("Colleagues who only read and answer need nothing installed: they sign in to the Space.")


def repo_names(org: str, name: str) -> dict:
    """The repositories of project `name`: the workspace and the Space share one name (the Hub keeps them apart)."""
    base = f"{org}/{REPO_PREFIX}{name.removeprefix(REPO_PREFIX)}"
    return {"workspace": base, "traces": f"{base}-traces", "sources": f"{base}-sources",
            "chat_debug": f"{base}-chat-debug", "space": base}


def project_name(repo_id: str) -> str:
    """The project's name from its workspace repository: org/physics-hive-x gives x."""
    return repo_id.split("/")[-1].removeprefix(REPO_PREFIX)


DATASET_CARDS = {
    "workspace": (
        "This dataset repository is the workspace of the PhysicsHive project **{name}**: the research "
        "files that the agents and the lead write. `project.md` states the question and the plan, "
        "`draft.tex` holds the best current state of the research, the folders `claims/`, `derivations/`, "
        "`computations/`, `critiques/` and `literature/` hold the record behind it, and `sessions/` holds each "
        "session's brief, note and debrief. Each session is a pull request on this repository.\n\n"
        "The project's other repositories:\n\n"
        "- the Space [{space}]({space_url}), the web app where the lead reads each session and answers it;\n"
        "- [{traces}]({traces_url}), the agents' transcripts, one folder per session;\n"
        "- [{sources}]({sources_url}), the source files of the papers the agents downloaded.\n"),
    "traces": (
        "This dataset repository holds the agent traces of the PhysicsHive project **{name}**, whose "
        "workspace is [{workspace}]({workspace_url}). Each folder `S<n>/` is one session: `trace.jsonl` is the "
        "record the agents' harness kept of it (prompts, responses, tool calls, and the model's reasoning when "
        "the harness stores it), and `meta.json` says who ran it, with which harness, models and method version, "
        "which commits it made and how many tokens each model used. `session.py end` uploads them.\n\n"
        "Before the upload, the export replaces the secrets it recognises (tokens of known formats, and the "
        "values of the environment's token variables) with a marker such as `[REDACTED:huggingface-token]`. "
        "This lowers the risk but does not guarantee that a trace holds no secret: read the traces before you "
        "make this repository public.\n"),
    "sources": (
        "This dataset repository holds the source files (LaTeX, or PDF when there is no source) of the "
        "papers that the agents of the PhysicsHive project **{name}** downloaded, one folder per paper. The "
        "workspace, [{workspace}]({workspace_url}), keeps them out of git because of their size; each session "
        "start downloads them into `literature/sources/`. The papers keep their own licences: check them before "
        "you make this repository public.\n"),
    "chat_debug": (
        "This dataset repository belongs to the PhysicsHive project **{name}**, whose workspace is "
        "[{workspace}]({workspace_url}). It is reserved for the debugging logs of a chat assistant in the "
        "project's Space. The current version of PhysicsHive does not write to it.\n"),
}
DATASET_TITLES = {"workspace": "", "traces": " (traces)", "sources": " (paper sources)", "chat_debug": " (chat logs)"}


def dataset_card(key: str, repos: dict) -> str:
    """The README.md of one dataset repository of a space: what it holds, which project it belongs to, and
    the tag that lets the Hub's search find spaces. The dataset viewer is off: these files are not tables."""
    name = project_name(repos["workspace"])
    title = CARD_TITLE.format(name=name) + DATASET_TITLES[key]
    fields = {"name": name}
    for k in ("workspace", "traces", "sources", "space"):
        fields[k] = repos.get(k, "")
        fields[f"{k}_url"] = f"{hf_constants.ENDPOINT}/spaces/{fields[k]}" if k == "space" else repo_url(fields[k])
    body = DATASET_CARDS[key].format(**fields)
    return (f"---\npretty_name: {json.dumps(title, ensure_ascii=False)}\ntags:\n- {CARD_TAG}\nviewer: false\n---\n\n"
            f"# {title}\n\n{body}\nMade with [PhysicsHive]({PROJECT_URL}), with which a small team of scientists "
            "steers AI coding agents on one problem in theoretical physics or mathematics.\n")


def upload_dataset_cards(repos: dict) -> None:
    """Give the traces, sources and chat_debug repositories their card. A failure only warns: the cards are
    for people who open the repositories on the Hub, and nothing in the method reads them."""
    hf = api()
    for key in ("traces", "sources", "chat_debug"):
        if not repos.get(key):
            continue
        try:
            hf.upload_file(path_or_fileobj=dataset_card(key, repos).encode("utf-8"), path_in_repo="README.md",
                           repo_id=repos[key], repo_type=DATASET, commit_message="Describe this repository")
        except (HfHubHTTPError, OSError) as exc:
            warn(f"warning: could not write the card of {repos[key]} ({exc}); the space works without it.")


def space_secret(choice: str) -> dict | None:
    """The token the new Space will hold: from SPACE_TOKEN_ENV ("env"), the login token ("mine"), or none.

    Checked before anything is created, so that a bad token stops create early.
    """
    if choice == "none":
        return None
    if choice == "mine":
        return {"token": get_token(), "label": "your login token", "env": False}
    token = os.environ.get(SPACE_TOKEN_ENV, "").strip()
    if not token:
        raise ScriptError(f"{SPACE_TOKEN_ENV} is not set")
    try:
        owner = HfApi(token=token).whoami()
    except HfHubHTTPError as exc:
        raise ScriptError(f"the Hub refused the token in {SPACE_TOKEN_ENV} ({exc}); replace it or unset it") from exc
    name = owner.get("auth", {}).get("accessToken", {}).get("displayName")
    label = f"the token {name!r} of {owner['name']}" if name else f"a token of {owner['name']}"
    return {"token": token, "label": f"{label}, from {SPACE_TOKEN_ENV}", "env": True}


def deploy_space(target: Path, repos: dict, secret: dict | None) -> None:
    """Create the private Space, upload the app from the method copy, and store its token."""
    app = target / ".physics-hive" / "space"
    hf = api()
    if not (app / "app.py").is_file():
        warn("The method copy has no Space app (.physics-hive/space/); skipping the Space.")
        return
    hf.create_repo(repos["space"], repo_type="space", space_sdk="docker", private=True)
    upload_space_app(app, repos, project_question(target), "Deploy the PhysicsHive Space")
    hf.add_space_variable(repos["space"], "PHYSICS_HIVE_WORKSPACE", repos["workspace"])
    hf.add_space_variable(repos["space"], "CHAT_DEBUG", "0")
    say(f"Created private Space {repos['space']}")
    if secret is None:
        say("Add a Space secret HF_TOKEN in the Space settings: a token that can read and write the workspace")
        say(f"repository {repos['workspace']}. Until then the Space cannot read the workspace.")
        return
    hf.add_space_secret(repos["space"], "HF_TOKEN", secret["token"],
                        description="Token the Space uses to read the workspace and save the lead's edits")
    say(f"The Space secret HF_TOKEN holds {secret['label']}. The Space reads the workspace and saves edits with it.")
    if not secret["env"]:
        say(f"To give new Spaces a dedicated token instead of yours, set {SPACE_TOKEN_ENV} before creating them.")
        return
    try:
        HfApi(token=secret["token"]).repo_info(repos["workspace"], repo_type=DATASET)
    except HfHubHTTPError:
        warn(f"warning: the token in {SPACE_TOKEN_ENV} cannot read {repos['workspace']}, so the Space cannot show it. "
             f"Give that token read and write access to the repositories of {repos['workspace'].split('/')[0]}, or "
             "replace the Space secret HF_TOKEN in the Space settings.")


def project_question(root: Path) -> str | None:
    """The question of project.md (its title), or None while it is not written."""
    from human import parse_project

    path = root / "project.md"
    doc = parse_project(path.read_text(encoding="utf-8")) if path.is_file() else None
    return doc.title if doc and not doc.is_template else None


def card_line(text: str, limit: int = CARD_DESCRIPTION_LIMIT) -> str:
    """The text on one line of at most `limit` characters, cut between words."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:") + "…"


def space_card(readme: str, name: str, question: str | None) -> str:
    """The Space's README.md with its card: the title names the project, the description is its question.

    Without a question, an existing description is kept.
    """
    m = re.match(r"---\n(.*?)\n---\n", readme, re.S)
    if not m:
        raise ScriptError("the Space's README.md has no metadata block")
    fields = {"title": CARD_TITLE.format(name=name)}
    if question:
        fields["short_description"] = card_line(question)
    lines = [line for line in m.group(1).splitlines() if line.split(":", 1)[0].strip() not in fields]
    lines[:0] = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items()]
    return "---\n" + "\n".join(lines) + "\n---\n" + readme[m.end():]


def space_app_stamp(app: Path) -> str:
    """What identifies a Space app: the method version of its copy and a hash of its files ('0.5.4 1a2b…')."""
    digest = hashlib.sha256()
    for path in sorted(p for p in app.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                       and p.suffix != ".pyc" and p.name != ".DS_Store"):
        digest.update(path.relative_to(app).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    version_file = app.parent / "VERSION"
    version = version_file.read_text().strip() if version_file.is_file() else "?"
    return f"{version} {digest.hexdigest()[:16]}"


def upload_space_app(app: Path, repos: dict, question: str | None, message: str) -> None:
    """Upload the Space app from a method copy, with the project's card in its README.md and its stamp in
    SPACE_STAMP, in one commit."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "space"
        shutil.copytree(app, folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        readme = folder / "README.md"
        name = project_name(repos["workspace"])
        readme.write_text(space_card(readme.read_text(encoding="utf-8"), name, question), encoding="utf-8")
        (folder / SPACE_STAMP).write_text(space_app_stamp(app) + "\n", encoding="utf-8")
        api().upload_folder(repo_id=repos["space"], repo_type="space", folder_path=folder, commit_message=message)


def sync_space(root: Path, repos: dict) -> None:
    """Make the Space run the app of this checkout's method copy, if it runs another one.

    The Space reads the workspace with the scripts of the method copy on main, so its app must come from the
    same copy: after an upgrade is merged, the next session start uploads it. Only the session start calls
    this, because it has just checked out origin/main; another checkout may be behind main and would put an
    older app back. A Space deployed before stamps existed has none, and gets the app once. A failure only warns.
    """
    space = repos.get("space")
    app = root / ".physics-hive" / "space"
    if not space or not (app / "app.py").is_file():
        return
    stamp = space_app_stamp(app)
    version = stamp.split()[0]
    try:
        try:
            deployed = Path(api().hf_hub_download(space, SPACE_STAMP, repo_type="space")).read_text().strip()
        except EntryNotFoundError:
            deployed = ""
        if deployed == stamp:
            return
        upload_space_app(app, repos, project_question(root), f"Run the Space app of method {version}")
        say(f"The Space {space} now runs the app of method {version}; it rebuilds, which takes a few minutes.")
    except (HfHubHTTPError, EntryNotFoundError, OSError, ScriptError) as exc:
        warn(f"warning: could not update the app of the Space {space} ({exc}); it keeps the app it has.")


def space_host(space: str) -> str | None:
    """The Space's own address (https://<org>-<name>.hf.space), or None if the Hub does not give it."""
    try:
        return getattr(api().space_info(space), "host", None)
    except (HfHubHTTPError, OSError):
        return None


def update_space_card(repos: dict, question: str | None) -> None:
    """Show the question on the Space's card if it changed. A commit to the Space restarts it, so only then."""
    space = repos.get("space")
    if not space or not question:
        return
    hf = api()
    try:
        readme = Path(hf.hf_hub_download(space, "README.md", repo_type="space")).read_text(encoding="utf-8")
        card = space_card(readme, project_name(repos["workspace"]), question)
        if card != readme:
            hf.upload_file(path_or_fileobj=card.encode("utf-8"), path_in_repo="README.md", repo_id=space,
                           repo_type="space", commit_message="Show the project's question on the Space card")
            say(f"The card of the Space {space} now shows the question of project.md.")
    except (HfHubHTTPError, OSError, ScriptError) as exc:
        warn(f"warning: could not update the card of the Space {space} ({exc}); the session goes on.")


def join(target: Path, repo: str, harnesses: list[str], render, regen, check_new_dir) -> None:
    hf = api()
    if not hf.repo_exists(repo, repo_type=DATASET):
        raise ScriptError(f"no dataset repository {repo} visible to you; check the name, and that you are a "
                          "member of the organisation that owns it")
    check_new_dir(target)
    if target.exists() and any(target.iterdir()):
        raise ScriptError(f"{target} is not empty; join clones the workspace into an empty folder")
    target.mkdir(parents=True, exist_ok=True)
    git(target, "clone", "-q", repo_url(repo), ".", env=git_env())
    if not ((target / "project.toml").is_file() and (target / ".physics-hive").is_dir()):
        raise ScriptError(f"{repo} is not a PhysicsHive workspace (no project.toml or .physics-hive/)")
    render(target, harnesses)
    regen(target)
    version = (target / ".physics-hive" / "VERSION").read_text().strip()
    say(f"Joined {repo} in {target} (method {version}, from the workspace's own copy).")


# ----- sessions -----


def fetch(root: Path, env: dict | None = None) -> None:
    git(root, "fetch", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main", env=env or git_env())


def push_researcher_edits(root: Path, is_researcher_path, env: dict | None = None) -> list[str]:
    """Push to main the commits of local main that are not on the Hub, if they only change the lead's files.

    They are the lead's edits, committed by `session.py`. If main moved on the Hub meanwhile (for instance
    an edit in the Space), they are rebased on it first. Returns the files pushed.
    """
    env = env if env is not None else git_env()
    fetch(root, env)
    if git_out(root, "rev-parse", "--abbrev-ref", "HEAD") != "main" or is_ancestor(root, "HEAD", "origin/main"):
        return []
    changed = [p for p in git_out(root, "diff", "--name-only", "origin/main...HEAD").splitlines() if p]
    others = [p for p in changed if not is_researcher_path(p)]
    if others:
        listing = ", ".join(others[:8]) + (", …" if len(others) > 8 else "")
        raise ScriptError(f"main has commits that are not on the Hub and change files other than the lead's "
                          f"({listing}); move them to a pull request, or drop them with "
                          "`git reset --hard origin/main`")
    if not is_ancestor(root, "origin/main"):
        proc = git(root, "rebase", "-q", "origin/main", check=False)
        if proc.returncode != 0:
            git(root, "rebase", "--abort", check=False)
            raise ScriptError(f"the lead's edits of {', '.join(changed)} conflict with changes made on the Hub "
                              f"since (for instance in the Space):\n{(proc.stderr or proc.stdout).strip()}\n"
                              "Nothing was pushed and the checkout is unchanged. Tell the contributor; resolving it "
                              "needs their decision.")
    git(root, "push", "-q", "origin", "HEAD:main", env=env)
    fetch(root, env)
    say(f"Pushed your edits of {', '.join(changed)} to main on the Hub.")
    return changed


def open_session(ws, root: Path, harness: str, model: str) -> dict:
    repos = hub_repos(ws)
    user = username()
    env = git_env()
    fetch(root, env)
    upstream = git(root, "show", "origin/main:.physics-hive/VERSION", check=False).stdout.strip()
    rendered = rendered_version(root)
    if upstream and rendered and upstream != rendered:
        git(root, "checkout", "-q", "--no-track", "-B", "main", "origin/main")
        rerender(root)
        raise ScriptError(
            f"the method on main is now version {upstream}, but this harness was loaded with prompts from "
            f"{rendered}. This checkout is now on the latest main and its harness files are re-rendered: "
            "restart your harness in this folder, then start the session again."
        )
    hf = api()
    description = (f"Session claimed by **{user}** ({harness}, {model}) on {now_iso()}.\n\n"
                   "The brief will replace this text once the contributor confirms it.")
    pr = hf.create_pull_request(repos["workspace"], title=f"[draft] session by {user}",
                                description=description, repo_type=DATASET)
    number = pr.num
    session = f"S{number}"
    hf.rename_discussion(repos["workspace"], number, f"[{session}] (brief pending) by {user}", repo_type=DATASET)
    branch = f"session/{session}"
    git(root, "checkout", "-q", "--no-track", "-B", branch, "origin/main")
    base = git_out(root, "rev-parse", "origin/main")
    sync_sources_down(root, repos)
    update_space_card(repos, project_question(root))
    sync_space(root, repos)
    return {"id": session, "number": number, "pr": number, "pr_url": pr_url(repos["workspace"], number),
            "branch": branch, "base": base, "operator": user}


# Files of the sources repository that are not paper sources: the Hub's .gitattributes and the repository's card.
# As ignore patterns they match only these paths at the root, so a paper's own README.md is still downloaded.
SOURCES_NOT_PAPERS = [".gitattributes", "README.md"]


def sync_sources_down(root: Path, repos: dict) -> None:
    """Download the paper sources into literature/sources/.

    The repository's files are listed first: when it holds no paper yet, nothing is downloaded, because
    snapshot_download would print a warning that every file was ignored."""
    if not repos.get("sources"):
        return
    try:
        from huggingface_hub import snapshot_download

        files = api().list_repo_files(repos["sources"], repo_type=DATASET)
        if not [path for path in files if path not in SOURCES_NOT_PAPERS]:
            return
        snapshot_download(repos["sources"], repo_type=DATASET, local_dir=root / "literature" / "sources",
                          ignore_patterns=SOURCES_NOT_PAPERS)
    except Exception as exc:  # an empty or unreachable sources repo must not block a session
        warn(f"note: could not download paper sources from {repos['sources']} ({type(exc).__name__}); continuing")


def sync_sources_up(root: Path, repos: dict, session: str) -> None:
    folder = root / "literature" / "sources"
    files = [p for p in folder.rglob("*") if p.is_file() and ".cache" not in p.parts
             and p.name != ".gitattributes" and p.relative_to(folder).as_posix() != "README.md"] if folder.is_dir() else []
    if not repos.get("sources") or not files:
        return
    api().upload_folder(repo_id=repos["sources"], repo_type=DATASET, folder_path=folder,
                        commit_message=f"[{session}] paper sources",
                        ignore_patterns=[".cache/*", "*.lock", ".gitattributes", "README.md"])
    say(f"Uploaded paper sources to {repos['sources']}.")


def push_pr(root: Path, number: int, env: dict | None = None) -> None:
    git(root, "push", "-q", "--force", "origin", f"HEAD:refs/pr/{number}", env=env or git_env())


def publish_brief(ws, root: Path, active: dict, brief_text: str, goal: str) -> None:
    repos = hub_repos(ws)
    push_pr(root, active["pr"])
    hf = api()
    hf.rename_discussion(repos["workspace"], active["pr"], f"[{active['id']}] {goal}"[:200], repo_type=DATASET)
    details = hf.get_discussion_details(repos["workspace"], active["pr"], repo_type=DATASET)
    first = next((e for e in details.events if e.type == "comment"), None)
    footer = f"\n\n---\nContributor: {active['operator']} · harness: {active['harness']} · model: {active['model']}\n"
    if first is not None:
        hf.edit_discussion_comment(repos["workspace"], active["pr"], first.id, brief_text + footer, repo_type=DATASET)


def is_ancestor(root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    return git(root, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


def rebase_on_main(root: Path, env: dict) -> bool:
    """Rebase the session branch on the latest main. Returns True if it moved."""
    fetch(root, env)
    if is_ancestor(root, "origin/main"):
        return False
    proc = git(root, "rebase", "-q", "origin/main", check=False)
    if proc.returncode != 0:
        git(root, "rebase", "--abort", check=False)
        raise ScriptError("the session branch does not rebase cleanly on main (another session changed the "
                          f"same files):\n{(proc.stderr or proc.stdout).strip()}\nThe branch is unchanged. "
                          "Tell the contributor; resolving it needs a human decision.")
    say("Rebased the session branch on the latest main.")
    return True


def end_session(root: Path, active: dict, merge: bool, finish) -> None:
    """Rebase on main, finish the session (debrief section, check), push, upload the trace, merge."""
    from cards import Workspace

    from common import clear_active
    from export_trace import Redactor, export
    from regen import regenerate

    ws = Workspace(root)
    repos = hub_repos(ws)
    hf = api()
    env = git_env()
    number, session = active["pr"], active["id"]

    status = hf.get_discussion_details(repos["workspace"], number, repo_type=DATASET).status
    if status == "closed":
        raise ScriptError(f"pull request #{number} was closed on the Hub; abort this session with `session.py abort`")

    rebase_on_main(root, env)
    base = git_out(root, "rev-parse", "origin/main")
    finish(root, base, session)
    push_pr(root, number, env)
    say(f"Pushed the session branch to pull request #{number}.")
    sync_sources_up(root, repos, session)

    out = Path(tempfile.mkdtemp(prefix=f"trace-{session}-"))
    token = get_token()
    try:
        trace = export(active["harness"], root, active["started"], out / session, secrets=[token])
    except Exception as exc:  # export keeps what it can; this covers the rest, so that the session still ends
        (out / session).mkdir(parents=True, exist_ok=True)
        (out / session / "trace.jsonl").write_text("")
        trace = {"records": 0, "omitted": 0, "models": [], "tokens": {}, "redactions": {},
                 "note": f"the trace of this session is missing: the export failed ({type(exc).__name__}: {exc})"}
    commits = [line.split(" ", 1) for line in
               git_out(root, "log", "--reverse", "--format=%H %s", f"{base}..HEAD").splitlines() if line.strip()]
    meta = {
        "session": session,
        "pull_request": number,
        "pull_request_url": active.get("pr_url"),
        "operator": active["operator"],
        "harness": active["harness"],
        "model": active["model"],
        "models_in_trace": trace["models"],
        "method_version": (root / ".physics-hive" / "VERSION").read_text().strip(),
        "started": active["started"],
        "ended": now_iso(),
        "commits": [{"sha": sha, "subject": subject} for sha, subject in commits],
        "commits_ref": f"refs/pr/{number}",
        "merge_commit": None,
        "trace_records": trace["records"],
        "trace_records_omitted": trace["omitted"],
        "trace_note": trace["note"],
        "tokens_by_model": trace["tokens"],
    }
    # meta.json is uploaded with the trace: its texts (commit subjects, the note) get the same cleaning, and
    # the counts cover both files.
    redactor = Redactor([token])
    meta = redactor.clean(meta)
    redactions = Counter(trace["redactions"]) + redactor.counts
    meta["trace_redactions"] = sum(redactions.values())
    meta["trace_redactions_by_kind"] = dict(sorted(redactions.items()))

    def upload_trace() -> None:
        (out / session / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        if repos.get("traces"):
            hf.upload_folder(repo_id=repos["traces"], repo_type=DATASET, folder_path=out / session,
                             path_in_repo=session, commit_message=f"[{session}] trace")

    upload_trace()
    redacted = meta["trace_redactions"]
    say(f"Uploaded the trace ({trace['records']} records) to {repos.get('traces')}/{session}."
        + (f" Secrets replaced with a marker in it: {redacted}." if redacted else "")
        + (f" Note: {meta['trace_note']}." if meta["trace_note"] else ""))

    if status == "draft":
        hf.change_discussion_status(repos["workspace"], number, "open", repo_type=DATASET)
    if not merge:
        say(f"Pull request #{number} is ready but not merged, as the brief asked: {active.get('pr_url')}")
        say("Merge it from the Hub, or run `session.py end` again to merge it from here.")
        return

    if status != "merged":
        for attempt in (1, 2):
            try:
                hf.merge_pull_request(repos["workspace"], number, repo_type=DATASET)
                break
            except HfHubHTTPError as exc:
                if attempt == 2:
                    raise ScriptError(f"the Hub refused to merge pull request #{number}: {exc}") from exc
                if rebase_on_main(root, env):
                    finish(root, git_out(root, "rev-parse", "origin/main"), session)
                    push_pr(root, number, env)
    fetch(root, env)
    meta["merge_commit"] = git_out(root, "rev-parse", "origin/main")
    upload_trace()

    git(root, "checkout", "-q", "--no-track", "-B", "main", "origin/main")
    git(root, "branch", "-q", "--set-upstream-to=origin/main", check=False)
    clear_active(root)
    regenerate(root)
    shutil.rmtree(out, ignore_errors=True)
    say(f"Session {session} merged into main as {meta['merge_commit'][:12]} (pull request #{number}). "
        "This checkout is back on main.")


def abort_session(root: Path, active: dict) -> None:
    from cards import Workspace

    repos = hub_repos(Workspace(root))
    try:
        api().change_discussion_status(repos["workspace"], active["pr"], "closed", repo_type=DATASET)
    except HfHubHTTPError as exc:
        warn(f"note: could not close pull request #{active['pr']} ({exc}); close it on the Hub")
    if git(root, "status", "--porcelain", check=False).stdout.strip():
        warn("note: uncommitted changes stay in the working tree")
    else:
        fetch(root)
        git(root, "checkout", "-q", "--no-track", "-B", "main", "origin/main")
    say(f"Closed pull request #{active['pr']}. The branch {active['branch']} stays in this checkout.")


def shared_waiting(ws, root: Path, active: dict) -> list[tuple[str, list[str]]]:
    """Other open sessions (their pull requests), so that the coordinator can avoid overlapping briefs."""
    from cards import split_front_matter

    repos = hub_repos(ws)
    hf = api()
    others = []
    try:
        discussions = sorted(hf.get_repo_discussions(repos["workspace"], repo_type=DATASET,
                                                     discussion_type="pull_request"),
                             key=lambda d: d.num, reverse=True)
    except HfHubHTTPError as exc:
        return [("Other open sessions", [f"(could not list them: {exc})"])]
    for disc in discussions[:30]:
        if disc.num == active.get("pr") or disc.status not in ("draft", "open"):
            continue
        if not disc.title.startswith((f"[S{disc.num}]", "[draft] session")):
            continue
        goal = ""
        try:
            details = hf.get_discussion_details(repos["workspace"], disc.num, repo_type=DATASET)
            first = next((e for e in details.events if e.type == "comment"), None)
            meta, _ = split_front_matter((first.content or "") if first else "")
            goal = f" — {meta['goal']}" if meta.get("goal") else ""
        except Exception:
            pass
        others.append(f"#{disc.num} {disc.title} ({disc.status}){goal}")
    return [("Other open sessions", others)]


# ----- upgrades -----


def upgrade_shared(target: Path, old: str, new: str, copy_method, harnesses: list[str]) -> None:
    from cards import Workspace

    repos = hub_repos(Workspace(target))
    env = git_env()
    fetch(target, env)
    previous = git_out(target, "rev-parse", "--abbrev-ref", "HEAD")
    # The upgrade is made on main as it is on the Hub, without a local branch (deleting one writes .git/config,
    # which Claude Code's sandbox refuses); its commit is kept by the pull request.
    git(target, "checkout", "-q", "--detach", "origin/main")
    copy_method(target)
    toml = (target / "project.toml").read_text()
    import re

    toml = re.sub(r'(physics_hive_version\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{new}"', toml)
    (target / "project.toml").write_text(toml)
    git(target, "add", "-A", "--", ".physics-hive", "project.toml")
    if not git_out(target, "diff", "--cached", "--name-only"):
        git(target, "checkout", "-q", previous)
        say(f"main on the Hub already has this copy of the method ({new}); there is nothing to upgrade.")
        return
    git(target, "commit", "-q", "-m", f"Upgrade the method copy from {old} to {new}")
    # The pull request is opened only now, so that an upgrade that stops above leaves none behind.
    hf = api()
    pr = hf.create_pull_request(repos["workspace"], title=f"Upgrade the method from {old} to {new}",
                                description="Replaces .physics-hive/ with a newer copy of the method. "
                                            "Merge it, then re-render in every checkout with init.",
                                repo_type=DATASET)
    push_pr(target, pr.num, env)
    hf.change_discussion_status(repos["workspace"], pr.num, "open", repo_type=DATASET)
    git(target, "checkout", "-q", previous)
    say(f"Opened pull request #{pr.num} to upgrade the method: {pr_url(repos['workspace'], pr.num)}")
    say("Merge it from the Hub, then pull main and run init inside each checkout to re-render. The Space switches "
        "to the new app at the next session start.")
