# Questions and answers

- [Which models and harnesses can I use?](#which-models-and-harnesses-can-i-use)
- [Do I need a Hugging Face account?](#do-i-need-a-hugging-face-account)
- [What stays private?](#what-stays-private)
- [What does it cost to run?](#what-does-it-cost-to-run)
- [Does it work outside theoretical physics?](#does-it-work-outside-theoretical-physics)
- [How does it differ from Physics Intern?](#how-does-it-differ-from-physics-intern)
- [Can several people work in one space?](#can-several-people-work-in-one-space)
- [Can I check how a result was obtained?](#can-i-check-how-a-result-was-obtained)
- [A script failed. What do I do?](#a-script-failed-what-do-i-do)
- [uv stops with "Failed to initialize cache"](#uv-stops-with-failed-to-initialize-cache)
- [A script cannot reach the Hub, or reports a certificate error](#a-script-cannot-reach-the-hub-or-reports-a-certificate-error)


## Which models and harnesses can I use?

Four harnesses: Claude Code, Codex CLI, OpenCode and Pi. A workspace can be rendered for several of them, and two contributors to one space may use different ones.

PhysicsHive does not choose the model: each harness uses the one it is configured with. The only session recorded in this repository, the example in [`examples/pendulum/`](../examples/pendulum/), used `claude-opus-5-5` through Claude Code; the repository records no session with another harness or model. Claude Code runs Claude models and Codex CLI runs OpenAI models; OpenCode and Pi can use many providers, including open models through Hugging Face Inference Providers. The coordinator and its sub-agents run in the same harness, so in Claude Code the authors and the reviewers are all Claude models. Every card and every trace records the model that produced it.

The reviewer benchmark in [`bench/reviewer/`](../bench/reviewer/README.md) measures how often a reviewer configuration (a harness and a model) catches errors planted in derivations and computations, and how often it refutes correct work. It is the way to compare models for the reviewer's role.


## Do I need a Hugging Face account?

Not to try it. A local workspace is a git repository on your machine, without the Hub: sessions work the same way, you answer the debriefs in your editor, and you can run the Space on your folder. A shared space needs an account, and an organisation if anyone else is to see it. A local workspace keeps the same record but no agent traces and no token counts, and there is no command that turns it into a shared space later. See [Getting started](getting-started.md).


## What stays private?

- **On the Hub**, a shared space is five private repositories (four datasets and a Space). Only members of the organisation that owns them can see them. PhysicsHive has no step that makes anything public.
- **Traces.** In a shared space, the agents' transcript of each session is uploaded to the space's private `-traces` dataset, which every member of the organisation can read. A transcript contains whatever the agents read and printed. Secrets in a recognised format are replaced with a marker before the upload, but this does not guarantee that none is left; [Traces and secrets](shared-spaces.md#traces-and-secrets) says what is recognised. Read the traces before you make that dataset public. A local workspace exports and uploads no trace.
- **The model provider** receives what the agents read and write, as with any use of your harness.
- **The literature tools** send search queries and paper identifiers to arXiv, INSPIRE and Semantic Scholar.
- **The Space** holds a copy of a Hugging Face token, as a Space secret, to read the workspace and save your edits. See [the Space's token](shared-spaces.md#the-spaces-token) for how to give it a token with narrow permissions.
- **Harness files** (settings, agents, skills) stay on each machine and are not pushed.


## What does it cost to run?

The main cost is the model: what your harness's provider charges for the tokens of the coordinator and of every sub-agent it dispatches. The repository holds no cost figure, for a session or otherwise. What is known:

- The example's session S1 used `claude-opus-5-5` through Claude Code, made 5 of the 10 dispatches its brief allowed, and took about 35 minutes. No cost was recorded for it.
- In a shared space, each session's `meta.json` in the `-traces` dataset records how many tokens each model used (`tokens_by_model`), when the harness's record holds the counts; your provider's prices give the cost. PhysicsHive records no prices.
- A local workspace exports no trace, so it records no token counts; there, your harness's own usage display is the place to look.
- What bounds a session is its budget of dispatches, 20 by default, which you can change when you confirm the brief; a dispatch is one sub-agent run, such as one derivation or one review.

The reviewer benchmark, which runs single reviews outside any session, lets each configuration set a spending cap per review; its example configuration for Claude Code sets 5 USD. That number is a limit chosen in a file, not a measured cost.

On the Hub, a shared space is four private datasets and a Space. PhysicsHive does not request paid hardware for the Space.


## Does it work outside theoretical physics?

It was designed for theoretical physics and mathematics, and has only been tried on physics problems. Nothing in the scripts is specific to physics. The prompts speak of physics, derivations in LaTeX and computations in Python (SymPy, NumPy), and the literature tools search arXiv and INSPIRE, with Semantic Scholar for citations of papers outside INSPIRE. A field whose work is derivations and computations, and whose literature is on arXiv, is the closest fit.


## How does it differ from Physics Intern?

PhysicsHive grew out of [Physics Intern](https://github.com/huggingface/physics-intern) in November 2026. In Physics Intern, agents work without anyone steering them: a problem goes in and an answer comes out. In PhysicsHive, people steer: sessions are bounded, each returns a note and a debrief, and nothing enters the draft unless a lead puts it there. The two share the renderer, the harness glue, blind review, the literature tools and the reviewer benchmark. Workspaces created with Physics Intern are not supported by PhysicsHive. Physics Intern remains the tool for autonomous runs.


## Can several people work in one space?

The format is built for it, but nobody has worked this way yet. Colleagues who are members of the organisation can sign in to the Space and write in the debriefs; a second contributor can join with `--mode join` and run sessions. Two parts still assume one person: a debrief has one answer per question, and two sessions that edit the same file at the same time conflict when they merge. See [ROADMAP.md](../ROADMAP.md).


## Can I check how a result was obtained?

Yes. Under each result of a note, in the Space, a link opens the card's page with its evidence: the derivations and computations that support it, each with its one-page summary, its full material and its blind reviews. The session's page has the record folded at the bottom: the brief, the coordinator's log, what the session received, the artefacts, and the trace. Every card records which model and which contributor, or which person, produced it, and the workspace records the method version.


## A script failed. What do I do?

The coordinator stops and shows you the script's error, which is one line starting with `ERROR:`. Read it: it usually says what to do (commit or discard some changes, end or abort the active session, reach a host). Fix the cause, or run the command yourself in a terminal, and then tell the coordinator to continue.

Do not ask the coordinator to do the script's work by hand with git or the Hub: the scripts keep the record consistent, and a session pushed by hand can miss its trace or its *Changed by this session*.

Two failures have their own answers below. If a session is left active after a failure you cannot fix, `uv run .physics-hive/scripts/session.py status` shows it and `session.py abort` abandons it.


## uv stops with "Failed to initialize cache"

You are using Claude Code with its sandbox on, and the sandbox does not let uv write its cache, which is outside the workspace. Add this to `~/.claude/settings.json` (merge it with your existing settings), then restart Claude Code:

```json
{ "sandbox": { "filesystem": { "allowWrite": ["~/.cache/uv"] } } }
```

If you set `UV_CACHE_DIR`, allow that folder instead. Do not run the scripts outside the sandbox instead; see [Setting up your harness](harness-setup.md#claude-code).


## A script cannot reach the Hub, or reports a certificate error

A script that cannot reach the Hub says so in one line. If it runs in a sandbox, the sandbox must let it reach `huggingface.co`, `hf.co` and their subdomains, and, the first time a script runs, `pypi.org` and `files.pythonhosted.org`. The settings rendered in the workspace allow these for Claude Code and Codex.

On macOS, the scripts check the Hub's certificates against the system file `/etc/ssl/cert.pem`, because Claude Code's sandbox blocks the usual check through the keychain. If your network inspects encrypted traffic with a certificate installed in your keychain (some company networks do), the check fails: set `SSL_CERT_FILE` to a file that includes that certificate.
