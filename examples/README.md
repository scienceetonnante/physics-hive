# Example: a pendulum, two sessions

[`pendulum/`](pendulum/) is a real PhysicsHive workspace after two sessions, copied as it was. The question is a textbook one, chosen so that the output is easy to judge: *What is the period of a pendulum to second order in the amplitude?* Session S1 answered it (the coefficient is 1/16). The lead ticked that result for the draft and asked for a short literature survey. Session S2 copied the result into the draft, which makes it established, and found a paper to cite. The lead has not answered S2's debrief yet, so the Space opens on that session, marked *Awaiting your response*.

## How it was produced

Everything in this section comes from the files of the example, and from the git history of the space, which is not included.

- The project was a shared space on the Hugging Face Hub, `dlouapre/physics-hive-pendulum`, with one lead, `dlouapre` (`project.toml`), who also ran both sessions as the contributor. The repositories it names on the Hub may not be public.
- The method was PhysicsHive 0.6.0 (`project.toml`), in its release candidate. Two details of the record differ from what the release produces, and the example keeps them: S1's debrief shows *Changed by this session* commit by commit, so a line of `conventions.md` appears added and then replaced, where the release shows one net diff per file; and S1 has a computation `C-S1-2` but no `C-S1-1`, because the session wrote that ID in its log before reserving it (the log says so); the release tells the agents to reserve an ID before writing it anywhere.
- Before S1, the lead wrote the goal in `project.md` (`sessions/S1/received.md` shows the edit).
- Both sessions ran on 24 November 2026, by `dlouapre` with Claude Code and the model `claude-opus-5-5` (`sessions/S1/log.md`, `sessions/S2/log.md`).
- S1 started at 13:22 UTC; the git history dates its last commit at 13:41 UTC. It used 5 of the 20 sub-agent dispatches its brief allowed: one derivation, one computation, a blind review of each, and one critique. A writer sub-agent wrote the note.
- At 13:59 UTC the lead saved a response to the S1 debrief in the Space: two lines ticked and a note. The debrief's question was answered in the terminal at the start of S2 ("Survey only, then stop"), and the session recorded the answer in the debrief (`sessions/S2/log.md`).
- S2 started at 13:59 UTC and its last commit is at 14:12 UTC. It applied the two ticked lines, then used 1 of the 3 dispatches its brief allowed, for the survey. A writer sub-agent wrote the note.
- The claim card records the model and the contributor who ran the session (under the key `operator`) in its `produced_by` field. The reviews record only that an agent wrote them.
- The record states no cost.

## A reading order

1. The question and the goal: [`project.md`](pendulum/project.md).
2. S1's note, written for a reader who was not there: [`sessions/S1/note.pdf`](pendulum/sessions/S1/note.pdf) (source: [`note.tex`](pendulum/sessions/S1/note.tex)).
3. S1's debrief, the one page the lead answers, as the lead left it: [`sessions/S1/debrief.md`](pendulum/sessions/S1/debrief.md). It holds the answer to its question, two of its four lines ticked (copy Result 1 into the draft; add a literature survey as the next step), and a note.
4. What S2 received from the lead before it proposed its brief: [`sessions/S2/received.md`](pendulum/sessions/S2/received.md).
5. The draft, which now holds Result 1 of note S1: [`draft.pdf`](pendulum/draft.pdf) (source: [`draft.tex`](pendulum/draft.tex)). Because a result of the draft names its claim, the claim is established.
6. That claim: [`claims/CL-S1-1.md`](pendulum/claims/CL-S1-1.md). The derivation that supports it, its summary then the full text: [`D-S1-1.summary.md`](pendulum/derivations/D-S1-1.summary.md), [`D-S1-1.tex`](pendulum/derivations/D-S1-1.tex), then its blind review [`D-S1-1_R-S1-1.md`](pendulum/derivations/D-S1-1_R-S1-1.md). The computation that supports the same claim independently: its summary [`C-S1-2.md`](pendulum/computations/C-S1-2.md), the script [`C-S1-2.py`](pendulum/computations/C-S1-2.py) and its output [`C-S1-2.out`](pendulum/computations/C-S1-2.out), then its review [`C-S1-2_R-S1-1.md`](pendulum/computations/C-S1-2_R-S1-1.md).
7. The survey of S2: the paper card of Lima and Arun (2006), [`literature/P-physics_0510206.md`](pendulum/literature/P-physics_0510206.md), the second paper card, [`P-0707.1029.md`](pendulum/literature/P-0707.1029.md), and the overview of the literature, [`overview.md`](pendulum/literature/overview.md). Then S2's note: [`sessions/S2/note.pdf`](pendulum/sessions/S2/note.pdf) (source: [`note.tex`](pendulum/sessions/S2/note.tex)).
8. S2's debrief, waiting for the lead: [`sessions/S2/debrief.md`](pendulum/sessions/S2/debrief.md). Its one line to tick would add a sentence after Result 1 of the draft that cites Lima and Arun.

To go further: each session's brief and log ([`S1/brief.md`](pendulum/sessions/S1/brief.md), [`S1/log.md`](pendulum/sessions/S1/log.md), [`S2/brief.md`](pendulum/sessions/S2/brief.md), [`S2/log.md`](pendulum/sessions/S2/log.md)), the critique of S1 ([`CR-S1-1.md`](pendulum/critiques/CR-S1-1.md)), and the generated index of every card, artefact and paper ([`INDEX.md`](pendulum/INDEX.md)). [`commons/workspace-doc.md`](../commons/workspace-doc.md) describes the format of each file.

The computation can be re-run from the `pendulum/` folder; it reproduces its output and data file exactly:

```bash
uv run --with sympy --with numpy --with scipy python computations/C-S1-2.py
```

## Open it in the Space

From the root of the repository:

```bash
uv run scripts/serve.py --dir examples/pendulum --read-only
```

With `--read-only` you can open every page and type in the forms, but nothing is saved, so the example stays as it is. Without it, saving a response form writes into the session's debrief, such as `pendulum/sessions/S2/debrief.md`; to try saving, run the Space on a copy of the folder.

[`deploy_demo.py`](deploy_demo.py) builds the same read-only Space as a public Space on the Hugging Face Hub (`uv run examples/deploy_demo.py --push --repo <owner>/<name>`; without `--push` it only builds the folder and says how to try it). [DOCUMENTATION.md](../DOCUMENTATION.md#the-demonstration-space) describes it.

## What is not here

Compared with the space on the Hub, the example leaves out:

- the agent traces, which a shared space keeps in a separate dataset on the Hub;
- the sources of the papers that S2's survey downloaded, which a shared space also keeps in a separate dataset, and which keep their own licences;
- the method copy `.physics-hive/` and the harness files that `init` renders from it (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/`, `.agents/`, `.opencode/`, `opencode.json`, `.pi/`, `.mcp.json`);
- the card of the dataset (`README.md`), which describes the repository and links to the space's other repositories on the Hub;
- the workspace's `.gitignore`, and the git history.

No file of the research record was removed or edited. Five generated files, which a real workspace keeps out of git, are included because they help a reader: `INDEX.md` and `references.bib` (from `scripts/regen.py`), and the PDFs of the two notes and of the draft (from `scripts/pdf.py`).
