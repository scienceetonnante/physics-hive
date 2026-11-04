# Physics Intern — Shared Spaces on the Hugging Face Hub

*Design proposal, revised in November 2026 after the first shared run (`workspaces/helmholtz-2`).*
*Audience: people who know Physics Intern, and the coding agent that will implement the revision.*
*A clickable mock-up of the Space described here is at https://claude.ai/artifact/JV27FRGWrAUhbDmFaA1pBX (private; share it from its page). Its session S1 is the real output of helmholtz-2; sessions S2 and S3 are invented to show the flow.*

## 1. Summary

A shared space is a private set of repositories on the Hugging Face Hub, plus a web app (the Space), where a researcher follows and steers agent work from a browser while the agents run in a terminal. Version 0.3.0 of the method implements the October draft of this document. This revision changes the human side of it.

**Why it changes.** The first shared run produced good physics and a bad experience. Session S1 of helmholtz-2 wrote about 16,000 words: two survey summaries, two critiques, a log, a report of 1,300 words and a plan proposal of 700 words with nine items and eleven "not pursued" entries. The report asked for seven decisions, mixing one real physics question (must the method use only walks?) with routine ones (adopt these conventions, a fallback threshold, library access). The Status page showed the full problem statement, the plan, the report and the decisions at once, with nothing saying where to start. The underlying problem: the same documents served two readers. Agents need everything; the researcher needs the results, the few decisions that are really theirs, and what happens next.

**What changes.** The workspace now has two layers. **The record** is for agents: cards, artefacts, reviews, critiques, logs, traces. It stays as it is. **The human view** is a handful of files, modelled on how a theoretical physicist works with a student: the researcher sets the goal and the next steps; each session comes back with a short LaTeX note and a one-page debrief; the researcher answers in the debrief; a shared LaTeX draft holds what the researcher decided to keep. Everything the researcher reads or writes is one of these files, and the Space shows each as a page.

**Three commitments stay.** *Traceability*: for every result we can tell who produced it, how, and with which version of the method. *Checkability*: agents check agents, and humans can check anything. *Human attention is the scarcest resource*: agents run long, bounded sessions on their own, and the researcher reads one note and answers one debrief per session.

**Default configuration: one person.** The researcher is both the lead, in the browser, and the operator, in the terminal. Several people and roles made most of the October design's bureaucracy (a leads list, permissions, proposal pull requests, promotion rights). The file format still supports several people, so colleagues can be added later (section 4).

## 2. What changed from the October draft

| Removed | Replaced by |
|---|---|
| `problem.md` and `plan.md` | `project.md`: the question, goal, approach, next steps, done steps, definition of done |
| Question cards | The free note at the end of each debrief |
| `report.md` and its *Needs a human decision* section | `note.tex` (results, for reading) and `debrief.md` (questions and decisions, for answering); what only agents need goes at the end of `log.md` |
| Plan proposals as pull requests (`propose.py`) | Tick lines in the debrief, applied by the next session |
| Promotion records (`promote.py`, `feedback/`) | Copying a claim into the draft as a result (section 10) |
| Reactions, triage buttons, verification forms | Answers and notes in the debrief; one rating per paper |
| Per-session survey summaries (`survey-S<n>.md`) | One overview, `literature/overview.md`, updated by each survey |
| `/write-up` | The draft, `draft.tex`, compiled to PDF at any time |
| The Status and Results pages | Five pages, each showing files: Latest, Project, Draft, Sessions, Literature |

Unchanged: the card format for claims and dead ends, session-scoped IDs, computed status and propagation of doubt, blind and test-based review, sessions as draft pull requests, traces, the method copy in `.physics-intern/`, harness files out of git.

## 3. Two layers

**The human view** is these files:

| File | What it is |
|---|---|
| `project.md` | The question in one line as its title, then goal, approach, next steps, done steps, definition of done, and the question in full |
| `conventions.md` | Notation, units, sign conventions |
| `draft.tex` | The best current state of the research, as a draft paper; `references.bib` is generated from the paper cards |
| `sessions/S<n>/note.tex` | What session S<n> found, in two to four pages |
| `sessions/S<n>/debrief.md` | What session S<n> asks of the researcher, and the researcher's answers |
| `literature/overview.md` and the paper list | What the field knows, and one line and one rating per paper |

