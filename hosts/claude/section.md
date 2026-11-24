### Claude Code

- Name to pass to the scripts' `--harness` option: `claude`.
- Skills are slash commands (`/session-run`, `/derive`, …). The sub-agent roles are in `.claude/agents/`.
- The workspace scripts need network access (the Hub, PyPI for `uv`). `.claude/settings.json` lets them reach these hosts from inside the sandbox. Run them there, never outside the sandbox; if one cannot reach the Hub, report its error to the contributor. If uv stops with "Failed to initialize cache", tell the contributor to allow `~/.cache/uv` in the sandbox settings of their `~/.claude/settings.json`, as the README explains under *Setting up your harness*.
- **Dispatch** a sub-agent with the `Agent` tool (called `Task` in older versions of Claude Code): set `subagent_type` to the role name and give a short prompt that points to the brief. Example for a derivation:

  ```
  Agent(
    subagent_type="deriver",
    description="derive D-S12-3",
    prompt="Read derivations/.briefs/D-S12-3.md and follow your role definition. Write derivations/D-S12-3.tex and derivations/D-S12-3.summary.md, with the return block at the top of the summary."
  )
  ```

  For dispatches without a brief file (`/review`, `/critique`, `/survey`, `/research-plan`, and the writer of the note), put the small context inline in `prompt`.
- Your model ID is in your system prompt. Pass it to `session.py start --model`.
