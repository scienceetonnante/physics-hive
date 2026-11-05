"""Hugging Face Hub operations for shared spaces.

A shared space is a private dataset repository holding the research files
(the workspace), three more private dataset repositories (traces, sources,
chat_debug) and a private Space, all owned by one organisation. The
repositories of project <name> are named physics-hive-<name> (the workspace and
the Space, which the Hub keeps apart) and physics-hive-<name>-traces, -sources
and -chat-debug. The Space's card on the Hub is titled "[Physics Hive] <name>"
and shows the question of project.md, which `open_session` updates when the
researcher changes it. A session is a
pull request on the workspace repository: the scripts open it as a draft (its
number is the session number), push the session branch to `refs/pr/<n>`, mark
it ready and merge it. The Hub squashes a pull request into one commit when it
merges it, so the trace's meta.json records the pull request number, the
session's own commits (still reachable through `refs/pr/<n>`) and the merge
commit.

Git talks to the Hub with the token of `hf auth login`, passed in an HTTP
header for each command; it is never written to the repository's config.
The Space gets its own copy of a token, the secret HF_TOKEN: the one in the
environment variable PHYSICS_HIVE_SPACE_TOKEN if it is set, else the
creator's login token.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, get_token
from huggingface_hub import constants as hf_constants
from huggingface_hub.utils import HfHubHTTPError, disable_progress_bars

from common import ScriptError, git, git_out, now_iso, rendered_version, rerender, say, warn

DATASET = "dataset"
SPACE_TOKEN_ENV = "PHYSICS_HIVE_SPACE_TOKEN"  # token stored in a new Space, instead of the creator's login token
REPO_PREFIX = "physics-hive-"  # the repositories of project <name> are <org>/physics-hive-<name>[-traces, ...]
CARD_TITLE = "[Physics Hive] {name}"
CARD_DESCRIPTION_LIMIT = 60  # the Hub refuses a longer short_description

disable_progress_bars()  # the scripts' output is read by agents; keep it to what they need


# ----- identity and git authentication -----


def api() -> HfApi:
    if not get_token():
        raise ScriptError("you are not logged in to Hugging Face; run `hf auth login` first")
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
        raise ScriptError(f"could not identify you on the Hub ({exc}); run `hf auth login`") from exc


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
        raise ScriptError("you are not logged in to Hugging Face; run `hf auth login` first")
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

    env = git_env()
    git(target, "init", "-q", "-b", "main")
    git(target, "remote", "add", "origin", repo_url(repos["workspace"]))
    git(target, "fetch", "-q", "origin", env=env)
    git(target, "reset", "-q", "origin/main")
    # The Hub's default .gitattributes routes many extensions to LFS; a workspace
    # holds small text files and plain git is simpler for every operator.
    git(target, "rm", "-q", "--cached", "--ignore-unmatch", ".gitattributes")
    first_commit(target, f"Initialize PhysicsHive workspace (shared space {repos['workspace']})")
    git(target, "push", "-q", "origin", "HEAD:main", env=env)
    git(target, "branch", "-q", "--set-upstream-to=origin/main", check=False)
    regen(target)
    say(f"Pushed the first commit to {repo_url(repos['workspace'])}")

    deploy_space(target, repos, secret)
    say("")
    say(f"Shared space created: {repos['workspace']} (method {version}). You are its researcher ([people] leads in project.toml).")
    say(f"  Workspace: {repo_url(repos['workspace'])}")
    say(f"  Space:     {hf_constants.ENDPOINT}/spaces/{repos['space']}")
    host = space_host(repos["space"])
    if host:
        say(f"             {host} (the Space alone, outside the Hub's page: sign-in stays in the same tab)")
    say("To work from another checkout or machine (or, later, to add a colleague), join with:")
    say(f"  init-physics-hive.sh --mode join --repo {repos['workspace']}")
    say(f"  (or, in Claude Code or Codex, the init-physics-hive plugin command with the repository {repos['workspace']})")


def repo_names(org: str, name: str) -> dict:
    """The repositories of project `name`: the workspace and the Space share one name (the Hub keeps them apart)."""
    base = f"{org}/{REPO_PREFIX}{name.removeprefix(REPO_PREFIX)}"
    return {"workspace": base, "traces": f"{base}-traces", "sources": f"{base}-sources",
            "chat_debug": f"{base}-chat-debug", "space": base}


def project_name(repo_id: str) -> str:
    """The project's name from its workspace repository: org/physics-hive-x gives x."""
    return repo_id.split("/")[-1].removeprefix(REPO_PREFIX)


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
                        description="Token the Space uses to read the workspace and save the researcher's edits")
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