**The record** is everything else: claim and dead-end cards, derivations, computations, reviews, critiques, paper cards (the full digests), briefs, logs, `INDEX.md`, traces. Agents read it through `INDEX.md` as before. The researcher is never asked to read it; notes and the draft link into it for anyone who wants to check a step.

**Who writes what:**

| File | Written by | Agents may |
|---|---|---|
| `project.md` | the researcher | apply what the researcher ticked in a debrief; move the step a session finished to *Done* |
| `conventions.md` | the researcher and agents | edit it; every change appears in the session's debrief |
| `draft.tex` | the researcher | apply what the researcher ticked; edit it when a next step asks for it (for example "tidy the draft") |
| `note.tex` | the session, through a fresh writer sub-agent | — |
| `debrief.md` | the session, then the researcher | write it at the end of the session; never edit the researcher's answers |
| `literature/ratings.yaml` | the researcher, from the Space | read it; the agent's own estimate stays in the paper card |
| the record | agents | as before |

The rule behind the table: agents never change the meaning of what the researcher wrote. They suggest changes in the debrief, and apply them only once ticked. Every change an agent makes to a human file is listed in its debrief, generated from git.

## 4. People

The default is one person working in two places. In the **Space** they read notes, answer debriefs, and edit `project.md`, `conventions.md` and the draft. In the **terminal** they run sessions with `/session-run`. This document calls that person the researcher. The researcher may also answer a debrief from the terminal, by telling the coordinator; both routes write the same file.

Adding people later costs little, because IDs embed the session number and every item is its own file. A colleague would first read the draft and the notes and write in a debrief's note box, as a colleague reads a draft sent to them; the Space records who wrote what. A second operator comes last: the session machinery already uses pull requests, and `project.toml` keeps the `leads` list for that case.

## 5. Starting a project

`init-physics-intern` asks a few questions, each with a default and a command-line flag: start a local workspace, create a shared space, or join one; which harnesses to render (Claude Code, Codex, OpenCode, Pi); where; and, to create, the Hugging Face organisation and the project name. The plugin commands ask the same questions in the chat and call the script with flags. This part of the October design is implemented and does not change.

Two choices from the October draft stay. **Harness files are personal**: they are rendered locally and git-ignored, so researchers on different harnesses share only research files. **The method is copied into the workspace** (`.physics-intern/`, with its version in `project.toml`), so every session and the Space run the same prompts and scripts, and the prompts that produced a result sit in the git history next to it.

What changes is the skeleton. Init writes `project.md` (its sections with placeholders), `conventions.md`, `draft.tex` (title, empty abstract, an introduction to write) and `literature/seeds.md`. The researcher fills in the title and the goal of `project.md` before the first session, in the Space, in an editor, or by dictating them to the coordinator. Seeds may stay empty.

## 6. Sessions

Work is done in sessions: bounded autonomous runs of a few hours. By default a session takes the first next step in `project.md` as its brief; the researcher may choose another step or give a one-line brief instead. Sessions may read papers, derive, compute and revise the approach, in any order the work needs.

| Step | What happens |
|---|---|
| Start | `session.py start` refuses to start on uncommitted changes or when a session is already active. It fetches `main`, opens a draft pull request whose number is the session number, creates the session branch, runs `regen`, and prints what the researcher sent since the previous session (below). |
| Apply | The coordinator applies the lines the researcher ticked, in one commit that names the debrief they come from. |
| Questions | If a question in an open debrief has no answer, `/session-run` shows it in the terminal and waits. The researcher answers there or says to go on. |
| Brief | `/session-run` proposes the brief: the next step, why, the budget (20 dispatches by default) and the stop conditions. The operator confirms it. It is saved as `sessions/S<n>/brief.md`. |
| Work | As in the October design: dispatch, integrate, write cards, keep the log, run `regen`, commit with `[S<n>]` prefixes. The coordinator may edit `conventions.md` when the work fixes a convention. |
| Stop | At the first of: goal reached; budget spent; four dispatches in a row that add nothing; or the work shows that `project.md` should change. |
| Write | A fresh writer sub-agent writes `note.tex` from the session's artefacts and log. The coordinator writes `debrief.md`, and ends `log.md` with a *Handoff* section: what the next session needs that the researcher does not (open threads, requirements for later briefs, deferred flags). |
| End | `session.py end` runs `check`, adds the section *Changed by this session* to the debrief from the git diff of the human files, pushes, uploads the trace, and merges the pull request. |

