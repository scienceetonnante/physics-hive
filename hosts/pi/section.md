### Pi

- Name to pass to the scripts' `--harness` option: `pi`.
- Skills are slash commands (`/session-run`, `/derive`, …) from `.pi/prompts/`. The sub-agent roles are in `.pi/agents/`. Pi installs `pi-subagents` and `pi-web-access` from `.pi/settings.json` on first launch.
- Tool names are literal and lowercase: `read`, `write`, `edit`, `bash` (with an explicit timeout for long commands), `grep`, `find`, `ls`, `web_search`, `fetch_content`. There is no `Task` tool. To ask the operator something, write plain text and wait for the next message.
- **Dispatch** a sub-agent with the `subagent` tool (from `pi-subagents`):

  ```json
  {
    "tasks": [
      {
        "agent": "deriver",
        "task": "Read derivations/.briefs/D-S12-3.md and follow .pi/agents/deriver.md. Write derivations/D-S12-3.tex and derivations/D-S12-3.summary.md, with the return block at the top of the summary.",
        "output": "derivations/D-S12-3.summary.md"
      }
    ],
    "concurrency": 1,
    "failFast": false
  }
  ```

  For skills without a brief file, put the small context inline in `task`.
- Pass your model ID to `session.py start --model`.
