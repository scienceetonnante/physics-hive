# The workspace

A workspace is a git repository that holds one project: a few files for the leads, and a complete record for the agents. This guide describes both, how the leads' decisions reach the agents, what "established" means, and the skills and scripts. The authoritative description, as the agents read it, is `AGENTS.md` in each workspace (its source is [`commons/workspace-doc.md`](../commons/workspace-doc.md)); the developer reference is [DOCUMENTATION.md](../DOCUMENTATION.md#the-workspace-format).


## The lead's files

| File | What it is | Who changes it |
|---|---|---|
| `project.md` | The question in one line as its title, then *Goal*, *Approach* and *Next steps* | The leads. Agents only apply a line you ticked, and remove the step their session finished. |
| `conventions.md` | Notation, units, sign conventions | The leads and the agents; every change an agent makes appears as a diff in its debrief. |
| `draft.tex` | The best current state of the research, as a draft paper | The leads. Agents copy into it only what you tick, or edit it when a next step asks them to; such edits appear as a diff in their debrief. |
| `sessions/S<n>/note.tex` | What session S<n> found, in two to four pages of LaTeX | A fresh writer agent. |
| `sessions/S<n>/debrief.md` | What session S<n> asks of you: a summary, *Changed by this session*, questions, tick lines, a note box | The session, then the leads. |
| `literature/overview.md`, `seeds.md`, `ratings.yaml` | The field in a few paragraphs; your seed papers; your rating of papers | Surveys write the overview; the leads write the seeds and the ratings. |

The rule behind the table: agents never change the meaning of what a lead wrote. They suggest changes in the debrief, and apply them only once ticked. Every change an agent makes to one of the lead's files is listed in its debrief, generated from git.

**The note** is what a student would bring back: a title and an abstract (what was asked, what was found), a *Setting* paragraph with the conventions and assumptions, one section per finding with its equations and citations, what did not work, and the open question with the suggested next steps. Each result names its claim card with `\card{CL-S<n>-<k>}`. Notes use a plain subset of LaTeX, so that the Space renders them faithfully.

**The debrief** fits on one screen. After the summary and *Changed by this session* come the questions, each followed by `> **Answer:**`; the tick lines, `- [ ] …`, each a concrete change to `project.md`, `conventions.md` or `draft.tex` that the next session can apply without further judgment; and a note box, `> **Note:**`, for anything else. For an assumption the session made, the question says that no answer means agreement. The example's debrief is [`examples/pendulum/sessions/S1/debrief.md`](../examples/pendulum/sessions/S1/debrief.md).


## How decisions flow

You never ask the agents for anything in the middle of their work. You answer the latest debrief, tick its lines, and write in its note box, in the Space or in an editor; you may also edit `project.md`, `conventions.md` or the draft directly.

The next `session.py start` prints everything written since the previous session *started*, and records it in `sessions/S<n>/received.md`. Counting from the previous start, not its end, catches what you write while a session is running: it reaches the session after. The session then applies the ticked lines first, asks any question left unanswered, and proposes its brief.

- An unticked line is not applied.
- An unanswered question that still matters is asked again in the next debrief, so you never need to go back to old debriefs.
- An answer in words that implies an action ("fine for now; we will add a corner later") is turned by the next session into a tick line in its own debrief.
- A tick is never applied twice: what a session received is recorded, and later sessions receive only what changed.
- You may also answer from the terminal, by telling the coordinator; it records your words in the debrief as yours (`session.py answer` and `session.py tick`).

A debrief is *open* until a later session starts and reads it, and *closed* afterwards. A closed debrief is the record of what was asked, what was decided and when; git gives the author and the time.


## What "established" means

A claim is *established* when a `result` environment of `draft.tex` names its card:

```latex
\begin{result}[Short title]
The statement, with its key equation.\footnote{Derivation D-S2-1 and computation
C-S2-1, each confirmed by a blind review.}\card{CL-S2-1}
\end{result}
```

Only the leads decide what enters the draft: by ticking a line such as "Copy Result 1 of note S2 into the draft, as a result", or by editing it. `check` refuses a result whose claim has no confirming review of a supporting derivation or computation (or a verification by a lead, reported in a debrief); such a claim goes in a `conjecture` environment instead. Sessions merge without the leads, because a merge endorses nothing.

If a claim in the draft is later refuted or revised, the Space marks it on the *Draft* page, and the next debrief proposes the change to the draft as a tick line.

**A verification by a lead.** If you write in a debrief that you checked an artefact by hand ("I redid equation 12 of D-S3-2, it holds"), the next session records it as a review by you, which counts as evidence.

**If you think a result is wrong**, say so in the debrief, in an answer or in the note box: the next session reads it as an input to its brief. A claim becomes *refuted* only through a dead-end card, which a session writes once a second, independent review agrees; every card that depends on it is then flagged *needs re-check*, and if the claim is in the draft, the next debrief offers the change as a tick line.


## What a workspace looks like

```
project.md            the question, goal, approach, next steps (the lead's)
conventions.md        notation, units, signs
draft.tex             the draft paper (the lead's); references.bib is generated from the paper cards
project.toml          method version, Hub repositories, people
.physics-hive/        copy of the method: prompts, renderer, scripts, templates, Space app
sessions/S12/         received.md, brief.md, log.md, note.tex (to read), debrief.md (to answer)
claims/               one card per claim or dead end
derivations/          D-S12-3.summary.md (one page) + D-S12-3.tex (full LaTeX) + reviews
computations/         C-S12-1.md (one page) + .py + .out + reviews
critiques/            strategic critiques
literature/           overview.md, one card per paper (P-<arXiv id>.md), seeds.md, ratings.yaml
INDEX.md              generated: one line per card, artefact, paper and session (git-ignored)
```