**What the next session receives.** `session.py start` prints everything the researcher wrote since the previous session *started*, wherever they wrote it: answers, ticked and unticked lines and notes in debriefs, and the diffs of `project.md`, `conventions.md` and `draft.tex`, plus changed literature ratings. Counting from the previous start, not from its end, catches what the researcher writes while a session is running. Everything comes from git and the files, so it does not depend on what an agent remembers. An example, as the mock-up shows it after session S3:

```
From you since S3
  Debrief S3 (sessions/S3/debrief.md)
    Question 1: To reach 1% on more levels, I can use more walks, …
      Answer: Change the basis first.
    Question 2: Should the next test move to the asymmetric domain now, …
      No answer yet.
    Ticked, applied before the brief:
      ✓ Copy the result of note S3 into the draft, as a result.
    Not ticked, so not applied:
      · Next step: repeat the test on the asymmetric domain with the same basis.
    Your note: none
  Your edits since S3
    project.md       +1 −0 lines
    conventions.md   unchanged
    draft.tex        unchanged
    literature       2 ratings changed
First next step in project.md:
  Find the variance threshold of walk on spheres with the per-ball weights, numerically on the disk.
```

**Why sessions merge without the researcher.** A merge adds to the record and endorses nothing. What the researcher endorses is what is in the draft (section 10), and the draft changes only through their ticks or their edits.

**Unchanged mechanics.** Draft pull requests give collision-free session numbers. A session works on a branch in the checkout where the harness runs, not in a git worktree, because the harness files are git-ignored and the sub-agents write in that checkout. In local mode, sessions take the next free number in `sessions/`, there is no pull request, and `session.py end` only runs `check` and writes *Changed by this session*.

## 7. The note

`sessions/S<n>/note.tex` is what a student would bring back: a short, self-contained LaTeX note, two to four pages, written for the researcher. A short session writes a short note. Its shape:

- title and abstract (what was asked and what was found);
- a *Setting* paragraph for the conventions and assumptions the session used;
- one section per finding, with its equations and citations;
- what did not work, briefly;
- the open question and the suggested next steps, in a paragraph;
- references, from `references.bib`.

A fresh writer sub-agent writes it from the session's artefacts and log. The coordinator's context is full of bookkeeping, and a fresh context writes for a reader who was not there. Each result in the note names its claim card with `\card{CL-S<n>-<k>}`, so that the draft can show its evidence later. Process details (dispatch counts, critiques) stay in the log; the note links to the session record.

Notes use plain LaTeX only: `amsmath`, sections, `itemize` and `enumerate`, `table` and `tabular`, footnotes, `\cite`, `\eqref`, `\ref`, and the environments `result`, `conjecture`, `theorem`, `proof`. This keeps the HTML rendering in the Space faithful (section 14).

## 8. The debrief

`sessions/S<n>/debrief.md` is one screen of markdown. Its parts, in order:

1. **Summary**: three to six sentences and a link to the note.
2. **Changed by this session**: generated by `session.py end` from git. It lists the human files the session changed and why ("as you ticked in S2"), and shows every change to `conventions.md` as a diff.
3. **Questions**: only those the session cannot settle itself. Each is followed by an answer line, `> **Answer:**`, which the Space shows as a text box. For an assumption the session made, the question says that no answer means agreement.
4. **Tick lines**: each a concrete change to a human file, written so that it can be applied without further judgment: set the approach, add a next step, add a definition of done, copy a section or a result of the note into the draft (as a result or as a conjecture). The Space shows them as checkboxes.
5. **Anything else for the next session**: a free note, `> **Note:**`, shown as a larger text box. This is where the researcher asks for something, points to a paper, or makes a remark. It replaces question cards.

