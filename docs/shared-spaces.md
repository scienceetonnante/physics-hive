# Shared spaces

A shared space puts a PhysicsHive workspace on the Hugging Face Hub, so that the leads can read and answer in a browser while the contributors run sessions in a terminal, on one machine or several. This guide covers creating and joining a space, what a session does on the Hub, the token the Space holds, editing files outside the Space, and upgrades. [Getting started](getting-started.md) walks through a first session; [The Space](the-space.md) describes the web app.


## What a space is

A space for the project `x-correction`, owned by the organisation `our-lab`, is five private repositories on the Hub:

| Repository | Type | Holds |
|---|---|---|
| `our-lab/physics-hive-x-correction` | dataset | the workspace: the lead's files and the record, as a git repository |
| `our-lab/physics-hive-x-correction-traces` | dataset | one folder per session: the exported transcript of the agents (`trace.jsonl`, with the secrets it recognises replaced by a marker) and `meta.json` (who ran the session, with which harness, models and method version, its commits, and the tokens each model used) |
| `our-lab/physics-hive-x-correction-sources` | dataset | the sources of the papers the surveys downloaded |
| `our-lab/physics-hive-x-correction-chat-debug` | dataset | reserved for the Space's assistant, which does not exist yet |
| `our-lab/physics-hive-x-correction` | Space | the web app |

The Hub keeps datasets and Spaces apart, so the workspace and the Space share the name. The research files are not stored in the Space's repository, because every push to a Space rebuilds the app.

All five are private, so only members of the owning organisation can see them. Private repositories under a personal account cannot be shared with anyone else, so a team needs one organisation (one per team, not per project). Choosing your own account as the owner works for trying a space alone; the installer warns you that nobody else will be able to see it.

On the Hub, the Space's card reads "[Physics Hive] x-correction" and shows the question of `project.md`. Each session start updates it when the question has changed.


## Create

In a new, empty folder:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh
```

`create` is the installer's default. It asks the questions listed in [Getting started](getting-started.md#1-create-the-space), makes the local workspace, creates the five repositories, pushes the first commit, deploys the Space, and prints two things: the Space's own address (`https://our-lab-physics-hive-x-correction.hf.space`), and the command for joining the space. Opened at its own address rather than on huggingface.co, the Space signs you in within the same tab.


## Join