The harness files (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/`, `.agents/`, `.opencode/`, `opencode.json`, `.pi/`, `.mcp.json`) are rendered from `.physics-hive/` on each machine and are not committed; neither are `INDEX.md`, `references.bib` and the PDFs. In a shared space, the workspace also has a `README.md`: its card on the Hub, which says what the repository holds; no script reads it. `.physics-hive/` itself is committed, so every checkout and the Space run the same prompts and scripts, and the prompts that produced a result sit in the git history next to it.


## The record

The record is everything besides the lead's files. The leads are never asked to read it; notes and the draft link into it, and the Space shows it on demand.

**Cards** are the record of results. A *claim* (`CL-`) is one assertion about the physics, in one sentence, that a derivation or a computation can check; a *dead end* (`DE-`) records an obstacle or a refutation. Each card records who produced it: the agent's model and the contributor who ran the session (under the key `operator`), or the person. A card can be corrected during the session that wrote it and never changes afterwards. Everything that happens to it later is a new file that names it: an artefact that supports it, a review, a dead end that refutes it, a claim that supersedes it. The example's claim is [`examples/pendulum/claims/CL-S1-1.md`](../examples/pendulum/claims/CL-S1-1.md).

The scripts compute each claim's status: `refuted` if a dead end refutes it; otherwise `revised` if a claim supersedes it; otherwise `established` if a result of the draft names it; otherwise `working`. They compute its evidence (the artefacts that support it and their reviews), and flag as *needs re-check* every card that depends on a refuted or revised one. None of this is stored; it is recomputed from the files.

**Artefacts** are the derivations (`derivations/D-S<n>-<k>.summary.md`, a one-page summary, and `.tex`, the full LaTeX) and the computations (`computations/C-S<n>-<k>.md`, with the script `.py` and its output `.out`). Their headers carry no authorship, so that reviews stay blind.

**Reviews** (`<artefact>_R-S<n>-<k>.md`, next to the artefact) are blind: the reviewer gets the artefact and the statement under review, never who produced it nor earlier verdicts. It runs tests with a clear outcome first (dimensions, limiting cases, symmetries, numerical spot checks); every other remark points to a location and carries a severity. "No issue found" is a valid outcome. A refutation becomes a dead end only after a second, independent review agrees.

**Also in the record:** paper cards (`literature/P-<arXiv id>.md`), critiques (`critiques/CR-S<n>-<k>.md`), and each session's folder (`received.md`, `brief.md`, `log.md` with its *Handoff* for the next session, and `plan.md` when `/research-plan` ran). In a shared space, the traces are in the `-traces` dataset.

**IDs** embed the session number (`CL-S12-2`, `D-S12-3`, `D-S3-2_R-S12-1`), so parallel sessions never collide. Every object exists at up to three levels: a line in `INDEX.md`, a one-page summary, and the full material. Agents read the index first.


## Skills

Skills are the workflows the coordinator follows. You run `/session-run`; the session runs the others as the work needs them, and you may also run them yourself during a session.

| Skill | What it does |
|---|---|
| `/session-run` | Runs one session: start, apply the ticked lines, a brief you confirm, autonomous work within a budget, note and debrief, end (and merge, in a shared space). |
| `/survey` | Literature: expands from the seed papers and the papers rated high, along citations (INSPIRE, arXiv), writes paper cards and updates the overview. Usable in any session. |
| `/research-plan` | Drafts an approach and next steps, which the session offers as tick lines. |
| `/derive <target>` | Analytical derivation in LaTeX with a one-page summary, by a fresh-context sub-agent. |
| `/compute <target>` | Symbolic and numerical computation (SymPy, NumPy), with both paths compared. |
| `/review <artefact>` | Blind, test-based review: dimensions, limits, symmetries and spot checks first, then located remarks with a severity. |
| `/critique` | Strategic critique of the overall state. |

In Codex, skills are invoked with `$` (`$session-run`).


## Scripts

The deterministic work is done by scripts in `.physics-hive/scripts/`, which the skills call with `uv run`. You rarely need to run them yourself; these are the ones you may want:

| Command | What it does |
|---|---|
| `uv run .physics-hive/scripts/session.py status` | Whether a session is active in this checkout; otherwise what a session started now would receive. |
| `uv run .physics-hive/scripts/session.py save` | Commit your edits of your own files as yours and, in a shared space, push them to `main`. |
| `uv run .physics-hive/scripts/session.py abort` | Abandon the active session (in a shared space, close its pull request). |
| `uv run .physics-hive/scripts/pdf.py` | Compile `draft.tex` to `draft.pdf`; `pdf.py S3` compiles the note of S3 to `sessions/S3/note.pdf`. Needs `latexmk`. |
| `uv run .physics-hive/scripts/regen.py` | Rebuild `INDEX.md` and `references.bib`. |
| `uv run .physics-hive/scripts/check.py` | Validate the workspace: cards, references, immutability, the draft's results, notes and debriefs. |
| `uv run .physics-hive/scripts/serve.py` | Run the Space on this folder (see [The Space](the-space.md#running-the-space-on-your-machine)). |
| `uv run .physics-hive/scripts/hubgit.py <git arguments>` | Run git against the Hub with your token, without storing it. |
| `uv run .physics-hive/scripts/init.py` | Add a harness or render the harness files again (`--harness codex`). |

The others are used by the skills: `session.py` (also `start`, `next`, `answer`, `tick`, `brief`, `end`), `export_trace.py` (the session's trace), `literature.py` (arXiv and INSPIRE search, citations, sources; also an MCP server), and `hub.py` (the Hub operations). Each script prints what it did, and fails with one `ERROR:` line rather than guess.
