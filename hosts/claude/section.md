### Claude Code

- Name to pass to the scripts' `--harness` option: `claude`.
- Skills are slash commands (`/session-run`, `/derive`, …). The sub-agent roles are in `.claude/agents/`.
- **Dispatch** a sub-agent with the `Task` tool: set `subagent_type` to the role name and give a short prompt that points to the brief. Example for a derivation:

  ```
  Task(
    subagent_type="deriver",
    description="derive D-S12-3",
    prompt="Read derivations/.briefs/D-S12-3.md and follow your role definition. Write derivations/D-S12-3.tex and derivations/D-S12-3.summary.md, with the return block at the top of the summary."
  )
  ```

  For skills without a brief file (`/review`, `/critique`, `/survey`, `/research-plan`, `/finalize`, `/write-up`), put the small context inline in `prompt`.
- Your model ID is in your system prompt. Pass it to `session.py start --model`.
