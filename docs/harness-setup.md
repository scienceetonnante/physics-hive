# Setting up your harness

A harness is the coding agent that runs the sessions: Claude Code, Codex CLI, OpenCode or Pi. A session runs on its own for hours, so a few minutes of setup before the first one saves interruptions later. The installer renders the harness files you selected (agents, skills, settings) into the workspace; this guide covers what is left for you to do.


## With every harness

- **Launch the harness from the workspace folder**, after the installer has finished. A harness reads the workspace's settings when it starts, so restart it after you add a harness or upgrade the workspace.
- **Stay logged in to Hugging Face** for a shared space. The installer logs you in if needed; to log in again later, run `hf auth login`, or `uv tool run --from huggingface_hub hf auth login` if the `hf` command is not installed. If the environment variable `HF_TOKEN` is set, the scripts use it instead of your login.
- **When a script fails, let it stop the session.** The coordinator stops and shows you the error instead of working around it. Fix the cause, or run the command yourself in a terminal, and then let the coordinator continue. Do not ask it to redo the script's work with git or the Hub by hand: the scripts keep the record consistent.
- **On macOS**, the scripts check the Hub's certificates against the system file `/etc/ssl/cert.pem`, because a sandbox blocks the usual check through the keychain. If your network inspects encrypted traffic with a certificate installed in your keychain, set `SSL_CERT_FILE` to a file that includes it.
- **Network.** The scripts need to reach `huggingface.co`, `hf.co` and their subdomains (in a shared space), and uv needs `pypi.org` and `files.pythonhosted.org` the first time it installs a script's dependencies. The literature tools reach arXiv, INSPIRE and Semantic Scholar.

A workspace rendered for several harnesses opens in any of them without running anything again. `AGENTS.md` holds the method and one short section per harness. The coordinator records its model in every card it writes and in the session's trace, so each harness passes its model's identifier to the scripts at the start of a session; you do not need to.


## Claude Code

Claude Code reads `CLAUDE.md`, a one-line import of `AGENTS.md`. Skills are slash commands: `/session-run`.

- **Accept the trust prompt** for the folder on first launch. It turns on the workspace's settings, including the literature tools (an MCP server).
- **Choose a permission mode before `/session-run`.** The workspace's `.claude/settings.json` allows the workspace scripts (`uv run`, `python`), a few git commands (`add`, `commit`, `status`, `log`, `diff`, `show`), `mkdir`, `ls` and the literature tools. It allows no file edits and sets no permission mode. In Claude Code's default mode, the coordinator and its sub-agents therefore ask before each file edit, and the session waits until you answer. Switch to a mode in which Claude Code edits files without asking, auto mode or accept-edits mode (Shift+Tab cycles the modes), before you start the session. In accept-edits mode, a command that the settings do not allow may still ask. The author runs sessions in auto mode with the sandbox on.
- **The sandbox can stay on.** The workspace's `.claude/settings.json` lets commands reach the Hub and PyPI, which the scripts need. One setting is yours to add, in `~/.claude/settings.json`: the scripts run through uv, which writes its cache outside the workspace, so the sandbox must allow that folder. Merge this into your existing settings:

  ```json
  { "sandbox": { "filesystem": { "allowWrite": ["~/.cache/uv"] } } }
  ```

  Without it, no workspace script can run in the sandbox, and uv stops with "Failed to initialize cache". If you set `UV_CACHE_DIR`, allow that folder instead. The workspace's own settings do not open this folder, because a sandboxed command could then change packages that later run outside the sandbox; you decide it for your machine.
- **Do not let the agent run the workspace scripts outside the sandbox**, and do not exclude them from it (`sandbox.excludedCommands`). The scripts live in the workspace, which the agent can edit, so they would let anything the agent writes there run unsandboxed.


## Codex CLI

Codex reads `AGENTS.md`. Skills are invoked with `$`: `$session-run`.

- **Accept the project-trust prompt** on first launch. Otherwise Codex ignores `.codex/config.toml`, which gives commands network access in the workspace sandbox (the scripts need it), turns on web search, and starts the literature tools.


## OpenCode

OpenCode reads `AGENTS.md`. Skills are slash commands.

- The workspace's `opencode.json` lets the agent run commands, edit files and search the web without asking, so that a session can work on its own. **OpenCode does not confine those commands to the workspace.** Run it on a machine, or in an account, where that is acceptable.
- Dispatching custom sub-agents has depended on the OpenCode version ([opencode #29616](https://github.com/anomalyco/opencode/issues/29616)); `AGENTS.md` tells the coordinator what to do when it fails.


## Pi

Pi reads `AGENTS.md`. Skills are slash commands, from `.pi/prompts/`.

- On first launch it installs two packages, `pi-subagents` and `pi-web-access`, which it needs for sub-agents and web search.
- Pi has no MCP support, so the sub-agents call the literature tools from the command line instead (`uv run .physics-hive/scripts/literature.py`).


## Models

PhysicsHive uses whatever model your harness is configured with; it does not choose one. Claude Code runs Claude models, and Codex CLI runs OpenAI models. OpenCode and Pi can use many providers, including open models through Hugging Face Inference Providers (the reviewer benchmark's [`configs.toml`](../bench/reviewer/configs.toml) has examples). In Claude Code, the sub-agents run Claude models too, so authors and reviewers come from the same model family; see the [FAQ](faq.md#which-models-and-harnesses-can-i-use).
