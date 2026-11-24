# Example: a pendulum, one session

[`pendulum/`](pendulum/) is a real PhysicsHive workspace after its first session, copied as it was. The question is a textbook one, chosen so that the output is easy to judge: *What is the period of a pendulum to second order in the amplitude?* The session answered it (the coefficient is 1/16) and wrote a note and a debrief. The lead has not answered the debrief yet, so the Space opens on this session marked *Awaiting your response*.

## How it was produced

Everything in this section comes from the files of the example.

- The project was a shared space on the Hugging Face Hub, `dlouapre/physics-hive-pendulum`, with one lead, `dlouapre` (`project.toml`). The repositories it names on the Hub may not be public.
- The method was PhysicsHive 0.5.6 (`project.toml`).
- Before the session, the lead wrote the question and the goal in `project.md`, in the Space (`sessions/S1/received.md` shows the two edits).
- Session S1 started on 9 November 2026 at 15:01 UTC, run by `dlouapre` with Claude Code and the model `claude-opus-5-5` (`sessions/S1/log.md`). The git history of the space, which is not included, dates the end of the session at 15:35 UTC.
- The session used 5 of the 10 sub-agent dispatches its brief allowed: one derivation, one computation, a blind review of each, and one critique. A writer sub-agent wrote the note. The two claim cards record the model and the contributor who ran the session (under the key `operator`) in their `produced_by` field. The reviews record only that an agent wrote them.
- The record states no cost.

## A reading order

1. The question and the goal: [`project.md`](pendulum/project.md).
2. The note, written for a reader who was not there: [`sessions/S1/note.pdf`](pendulum/sessions/S1/note.pdf) (source: [`note.tex`](pendulum/sessions/S1/note.tex)).
3. The debrief, the one page the lead answers: [`sessions/S1/debrief.md`](pendulum/sessions/S1/debrief.md).
4. The claim behind Result 1 of the note: [`claims/CL-S1-1.md`](pendulum/claims/CL-S1-1.md).
5. The derivation that supports it, its summary then the full text: [`D-S1-1.summary.md`](pendulum/derivations/D-S1-1.summary.md), [`D-S1-1.tex`](pendulum/derivations/D-S1-1.tex). Then its blind review: [`D-S1-1_R-S1-1.md`](pendulum/derivations/D-S1-1_R-S1-1.md).
6. The computation that supports the same claim independently: its summary [`C-S1-1.md`](pendulum/computations/C-S1-1.md), the script [`C-S1-1.py`](pendulum/computations/C-S1-1.py) and its output [`C-S1-1.out`](pendulum/computations/C-S1-1.out). Its review is [`C-S1-1_R-S1-1.md`](pendulum/computations/C-S1-1_R-S1-1.md).

To go further: the session's brief and log ([`brief.md`](pendulum/sessions/S1/brief.md), [`log.md`](pendulum/sessions/S1/log.md)), the critique of the whole session ([`CR-S1-1.md`](pendulum/critiques/CR-S1-1.md)), and the generated index of every card and artefact ([`INDEX.md`](pendulum/INDEX.md)). [`commons/workspace-doc.md`](../commons/workspace-doc.md) describes the format of each file.

The computation can be re-run from the `pendulum/` folder; it reproduces its output and data files exactly:

```bash
uv run --with sympy --with numpy --with scipy python computations/C-S1-1.py
```

## Open it in the Space

From the root of the repository:

```bash
uv run scripts/serve.py --dir examples/pendulum --read-only
```

With `--read-only` you can open every page and type in the forms, but nothing is saved, so the example stays as it is. Without it, saving the response form writes into `pendulum/sessions/S1/debrief.md`; to try saving, run the Space on a copy of the folder.

[`deploy_demo.py`](deploy_demo.py) builds the same read-only Space as a public Space on the Hugging Face Hub (`uv run examples/deploy_demo.py --push --repo <owner>/<name>`; without `--push` it only builds the folder and says how to try it). [DOCUMENTATION.md](../DOCUMENTATION.md#the-demonstration-space) describes it.

## What is not here

Compared with the space on the Hub, the example leaves out:

- the agent traces, which a shared space keeps in a separate dataset on the Hub;
- the paper sources, which a shared space also keeps in a separate dataset. This session made no literature survey, so `literature/` holds only an empty `seeds.md`;
- the method copy `.physics-hive/` and the harness files that `init` renders from it (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/`, `.agents/`, `.opencode/`, `opencode.json`, `.pi/`, `.mcp.json`), which are the same for every workspace of version 0.5.6;
- the workspace's `.gitignore`, and the git history.

No file of the research record was removed or edited. Three generated files, which a real workspace keeps out of git, are included because they help a reader: `INDEX.md` and `references.bib` (from `scripts/regen.py`) and `sessions/S1/note.pdf` (from `scripts/pdf.py`). `references.bib` is empty because no paper was cited. `draft.tex` is still the empty template: nothing enters the draft until a lead ticks a line of the debrief.
