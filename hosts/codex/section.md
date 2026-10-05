### Codex CLI

- Name to pass to the scripts' `--harness` option: `codex`.
- Skills are invoked as `$name` (`$session-run`, `$derive`, …); this document writes them `/name`. The sub-agent roles are in `.codex/agents/`.
- Tool names are literal; use only tools visible in your tool set. Read files with `shell_command` (`cat`, `head`, `sed -n`); write and edit them with `apply_patch`; search with `shell_command` (`rg`, `find`, `ls`); use `web_search` for queries and `curl` through `shell_command` for a specific URL. If a tool returns `Tool not found`, do not retry the same call.
- The workspace scripts need network access (the Hub, PyPI for `uv`). `.codex/config.toml` allows it once the project is trusted.
- **Dispatch** a sub-agent with `spawn_agent`, then block on it with `wait_agent`. Give the role name as `agent_type` and keep `fork_context` false so the worker starts from a clean context:

  ```json
  {
    "agent_type": "deriver",
    "message": "Read derivations/.briefs/D-S12-3.md and follow your role definition in .codex/agents/deriver.toml. Write derivations/D-S12-3.tex and derivations/D-S12-3.summary.md, with the return block at the top of the summary.",
    "fork_context": false
  }
  ```

  Then call `wait_agent` with `{"targets": ["<agent id>"], "timeout_ms": 600000}`. For skills without a brief file, put the small context inline in `message`. Do not use `spawn_agents_on_csv`. Parameter names can drift between Codex versions; if dispatch breaks after an upgrade, check them first.
- Pass your model ID to `session.py start --model`.