```markdown
**Question 1.** Must the method use only SDF queries and walks, or is walk on spheres
inside a global eigensolver on a point set acceptable?

> **Answer:** Walks only first. Keep the global eigensolver as a fallback.

**Tick what you accept.** The next session applies the ticked lines.

- [x] Copy sections 1 to 3 of the note into the draft.
- [ ] Next step: check the per-ball weights by sampling exit times.

#### Anything else for the next session

> **Note:** Start the extraction test on the disk, whose spectrum is exact.
```

**Rules.**

- Decisions take effect at the next session, not when the researcher ticks. The Space only writes files; it applies nothing. Edits the researcher makes directly to `project.md`, `conventions.md` or the draft are theirs and take effect at once.
- A debrief is *open* until a later session starts and reads it, and *closed* afterwards. The Latest page shows open debriefs in full and closed ones folded to one line ("S2 · answered on 28 October · read by S3"). A closed debrief is the record of what was asked, what was decided and when; git gives the author and the time.
- The note box of the newest debrief stays editable while the next session runs. Since `session.py start` reads everything written since the previous start, a note written then reaches the session after.
- An unticked line is not applied. An unanswered question that still matters is asked again in the next debrief, so the researcher never needs to go back to old debriefs.
- An answer in words that implies an action ("fine for now; we will add a corner later") is turned by the next session into a tick line in its own debrief.
- The debrief replaces the report's *Needs a human decision*, plan proposals, promotion proposals, question cards and reactions.

## 9. `project.md` and `conventions.md`

`project.md` replaces `problem.md` and `plan.md`. A real research plan is an end goal and a few next steps, not a list of milestones with dependencies, so the file holds:

```markdown
# <the question in one line>

## Goal
## Approach        (a few sentences: what we are trying now)
## Next steps      (a numbered list; a session takes the first)
## Done            (one line per finished step, with its session)
## Definition of done
## The question in full
```

The researcher writes it. Agents change it in two cases only: to apply a line the researcher ticked, and to move the step their session finished to *Done*. The reasons for dropping a route, which filled the *Not pursued* list of the S1 plan proposal, are useful to agents and stay in the notes and the record.

`conventions.md` stays a separate file, because agents read it before every derivation and computation, and because agents are usually the ones who find a convention clash (S1 found a factor 2 in time between papers). Agents may edit it. Every change appears as a diff in the session's debrief, generated from git, so the researcher sees it even if the agent does not mention it.

## 10. The draft

`draft.tex` is the best current state of the research, written as a draft paper, with `references.bib` generated from the paper cards. Its structure follows a theoretical physics paper:

- **Main text**: statements, key equations, short arguments. Results and conjectures use the `result` and `conjecture` environments, each naming its claim card with `\card{CL-…}`. The card's evidence goes in a footnote ("derivation D-S2-1 and computation C-S2-1, each confirmed by a blind review").
- **Appendices**: the derivations behind the results, included from the record as written, since they are already LaTeX.
- **Supplementary material**: the record itself (computations with code and output, reviews, logs), linked from the footnotes.

**How it grows.** Only the researcher decides what enters the draft: by ticking a line such as "Copy Result 1 into the draft, as a result", or by editing it. The session that applies the tick copies the block from the note unchanged, with a LaTeX comment naming its source. Agents edit the draft otherwise only when a next step asks them to, for example "tidy the draft" or "write the proof of Result 2 as an appendix"; their changes appear in the debrief. The size of the draft is therefore set by what the researcher keeps, and agents cannot flood it.

**Established means: in the draft as a result.** This replaces promotion records. A claim is *established* when a `result` environment in `draft.tex` names its card; `regen` reads the draft to compute it. `check` refuses a `result` environment whose card has neither a supporting artefact with a confirming review nor a human verification, the same bar as the old promotion check. A session asked to copy a result that fails it copies nothing, and says why in its debrief, offering to copy it as a conjecture. If a claim in the draft is later refuted or revised, `regen` flags it, the Space marks it on the Draft page, and the next debrief proposes the change to the draft as a tick line.

Under `/autoresearch` in local mode, which runs benchmarks without a person, the coordinator acts for the researcher: it applies its own suggestions and logs each one as a gate it skipped.

## 11. Results as cards (the record)

The October card format stays, with one kind fewer. A card is one file in `claims/` with a small YAML header and a free prose body.