A contributor who wants to run sessions from another machine, or a second contributor, joins the space once per checkout:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh -s -- --mode join --repo our-lab/physics-hive-x-correction
```

`create` prints this command with your repository. Joining clones the workspace into an empty folder and renders the harness files you select from the workspace's own copy of the method, so that every checkout and the Space run exactly the same prompts and scripts.

Harness files are personal: they are git-ignored, and only the research files and the method copy are shared. Two contributors may use different harnesses.

One checkout holds at most one active session. To run two sessions at once on one machine, join the space a second time in another folder.

A colleague who only reads and answers needs no checkout and installs nothing: as a member of the organisation, they sign in to the Space.


## What happens in a session

`/session-run` runs the steps below; the scripts in `.physics-hive/scripts/` do every git and Hub operation, so the agents never run git against the Hub themselves.

1. **Start.** `session.py start` first commits the uncommitted edits of the lead's files and pushes them to `main`. It then claims the session by opening a draft pull request on the workspace repository; the pull request's number is the session number (`S12`). It puts the checkout on the branch `session/S12`, made from the latest `main`, downloads the paper sources, and prints what the leads sent since the previous session started: answers, ticked and unticked lines, notes, edits of `project.md`, `conventions.md` and `draft.tex`, changed ratings. It also lists the other open sessions.
2. **Apply.** The coordinator applies the ticked lines, one commit per debrief.
3. **Brief.** It asks any question left unanswered, then proposes a brief, which the contributor confirms. If another open session works on the same step, it says so and lets the contributor decide. The brief is committed, copied into the pull request's description, and the pull request is renamed after the session's goal.
4. **Work.** The session works on its own within its budget (20 dispatches by default) and stops when the goal is reached, the budget is spent, four dispatches in a row add nothing, or the work shows that `project.md` should change.
5. **End.** It writes the note and the debrief. `session.py end` adds *Changed by this session* to the debrief from git, rebases on `main` if `main` has moved, checks the workspace, pushes the branch to the pull request, uploads the paper sources and the trace, and merges the pull request.

A merge adds to the record and endorses nothing: what the leads endorse is what is in the draft. That is why sessions merge without waiting for anyone.

**Session numbers.** The session number is the number of the pull request, and the Hub numbers the pull requests and discussions of a repository in one sequence. So session numbers can skip: an abandoned session keeps its number with its closed pull request, and the pull request of a method upgrade also takes one.

The Hub squashes a pull request into one commit when it merges it. The session's own commits stay reachable through the pull request (`refs/pr/<n>`), and the trace's `meta.json` lists them with the merge commit.

**Parallel sessions.** Two contributors, or two checkouts, can run sessions at the same time: every card and artefact is its own file with an ID that contains the session number, so they never collide. Two sessions that edit the same file (`draft.tex`, `conventions.md`, `literature/overview.md`) do conflict: the second to end stops at the rebase, with nothing pushed, and shows the conflict.


### Traces and secrets

Before `session.py end` uploads a trace, `export_trace.py` replaces the secrets it recognises with a marker such as `[REDACTED:huggingface-token]`: tokens of known formats (Hugging Face, Anthropic, OpenAI, GitHub, AWS access keys, private key blocks, JWTs, signatures in URLs and credentials in HTTP Authorization headers), and the values of the environment variables whose name contains `TOKEN`, `KEY` or `SECRET`, along with the Hub token the scripts use. The number of replacements is recorded in the trace's `meta.json`. This reduces the risk that a trace leaks a secret; it does not guarantee that a trace holds none. A secret in another format, one shorter than 12 characters, one printed in pieces or encoded, or one held in a variable with another name, is not recognised. Every member of the organisation can read the traces dataset, so read the traces before you make it public.

A local workspace exports and uploads no trace, and records no token counts.


## The Space's token

The Space reads the workspace and saves the leads' edits with its own copy of a token, the Space secret `HF_TOKEN`. Saves are commits made with this token; the Space names the signed-in user in each commit's message.

Which token `create` stores:

- If the environment variable `PHYSICS_HIVE_SPACE_TOKEN` is set, that token. `create` checks it before creating anything.
- Otherwise, when it is asking questions, the installer asks whether to give the Space your Hugging Face login token. Without questions (`--yes`), it gives it.
- `--space-token env|mine|none` overrides this: the token in `PHYSICS_HIVE_SPACE_TOKEN`, your login token, or none (you then set the secret `HF_TOKEN` yourself in the Space's settings, and until then the Space cannot read the workspace).

**What can reach the token.** The Space runs code that comes from the workspace: it imports the scripts of the workspace's own method copy (`.physics-hive/scripts/`), and it compiles the workspace's LaTeX (the draft and the notes) to PDF, and LaTeX can read any file the Space can read. So anyone who can commit to the workspace repository can obtain what the Space holds, in particular its token. That includes an agent that follows instructions planted in a paper it read. By default, that token is the creator's own login token, which can do everything the creator can do on the Hub. For a team, and for any project whose agents read papers from outside, give the Space a dedicated token limited to the organisation's repositories, as described below. Such a token, if it leaked, would still give read and write access to those repositories, but not to the rest of your account. [SECURITY.md](../SECURITY.md) lists what a shared space trusts.

**A dedicated token.** To give new Spaces a token of their own rather than your login token (recommended), set the variable in your shell profile, for example `export PHYSICS_HIVE_SPACE_TOKEN=hf_...` in `~/.zshrc`. When you work from a clone of this repository, the `.env` at its root also works (it is git-ignored, and read only by `./init-physics-hive.sh`). Do not put the token in a `.env` file inside a workspace: the workspace is pushed to the Hub.

Make it a fine-grained token (Hugging Face → Settings → Access Tokens) with only these permissions:

- in the section for the organisation that owns your projects: read and write access to the contents of all its repositories;
- *Make calls to Inference Providers*, for the Space's assistant once it exists.

If you rotate the token, update the secret `HF_TOKEN` in each Space's settings. The variable only applies to Spaces created after it is set.


## Editing files outside the Space

The lead's files are `project.md`, `conventions.md`, `draft.tex`, `literature/seeds.md`, `literature/ratings.yaml` and the debriefs. You may edit them in your checkout rather than in the Space. The next session start commits your edits as yours and pushes them to `main`. To publish them now, run:

```bash
uv run .physics-hive/scripts/session.py save
```

or ask the coordinator to. `save` refuses when other files have uncommitted changes. If `main` moved on the Hub in the meantime, it rebases your commits first, and on a conflict it stops with nothing pushed.

For other git commands against the Hub, `hubgit.py` runs git with your Hub token without storing it:

```bash
uv run .physics-hive/scripts/hubgit.py <git arguments>
```

The token never goes into `.git/config`: the scripts pass it in a header for each git command.


## Upgrading a workspace

Each workspace keeps its own copy of the method in `.physics-hive/`, with its version in `project.toml`. A new release of PhysicsHive does not change existing workspaces until you upgrade them. Inside the workspace:

```bash
curl -LsSf https://raw.githubusercontent.com/scienceetonnante/physics-hive/master/install.sh | sh -s -- --upgrade
```

- In a **local workspace**, this replaces the method copy, re-renders the harness files, and commits.
- In a **shared space**, it opens a pull request on the workspace repository and prints its address. Merge it on the Hub. Then, in each checkout whose harness files come from the older version, the next session start moves the checkout to the new `main`, renders the harness files again, and asks you to restart your harness and run `/session-run` again. The first session start after the merge also uploads the new app to the Space.

The upgrade refuses while the checkout has uncommitted changes or an active session, and says so when the workspace already has the downloaded version. It also refuses workspaces of the 0.3 format (with `problem.md` instead of `project.md`), which this method does not convert. Workspaces created with Physics Intern are not supported.


## Removing a project

There is no command for this in a workspace. The five repositories can be deleted from their settings pages on the Hub. From a clone of this repository, `uv run tests/clean_hub.py our-lab/physics-hive-x-correction` deletes the four datasets and the Space, after asking; it was written to clean up test projects.
