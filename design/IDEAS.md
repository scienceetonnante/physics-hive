Upload traces in the format the Hub's trace viewer reads. export_trace.py wraps every line as {"source", "record"} and merges the main conversation and the sub-agent transcripts into one file, so the Hub
   treats it as plain JSONL. According to their notes (checked on 2026-07-26; I didn't re-check), the Hub recognises raw Claude Code, Codex or Pi session files uploaded unchanged and opens them in its      
   session viewer, one file per row. Other harnesses need the Hub's STS format.
    - Gain: reviewers could read an agent's reasoning in the browser.
    - Costs:
        - OpenCode traces would need converting to that format.
        - investigate-run would need to read the new layout.
        - The viewer only works on a private dataset with a paid plan.

Remove secrets from traces before uploading them. Their scripts/share-redact.mjs combines two checks:
    - a list of token patterns (Hugging Face, Anthropic, OpenAI, GitHub, AWS, private keys, JWTs, signed URLs);
    - the actual values of every environment variable whose name contains TOKEN, KEY or SECRET.

   Our traces go to a dataset the organisation's members can read, and a transcript contains a token as soon as an agent prints the environment or a config file. A Python version in export_trace.py would be
   about 50 lines. For us, replacing each hit with a marker is better than refusing the upload, because session.py end shouldn't fail on it.

Record token use per session. meta.json records the models but not the token counts. The transcripts contain those counts, and export_trace.py already reads every record. Adding the totals per model     
   would give the cost of each session and of each reviewer-benchmark run.                