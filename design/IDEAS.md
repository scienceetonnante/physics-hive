Upload traces in a format that the Hub's trace viewer can open.

   Today `scripts/export_trace.py` writes one file per session, `S<n>/trace.jsonl` in the traces dataset. It
   merges the main conversation and the sub-agent transcripts into that one file and wraps every line as
   `{"source", "record"}`, where `source` names the transcript the line came from. The Hub sees it as plain
   JSONL, and the cards turn the dataset viewer off.

   The Hub has a viewer for agent sessions. According to its documentation (read on 2026-07-26 and not
   checked since), it recognises the session files of Claude Code, Codex and Pi when they are uploaded
   unchanged, one file per row, and shows them as conversations. Other harnesses need the Hub's own format
   for traces (STS). The change would upload each transcript as its own file, unchanged except for the
   secrets that the export replaces, next to `meta.json`.

    - Gain: a person could read an agent's reasoning and tool calls in the browser, without downloading the
      trace.
    - Costs:
        - OpenCode keeps its record in a SQLite database, not in files; its traces would need converting to
          the Hub's format.
        - The `investigate-run` skill reads `trace.jsonl` in the current layout and would need to read the new
          one.
        - The viewer works on a private dataset only for paid accounts (PRO, Team or Enterprise), and the
          cards would need to turn the viewer back on for the traces dataset.
