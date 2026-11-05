---
description: Set up a PhysicsIntern research workspace in the current folder (local, a new shared space on the Hugging Face Hub, or join one)
agent: build
---
This is a bootstrap. Ask the questions below in the chat, run the installed initializer once with the answers as flags, and relay its result. Do not create, copy or render any workspace file yourself, and do not narrate the steps. The initializer is `${XDG_CONFIG_HOME:-$HOME/.config}/opencode/physics-intern/scripts/plugin-init.sh`; call it with `bash`.

1. **What to do.** Ask the user to choose:
   - a **local workspace** (`--mode local`): one person, on this machine;
   - **create a shared space** (`--mode create`): private repositories on the Hugging Face Hub, for a team;
   - **join a shared space** (`--mode join`): clone a team's existing workspace.
2. **Harnesses.** OpenCode is always included. Run the initializer with `--list-harnesses` and ask whether the folder should also be set up for the other installed harnesses (Claude Code, Codex CLI, Pi), for people who will open it with them.
3. **Where.** The default is the current folder. For local and create it must be empty, apart from an optional `project.md`; for join it must be empty, or you can choose a new subfolder.
4. **Create:** run the initializer with `--list-orgs` (this needs `hf auth login`; if it fails, ask the user to run `hf auth login` and stop) and ask which organisation owns the project (the last line is the user's own account, which only they can see), then the project name. **Join:** ask for the workspace repository (`org/name`).
5. **Run once:**

   ```
   bash "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/physics-intern/scripts/plugin-init.sh" --mode <mode> --harness opencode[,<others>] --dir "<folder>" [--org <org> --name <name> | --repo <org/name>] --yes
   ```

   If OpenCode asks to approve the `bash` command, approve it. Never fall back to doing the work by hand.
6. **Relay** the script's last lines (where the workspace is, and the next steps), then add: **exit and restart OpenCode in the workspace folder**, so that its skills and agents load, and run `/session-run` there.

If the script fails, show the user its `ERROR:` line and stop.