def upload_space_app(app: Path, repos: dict, question: str | None, message: str) -> None:
    """Upload the Space app from a method copy, with the project's card in its README.md, in one commit."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "space"
        shutil.copytree(app, folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        readme = folder / "README.md"
        name = project_name(repos["workspace"])
        readme.write_text(space_card(readme.read_text(encoding="utf-8"), name, question), encoding="utf-8")
        api().upload_folder(repo_id=repos["space"], repo_type="space", folder_path=folder, commit_message=message)


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


def open_session(ws, root: Path, harness: str, model: str) -> dict:
    repos = hub_repos(ws)
    user = username()
    env = git_env()
    fetch(root, env)
    branch = git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "main":
        ahead = git_out(root, "rev-list", "--count", "origin/main..HEAD")
        if ahead != "0":
            raise ScriptError(f"main has {ahead} commit(s) that are not on the Hub; push them first "
                              "(git push origin main) or move them to a pull request")
    upstream = git(root, "show", "origin/main:.physics-hive/VERSION", check=False).stdout.strip()
    rendered = rendered_version(root)
    if upstream and rendered and upstream != rendered:
        git(root, "checkout", "-q", "-B", "main", "origin/main")
        rerender(root)
        raise ScriptError(
            f"the method on main is now version {upstream}, but this harness was loaded with prompts from "
            f"{rendered}. This checkout is now on the latest main and its harness files are re-rendered: "
            "restart your harness in this folder, then start the session again."
        )
    hf = api()
    description = (f"Session claimed by **{user}** ({harness}, {model}) on {now_iso()}.\n\n"
                   "The brief will replace this text once the operator confirms it.")
    pr = hf.create_pull_request(repos["workspace"], title=f"[draft] session by {user}",
                                description=description, repo_type=DATASET)
    number = pr.num
    session = f"S{number}"
    hf.rename_discussion(repos["workspace"], number, f"[{session}] (brief pending) by {user}", repo_type=DATASET)
    branch = f"session/{session}"
    git(root, "checkout", "-q", "-B", branch, "origin/main")
    base = git_out(root, "rev-parse", "origin/main")
    sync_sources_down(root, repos)
    update_space_card(repos, project_question(root))
    return {"id": session, "number": number, "pr": number, "pr_url": pr_url(repos["workspace"], number),
            "branch": branch, "base": base, "operator": user}


def sync_sources_down(root: Path, repos: dict) -> None:
    if not repos.get("sources"):
        return
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repos["sources"], repo_type=DATASET, local_dir=root / "literature" / "sources",
                          ignore_patterns=[".gitattributes"])
    except Exception as exc:  # an empty or unreachable sources repo must not block a session
        warn(f"note: could not download paper sources from {repos['sources']} ({type(exc).__name__}); continuing")


def sync_sources_up(root: Path, repos: dict, session: str) -> None:
    folder = root / "literature" / "sources"
    files = [p for p in folder.rglob("*")
             if p.is_file() and ".cache" not in p.parts and p.name != ".gitattributes"] if folder.is_dir() else []
    if not repos.get("sources") or not files:
        return
    api().upload_folder(repo_id=repos["sources"], repo_type=DATASET, folder_path=folder,
                        commit_message=f"[{session}] paper sources",
                        ignore_patterns=[".cache/*", "*.lock", ".gitattributes"])
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
    footer = f"\n\n---\nOperator: {active['operator']} · harness: {active['harness']} · model: {active['model']}\n"
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
                          "Tell the operator; resolving it needs a human decision.")
    say("Rebased the session branch on the latest main.")
    return True


def end_session(root: Path, active: dict, merge: bool, finish) -> None:
    """Rebase on main, finish the session (debrief section, check), push, upload the trace, merge."""
    from cards import Workspace

    from common import clear_active
    from export_trace import export
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
    trace = export(active["harness"], root, active["started"], out / session)
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
        "trace_note": trace["note"],
    }

    def upload_trace() -> None:
        (out / session / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        if repos.get("traces"):
            hf.upload_folder(repo_id=repos["traces"], repo_type=DATASET, folder_path=out / session,
                             path_in_repo=session, commit_message=f"[{session}] trace")

    upload_trace()
    say(f"Uploaded the trace ({trace['records']} records) to {repos.get('traces')}/{session}."
        + (f" Note: {trace['note']}." if trace["note"] else ""))

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

    git(root, "checkout", "-q", "-B", "main", "origin/main")
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
        git(root, "checkout", "-q", "-B", "main", "origin/main")
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
    hf = api()
    pr = hf.create_pull_request(repos["workspace"], title=f"Upgrade the method from {old} to {new}",
                                description="Replaces .physics-hive/ with a newer copy of the method. "
                                            "Merge it, then re-render in every checkout with init.",
                                repo_type=DATASET)
    previous = git_out(target, "rev-parse", "--abbrev-ref", "HEAD")
    git(target, "checkout", "-q", "-B", f"upgrade/{new}", "origin/main")
    copy_method(target)
    toml = (target / "project.toml").read_text()
    import re

    toml = re.sub(r'(physics_hive_version\s*=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{new}"', toml)
    (target / "project.toml").write_text(toml)
    git(target, "add", "-A", "--", ".physics-hive", "project.toml")
    git(target, "commit", "-q", "-m", f"Upgrade the method copy from {old} to {new}")
    push_pr(target, pr.num, env)
    hf.change_discussion_status(repos["workspace"], pr.num, "open", repo_type=DATASET)
    git(target, "checkout", "-q", previous)
    say(f"Opened pull request #{pr.num} to upgrade the method: {pr_url(repos['workspace'], pr.num)}")
    say("Merge it from the Hub, then pull main and run init inside each checkout to re-render.")
