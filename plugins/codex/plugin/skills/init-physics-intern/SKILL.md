---
name: init-physics-intern
description: Set up a PhysicsIntern research workspace in the current folder - a local workspace, a new shared space on the Hugging Face Hub, or a shared space you join. Run only when the user explicitly invokes it.
---

This is a bootstrap. Ask the questions below in the chat, run the bundled initializer once with the answers as flags, and relay its result. Do not create, copy or render any workspace file yourself, and do not narrate the steps. The initializer is `"${PLUGIN_ROOT}/scripts/plugin-init.sh"`.

1. **What to do.** Ask the user to choose:
   - a **local workspace** (`--mode local`): one person, on this machine;
   - **create a shared space** (`--mode create`): private repositories on the Hugging Face Hub, for a team;
   - **join a shared space** (`--mode join`): clone a team's existing workspace.
2. **Harnesses.** Codex CLI is always included. Run `bash "${PLUGIN_ROOT}/scripts/plugin-init.sh" --list-harnesses` and ask whether the folder should also be set up for the other installed harnesses (Claude Code, OpenCode, Pi), for people who will open it with them.
3. **Where.** The default is the current folder. For local and create it must be empty, apart from an optional `project.md`; for join it must be empty, or you can choose a new subfolder.
4. **Create:** run `bash "${PLUGIN_ROOT}/scripts/plugin-init.sh" --list-orgs` (this needs `hf auth login`; if it fails, ask the user to run `hf auth login` and stop) and ask which organisation owns the project (the last line is the user's own account, which only they can see), then the project name. **Join:** ask for the workspace repository (`org/name`).
5. **Run once:**

   ```
   bash "${PLUGIN_ROOT}/scripts/plugin-init.sh" --mode <mode> --harness codex[,<others>] --dir "<folder>" [--org <org> --name <name> | --repo <org/name>] --yes
   ```

   It writes `.codex/` and runs git, which the workspace-write sandbox keeps read-only, and it needs network access (PyPI for uv, and the Hub for create and join), so Codex will ask for approval; that is expected. If it is denied, run the same command again with approval; never fall back to doing the work by hand.
6. **Relay** the script's last lines (where the workspace is, and the next steps), then add: **exit and restart Codex in the workspace folder** (accept the project-trust prompt on first launch, so that `.codex/config.toml` applies), and run `$session-run` there.

If the script fails, show the user its `ERROR:` line and stop.