- A **claim** (`CL-`) is one assertion about the physics or the mathematics that a derivation or a computation can check. Agents write one when they integrate an artefact.
- A **dead end** (`DE-`) records an obstacle or a refutation.
- There are **no question cards**. The researcher's questions and requests arrive through debriefs.

The rules stay. A card never changes once its session has ended; everything that happens to it later is a new file that names it (an artefact that supports it, a review, a dead end that refutes it, a claim that supersedes it). `regen` computes each claim's evidence and status: `working`, `established` (in the draft as a result), `refuted` or `revised`, the last two winning over `established`. Every card that depends on a refuted or revised card is flagged *needs re-check*. IDs embed the session number (`CL-S12-2`, `D-S12-3`, `D-S3-2_R-S7-1`), so parallel sessions never collide. The coordinator reserves a claim's ID in the brief of `/derive` or `/compute`, so that the artefact can name it in `supports`.

**Human verification.** When the researcher says in a debrief that they checked an artefact by hand ("I redid equation 12 of D-S3-2, it holds"), the next session writes a review file with `by: {kind: human, user: …}` that quotes the debrief. It counts as evidence, as before, without a form in the Space.

**Zoom levels.** Every object exists at up to three levels: a line in `INDEX.md`, a one-page summary, and the full material. Agents read the index first and open the rest when needed.

## 12. Review

Unchanged from the October draft, and implemented in 0.3.0. **Blind review**: the reviewer's brief names the artefact and the statement under review, and nothing about who produced them. **Tests before opinions**: the reviewer runs checks with a clear outcome (dimensions, limiting cases, symmetries, numerical spot checks), and every other remark points to a location and carries a severity: *breaks the result*, *weakens it*, or *cosmetic*. "No issue found" is a valid outcome. **Measured reviewers**: the reviewer benchmark gives each configuration a catch rate on planted errors and a false-alarm rate on correct work. **Model diversity is not enforced**, since Claude Code sub-agents can only run Claude models; every card and trace records the model, so the rule can come back if the benchmark shows a need.

## 13. Literature

The seed-and-expand workflow stays: the researcher lists seed papers in `literature/seeds.md`, and `/survey` expands along citations with INSPIRE and arXiv, downloads sources to the `sources` dataset, and writes one paper card per paper. Any session may survey.

Three changes make the literature readable for the researcher:

