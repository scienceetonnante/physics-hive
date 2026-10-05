### OpenCode

- Name to pass to the scripts' `--harness` option: `opencode`.
- Skills are slash commands (`/session-run`, `/derive`, …). The sub-agent roles are in `.opencode/agents/`, each with `mode: subagent`.
- **Dispatch** a sub-agent with the `task` tool: give the role name and a self-contained prompt that points to the brief. Example for a derivation:

  ```
  task(
    subagent_type="deriver",
    description="derive D-S12-3",
    prompt="Read derivations/.briefs/D-S12-3.md and follow your role definition. Write derivations/D-S12-3.tex and derivations/D-S12-3.summary.md, with the return block at the top of the summary."
  )
  ```

  For skills without a brief file, put the small context inline in `prompt`.
- Dispatching custom sub-agents has depended on the OpenCode version (some builds only accepted the built-in `explore` and `general` roles; see opencode issue #29616). If yours cannot dispatch these roles, run the step in your own context by reading the role file in `.opencode/agents/` and following it; the method still holds, only the context isolation is lost, and you record this in the session log.
- Pass your model ID (`provider/model`) to `session.py start --model`.
