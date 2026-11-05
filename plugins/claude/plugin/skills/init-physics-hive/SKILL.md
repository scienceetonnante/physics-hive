---
name: init-physics-hive
description: Set up a PhysicsHive research workspace in the current folder - a new shared space on the Hugging Face Hub, a shared space you join, or a local workspace.
disable-model-invocation: true
---

The PhysicsHive initializer is:

!`echo "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-init.sh"`

The current project folder is:

!`echo "${CLAUDE_PROJECT_DIR:-$PWD}"`

This is a bootstrap. Ask the questions below, run the initializer once with the answers as flags, and relay its result. Do not create, copy or render any workspace file yourself, and do not narrate the steps.

1. **What to do.** Ask the user (with AskUserQuestion) to choose:
   - **create a shared space** (`--mode create`, the usual choice): private repositories and a Space on the Hugging Face Hub, for a team or for one person;
   - **join a shared space** (`--mode join`): clone a team's existing workspace;
   - a **local workspace** (`--mode local`): on this machine only, without the Hub, to try the method.
2. **Harnesses.** Claude Code is always included. Run `bash <initializer> --list-harnesses` and ask whether the folder should also be set up for the other installed harnesses (Codex CLI, OpenCode, Pi), for people who will open it with them.
3. **Where.** The default is the current project folder above. For local and create it must be empty, apart from an optional `project.md`; for join it must be empty, or you can choose a new subfolder.
4. **Create:** run `bash <initializer> --list-orgs` (this needs `hf auth login`; if it fails, tell the user to run `! hf auth login` and stop) and ask which organisation owns the project (the last line is the user's own account, which only they can see), then the project name. **Join:** ask for the workspace repository (`org/name`).
5. **The question and the goal** (create and local). Ask for the question of the project in one line, and its goal: the question in full, and what would count as an answer. The user may leave either for later. They become the title and the *Goal* of `project.md`; a session needs both to start.
6. **Run once:**

   ```
   bash <initializer> --mode <mode> --harness claude[,<others>] --dir "<folder>" [--org <org> --name <name> | --repo <org/name>] [--question "<question>"] [--goal "<goal>"] --yes
   ```

   Quote the question and the goal for the shell, and leave out a flag the user left for later.

   It writes `.claude/` and runs git, which Claude Code's sandbox blocks, and it needs network access (PyPI for uv, and the Hub for create and join). Claude Code will ask to run it outside the sandbox or for permission; that is expected. If it is denied, run the same command again with permission; never fall back to doing the work by hand.
7. **Relay** the script's last lines (where the workspace is, and the next steps), then add: **exit and restart Claude Code in the workspace folder**, so that its skills and agents load, and run `/session-run` there.

If the script fails, show the user its `ERROR:` line and stop.