- **One overview.** `literature/overview.md` describes the field in a few paragraphs, one per topic: known approaches, known barriers, disagreements. Each survey updates it instead of writing a new summary. Two surveys running in parallel would edit the same file; with one researcher this is rare, and the second session resolves the conflict when it rebases.
- **One line per paper.** Each paper card gets three header fields: `why` (one sentence on why it matters here), `topic` (a heading of the overview), and `rating` (the agent's estimate: high, medium or low). The Literature page lists papers by topic with these lines; the full card is the digest shown on click.
- **One rating, changed from a menu.** The researcher clicks a paper's rating and picks high, medium, low or not relevant. The Space writes the choice to `literature/ratings.yaml`, never to the card. The next survey reads it and favours what the researcher rated high.

`regen` generates `references.bib` from the paper cards, with keys made of the first author's name and the year (`yang2015`), for notes and the draft.

## 14. The Space

The Space shows files. Each page shows one kind of file, rendered, with an Edit button where the researcher may write. Saving commits to `main` on the Hub with the Space's token and records the signed-in user as the author. The Space applies nothing on its own: it does not merge, promote or copy; ticked lines are applied by the next session.

| Page | Shows | The researcher can |
|---|---|---|
| **Latest** (first page) | The debriefs, newest first: open ones in full, closed ones folded to one line; below the open ones, what the next session will receive (section 6) | Answer questions, tick lines, write the note, edit the raw markdown |
| **Project** | `project.md` and `conventions.md`, lightly rendered | Edit either file in place |
| **Draft** | `draft.tex`, rendered like arXiv's HTML papers: a contents column, numbered sections and equations, result environments, footnotes, appendices, references | Edit the source beside a preview; download the PDF |
| **Sessions** | One line per session, newest first; each opens its note, rendered the same way, with a button to view the source and a link to the session record | Read |
| **Literature** | The overview, then the papers by topic with their one-line reason and rating; a click opens the agent's digest | Change a rating from its menu |

**Rendering.** Markdown is rendered on the server, with equations in KaTeX or MathJax. LaTeX is converted to HTML on save with LaTeXML, the tool arXiv uses for its HTML papers, and to PDF with `latexmk`. LaTeXML can take several seconds per document, so the Draft editor's live preview may use a lighter converter for the subset of section 7, and the saved page uses LaTeXML. The mock-up uses a small converter written for it.

**The session record** keeps today's pages (cards, artefacts, reviews, logs), reached from the notes, the draft footnotes and the Sessions page. Nobody is sent there by default.

**Ask, later.** A read-only assistant that answers questions about the project, citing the files it read, with three tools: list files, read a file, search text. It matters once a colleague without a terminal joins; with one researcher, the agent in the terminal already does this, and the debrief note covers requests to the agents. It is out of version 0.

## 15. Storage on the Hub

Unchanged and implemented. All repositories are private and belong to a Hugging Face organisation, since a private repository under a personal account cannot be shared. The workspace is a dataset repository holding the research files; `traces` (one folder per session with the exported transcript and `meta.json`), `sources` (paper sources) and `chat-debug` are separate dataset repositories; the Space is its own repository, because every push to a Space repository rebuilds the app. Commits carry `[S<n>]` and the trace lists them, so results and traces link both ways.

## 16. Skills and scripts

| Skill or script | Change |
|---|---|
| `/session-run` | Applies the ticked lines first and shows unanswered questions; takes the first next step as its brief; ends by dispatching the writer for `note.tex`, writing `debrief.md`, and closing `log.md` with its *Handoff* section. |
| Writer role (new) | Writes `note.tex` from the session's artefacts and log, in the LaTeX subset of section 7. |
| `/research-plan` | No longer opens pull requests. It drafts an approach and next steps, which the session puts in its debrief as tick lines. |
| `/survey` | Updates `literature/overview.md`; gives each paper card `why`, `topic` and `rating`; reads `literature/ratings.yaml`. |
| `/derive`, `/compute`, `/review`, `/critique` | Unchanged. |
| `/finalize` | Writes `answer.md` from the results in the draft, at the end of the project. |
| `/write-up` | Removed: the draft is compiled to PDF at any time. |
| `/autoresearch` | Local benchmark runs only; acts for the researcher (section 10). |
| `session.py start` | Prints what the researcher sent since the previous session started (section 6). The old *What is waiting* sections (open questions, reactions, plan proposals, promotions) go. |
| `session.py end` | Adds *Changed by this session* to the debrief from the git diff of the human files. |
| `regen` | Computes `established` from the draft; generates `references.bib`. |
| `check` | Checks the debrief format, the `\card` names in notes and the draft, and the evidence of every `result` environment. |
| `promote.py`, `propose.py` | Removed. |

## 17. Build plan

Version 0.3.0 implements the October draft: cards, sessions as pull requests, the Hub, blind review and its benchmark, a Space with Status and Results pages, and the literature tools. The revision is built in three phases, each ending with a test.

**Phase A — The human files, in local mode.** Skeletons for `project.md`, `conventions.md` and `draft.tex`; the writer role and `note.tex`; `debrief.md` with *Changed by this session*; `session.py start` reading the researcher's answers, ticks, notes and edits; the draft-based `established`; removal of question cards, `report.md`, `promote.py` and `propose.py`; `investigate-run` updated. *Test:* on a toy problem, three local sessions where the researcher acts only by editing debriefs and `project.md` in a text editor. Each decision is applied by the session after it; a result copied into the draft shows as established in `INDEX.md`; a result without a confirming review is refused and offered as a conjecture.

**Phase B — The Space.** The five pages, editing in place with commits to `main`, LaTeXML rendering, the PDF, the rating menu. *Test:* the helmholtz problem rerun from scratch, with the researcher answering only in the Space; every answer and tick appears in the next session's start output, and the researcher never opens a record page unless they choose to.

**Phase C — Literature.** `overview.md`, the `why`, `topic` and `rating` fields, `ratings.yaml`, `references.bib`. *Test:* after rating a few papers, the next survey's choices visibly follow the ratings.

**Then** a calibration run with a problem whose answer the researcher knows from unpublished notes, and later the Ask page and colleagues.

## 18. Open questions

- **LaTeX to HTML.** Whether LaTeXML is fast and robust enough on save, or whether pandoc with the restricted subset is enough.
- **Note length.** Whether a soft limit enforced by `check` (a warning above about four pages) is needed, or whether the writer's instructions suffice.
- **Copying into the draft.** Copying a block unchanged is simple and keeps provenance, but repeated copies make the draft a sequence of note excerpts. How often to tidy it, and whether tidying should be suggested by sessions, is to be seen in practice.
- **"No answer means agreement."** It keeps debriefs short, but a researcher who skips a debrief agrees to everything in it. A session could refuse to apply silent agreements older than a week.
- **Parallel sessions.** Two sessions editing `overview.md`, `conventions.md` or `draft.tex` at the same time conflict at merge; rare with one researcher, to be revisited with several.
- **Credit and authorship** if results from the draft are published.
- **Inference costs**, to be recorded per session in `meta.json`.

## 19. A worked example: helmholtz-2

This follows the mock-up. Session S1 is real; sessions S2 and S3 and the researcher's answers are invented.

**Setup.** The researcher creates the space, writes the title and goal of `project.md` ("Decide whether a walk-only Monte Carlo method can give the lowest Dirichlet eigenvalues of an SDF domain and its response to a point source"), and lists three seed papers.

**S1, literature.** The session surveys 29 papers. Its note, three pages, says that walk-on-spheres estimators of the Helmholtz equation have a finite mean only for $k^2<\lambda_1$, that $\lambda_1$ itself comes from the survival probability of absorbed walkers, and that the best route to several eigenvalues is a correlation matrix of the heat semigroup followed by the generalized eigenvalue method of lattice field theory. The session writes the conventions it adopted, including the factor 2 in time, to `conventions.md`. Its debrief asks two questions (must the method use only walks? are Dirichlet walls and this reading of the point response right?) and offers six tick lines: the approach, a definition of done, copying sections 1 to 3 of the note into the draft, and three next steps. The researcher answers "walks only first, with the global eigensolver as a fallback", leaves the second question empty, which means agreement, ticks all six lines, and adds a note: start the extraction test on the disk.

**S2, reference spectra and per-ball weights.** `session.py start` prints the answers, the ticks and the note. The coordinator applies the ticks in one commit: the approach, the definition of done and three next steps go into `project.md`, and sections 1 to 3 of note S1 into `draft.tex`. It then takes the first next step. The session computes reference spectra on three domains and confirms the per-ball weights $kR/\sin kR$ and $1/J_0(kR)$ by a derivation and by sampling exit times, each confirmed by a blind review. It moves the two steps it finished to *Done*. Its note has a table of spectra and Result 1; its debrief asks whether a domain without corners is a fair test, offers to copy Result 1 and the table into the draft, and suggests two next steps. The researcher answers "fine for now; we will add a corner later", ticks the two copies and the step on the variance threshold, and leaves the step on a domain with a corner unticked, so it is not applied.

**S3, the extraction with synthetic noise.** The session copies Result 1, which passes `check`, so it is now established, and the table as an appendix, and adds the ticked next step to `project.md`. It finds that with $10^6$ walks the extraction reaches 1% on the first three levels of the disk only, because the noise grows like $e^{(\lambda_n-\lambda_1/2)t}$. It adds one line to `conventions.md` (the normalisation of the basis functions), which its debrief shows as a diff. Its debrief asks whether to spend more walks or change the basis, and it moves its finished step to *Done*. The Latest page now shows S3's debrief open, the terminal output that S4 will receive, and S2 and S1 folded to one line each.

## Appendix — Hub notes for implementers

Pull requests on the Hub do not use forks or branches: a pull request is a ref `refs/pr/<n>` in the same repository. Create it with `HfApi.create_pull_request` (it starts as a draft), push session commits with `git push origin <branch>:refs/pr/<n>`, and merge with `HfApi.merge_pull_request`. For a single-file change made from the Space, `HfApi.create_commit` writes the file in one call. Conflicting pull requests are rebased locally before merging, since the Hub's web tools are simpler than GitHub's. Merging requires the write role in the organisation. Private repositories and Spaces are visible only to members of the owning organisation, so every collaborator needs a Hugging Face account and membership.
