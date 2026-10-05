"""The PhysicsIntern Space: a browser interface to a shared research workspace.

Reviewers read results, react, write question and claim cards, verify claims
and ask the explainer chat; leads also promote claims, edit the lead's files
and merge proposals. This file is the user interface only: reading and
writing the workspace is in backend.py, the explainer in chat.py.

Every write takes the signed-in user from the sign-in session itself
(`gr.OAuthProfile`), never from a value the page sends.

Run it on a local workspace folder, without the Hub and without sign-in:
    PHYSICS_INTERN_LOCAL=/path/to/workspace PHYSICS_INTERN_LOCAL_USER=alice python app.py
"""

import gradio as gr

import chat
from backend import CLAIM_REACTIONS, FILTERS, LEAD_FILES, PAPER_REACTIONS, VERDICTS, Backend, SpaceError

LATEX = [{"left": "$$", "right": "$$", "display": True}, {"left": "$", "right": "$", "display": False}]
NO_TARGET = "(none: I checked the statement directly)"


def md(value: str = "", **kwargs) -> gr.Markdown:
    """Markdown with equations."""
    return gr.Markdown(value, latex_delimiters=LATEX, **kwargs)


def attempt(action, *args) -> tuple[bool, str]:
    """Run a backend write: (True, its message) or (False, why it was refused)."""
    try:
        return True, action(*args)
    except SpaceError as exc:
        return False, f"**Not done.** {exc}"


def build(backend: Backend) -> gr.Blocks:
    def user_of(profile):
        return backend.user(profile.username if profile else None)

    # No usage analytics: the Space shows a private research project.
    with gr.Blocks(title="PhysicsIntern", analytics_enabled=False) as demo:
        version = gr.State(0)  # increased at every refresh, so that the rendered sections redraw
        viewer = gr.State(None)  # who is reading, to show or hide lead-only controls

        with gr.Row(equal_height=True):
            with gr.Column(scale=4):
                gr.Markdown("# PhysicsIntern")
                status = md()
            with gr.Column(scale=1, min_width=240):
                if not backend.local:
                    gr.LoginButton()
                who = md()
                refresh_btn = gr.Button("Refresh", size="sm")

        with gr.Tabs() as tabs:
            # ----- Overview -----
            with gr.Tab("Overview", id="overview"):
                overview = md()

            # ----- Results -----
            with gr.Tab("Results", id="results"):
                with gr.Row():
                    flt = gr.Dropdown(list(FILTERS), value="All cards", label="Show", scale=1)
                    query = gr.Textbox(label="Search the statements", placeholder="keywords", scale=2)
                with gr.Accordion("Index", open=True):
                    index = md()
                card_dd = gr.Dropdown(label="Open a card", choices=[], interactive=True)
                card_md = md()
                related_dd = gr.Dropdown(label="Open a related card", choices=[], interactive=True)
                md("**React** (one current reaction per person; reactions carry no evidential weight)")
                with gr.Row():
                    react_btns = {value: gr.Button(value.capitalize(), size="sm") for value in CLAIM_REACTIONS}
                    react_comment = gr.Textbox(placeholder="Optional one-line comment", show_label=False, scale=3)
                react_msg = md()
                explain_btn = gr.Button("Ask the explainer about this card", size="sm")

                @gr.render(inputs=[card_dd, version])
                def show_evidence(card_id, _version):
                    try:
                        items = backend.evidence_items(card_id)
                    except SpaceError:
                        return
                    if not items:
                        return
                    md("### Evidence")
                    for item in items:
                        md(f"#### {item['title']}")
                        md(item["summary"] or "(empty summary)")
                        for f in item["files"]:
                            with gr.Accordion(f"Full material: {f['path']}", open=False):
                                gr.Code(f["text"], language=f["language"], interactive=False, show_label=False)
                        for review in item["reviews"]:
                            with gr.Accordion(review["title"], open=False):
                                md(review["body"])

                with gr.Accordion("Verify this claim", open=False):
                    md("A verification is evidence, unlike a reaction: say what you checked yourself (steps, "
                       "limiting cases, numbers). The lead sees who wrote it when deciding a promotion.")
                    verdict = gr.Radio(list(VERDICTS), value="confirmed", label="Verdict")
                    v_target = gr.Dropdown(label="Artefact you checked", choices=[NO_TARGET], value=NO_TARGET)
                    v_body = gr.Textbox(lines=5, label="What you checked")
                    v_btn = gr.Button("Record the verification", variant="primary")
                    v_msg = md()
                with gr.Accordion("Promote this claim to established (leads)", open=False, visible=False) as promote_box:
                    md("Promotion is your judgment that the evidence is robust, usually two independent routes "
                       "with confirming reviews. The workspace's rule is checked again on the latest main.")
                    p_reason = gr.Textbox(lines=2, label="The evidence that justifies it")
                    p_btn = gr.Button("Promote", variant="primary")
                    p_msg = md()

            # ----- Explainer chat -----
            with gr.Tab("Explain", id="explain"):
                md("**The chat explains; it does not verify.** It answers from the project's files, and its "
                   "answers carry no evidential weight. To check a result yourself, verify it on the Results page.")
                banner = md(backend.chat_banner(), visible=backend.chat_debug)
                with gr.Row():
                    chat_card = gr.Dropdown(label="Card at hand", choices=[], scale=2)
                    level = gr.Radio(list(chat.LEVELS), value=next(iter(chat.LEVELS)), label="Level", scale=1)
                chatbot = gr.Chatbot(latex_delimiters=LATEX, height=460, show_label=False)
                question = gr.Textbox(placeholder="Ask about this card", show_label=False, submit_btn=True)
                read_note = md()
                to_card_btn = gr.Button("Turn my last question into a question card for the agents")

            # ----- Questions -----
            with gr.Tab("Questions", id="questions"):
                md("Open question cards are the queue for the agents: the next sessions start from them.")
                questions = md()
                ask_btn = gr.Button("Write a question card")

            # ----- Literature -----
            with gr.Tab("Literature", id="literature"):
                papers = md()
                paper_dd = gr.Dropdown(label="Open a paper card", choices=[], interactive=True)
                paper_md = md()
                md("**Triage** (one current choice per person; the next survey uses them as examples)")
                with gr.Row():
                    triage_btns = {value: gr.Button(value.capitalize(), size="sm") for value in PAPER_REACTIONS}
                triage_msg = md()

            # ----- Sessions -----
            with gr.Tab("Sessions", id="sessions"):
                md("### Open sessions")
                open_sessions = md()
                md("### Session briefs and reports")
                sessions_msg = md()

                @gr.render(inputs=[version, viewer])
                def show_sessions(_version, user):
                    try:
                        sessions = backend.session_views()
                    except SpaceError as exc:
                        md(f"**{exc}**")
                        return
                    if not sessions:
                        md("*No session has written a brief yet.*")
                    lead = backend.is_lead(user)
                    for i, session in enumerate(sessions):
                        with gr.Accordion(session["title"], open=i == 0):
                            md(session["markdown"])
                            pending = [p for p in session["proposals"] if p["status"] == "working"] if lead else []
                            if pending:
                                md("**Record a proposed promotion.** It is your judgment whether the evidence is robust.")
                            for p in pending:
                                with gr.Row(equal_height=True):
                                    reason = gr.Textbox(p["reason"], label=f"{p['card']}: {p['statement']}", scale=4)
                                    button = gr.Button(f"Promote {p['card']}", variant="primary", scale=1)
                                button.click(promoter(p["card"]), reason, sessions_msg).then(views, VIEW_INPUTS, VIEW_OUTPUTS)

            # ----- Write a card -----
            with gr.Tab("Write a card", id="write"):
                md("A **question** card asks the agents something: open questions are what the next sessions work on. "
                   "A **claim** card records an idea or a result obtained by hand; it starts with no evidence, "
                   "and anyone can verify it. Cards are never edited once written: to change one, write a claim "
                   "that supersedes it.")
                w_kind = gr.Radio(["question", "claim"], value="question", label="Kind")
                w_statement = gr.Textbox(lines=2, label="Statement",
                                         info="One sentence. Equations in LaTeX between $…$.")
                w_body = gr.Textbox(lines=8, label="Body",
                                    info="Context, the idea, or the steps of a hand derivation (Markdown and LaTeX).")
                w_depends = gr.Dropdown(label="Depends on", multiselect=True, choices=[])
                w_answers = gr.Dropdown(label="Answers these open questions", multiselect=True, choices=[], visible=False)
                w_supersedes = gr.Dropdown(label="Supersedes (revises) these claims", multiselect=True, choices=[],
                                           visible=False)
                with gr.Accordion("Preview", open=True):
                    w_preview = md()
                w_btn = gr.Button("Write the card", variant="primary")
                w_msg = md()

            # ----- Edit the lead's files -----
            with gr.Tab("Edit", id="edit"):
                md("These four files belong to the lead scientist. When a lead saves, the change is committed to "
                   "main. When anyone else saves, the Space opens a pull request that a lead merges, edits or closes.")
                e_file = gr.Radio(list(LEAD_FILES), value=LEAD_FILES[0], label="File")
                with gr.Row():
                    e_text = gr.Textbox(lines=24, max_lines=60, label="Text (Markdown, LaTeX between $…$)", scale=1)
                    with gr.Column(scale=1):
                        md("**Preview**")
                        e_preview = md()
                e_base = gr.State("")  # the text on main when the editor was loaded
                with gr.Row():
                    e_save = gr.Button("Save", variant="primary")
                    e_reload = gr.Button("Reload from main")
                e_msg = md()
                md("### Open proposals")
                md("Pull requests other than sessions: changes to these files, and method upgrades.")
                e_props = md()
                with gr.Row(visible=False) as merge_row:
                    e_pr = gr.Dropdown(label="Proposal to merge (leads)", choices=[], scale=3)
                    e_merge = gr.Button("Merge into main", scale=1)
                e_merge_msg = md()

        # ----- computed views -----

        def card_panel(card_id):
            """The card view, its related cards and the artefacts a verification may name."""
            try:
                related = sorted({i for _, ids in backend.related(card_id) for i in ids}) if card_id else []
                targets = [NO_TARGET] + backend.artefact_choices(card_id)
                text = backend.card_markdown(card_id)
            except SpaceError as exc:
                related, targets, text = [], [NO_TARGET], f"**{exc}**"
            return {card_md: text, related_dd: gr.Dropdown(choices=related, value=None),
                    v_target: gr.Dropdown(choices=targets, value=NO_TARGET)}

        def index_views(filter_name, text, card_id):
            try:
                choices = backend.card_choices(filter_name, text)
                if card_id and card_id not in [v for _, v in choices]:
                    choices.append((card_id, card_id))  # keep the open card even when the filter hides it
                return {index: backend.index_markdown(filter_name, text), card_dd: gr.Dropdown(choices=choices, value=card_id)}
            except SpaceError as exc:
                return {index: f"**{exc}**"}

        def views(filter_name, text, card_id, paper_id, version_value):
            """Every view that depends on the workspace, recomputed from the loaded snapshot."""
            try:
                snap = backend.current()
            except SpaceError as exc:
                return {status: f"**{exc}**", overview: f"**{exc}**", version: version_value + 1}
            card_id = card_id if card_id in snap.ws.cards else None
            paper_id = paper_id if paper_id in snap.ws.papers else None
            every_card = backend.choices()
            return {
                status: backend.status_markdown(), banner: backend.chat_banner(),
                overview: backend.overview_markdown(),
                **index_views(filter_name, text, card_id), **card_panel(card_id),
                chat_card: gr.Dropdown(choices=every_card),
                questions: backend.questions_markdown(),
                papers: backend.papers_markdown(), paper_dd: gr.Dropdown(choices=backend.paper_choices(), value=paper_id),
                paper_md: backend.paper_markdown(paper_id),
                open_sessions: backend.open_sessions_markdown(),
                w_depends: gr.Dropdown(choices=every_card), w_answers: gr.Dropdown(choices=backend.choices("question", "open")),
                w_supersedes: gr.Dropdown(choices=backend.choices("claim")),
                e_props: backend.proposals_markdown(),
                e_pr: gr.Dropdown(choices=[(f"#{pr['num']} {pr['title']}", pr["num"]) for pr in backend.proposal_prs()],
                                  value=None),
                version: version_value + 1,
            }

        def load_file(path):
            try:
                text = backend.lead_file(path)
            except SpaceError as exc:
                return {e_text: "", e_base: "", e_preview: f"**{exc}**"}
            return {e_text: text, e_base: text, e_preview: text}

        VIEW_INPUTS = [flt, query, card_dd, paper_dd, version]
        VIEW_OUTPUTS = [status, banner, overview, index, card_dd, card_md, related_dd, v_target, chat_card, questions,
                        papers, paper_dd, paper_md, open_sessions, w_depends, w_answers, w_supersedes, e_props, e_pr,
                        version]
        FILE_OUTPUTS = [e_text, e_base, e_preview]

        def on_load(filter_name, text, card_id, paper_id, version_value, path, profile: gr.OAuthProfile | None):
            backend.refresh_if_stale()
            user = user_of(profile)
            lead = backend.is_lead(user)
            out = views(filter_name, text, card_id, paper_id, version_value)
            out.update({viewer: user, who: backend.who_markdown(user), promote_box: gr.Accordion(visible=lead),
                        merge_row: gr.Row(visible=lead)})
            out.update(load_file(path))
            return out

        def on_refresh(*args):
            backend.refresh()
            return views(*args)

        demo.load(on_load, VIEW_INPUTS + [e_file], VIEW_OUTPUTS + [viewer, who, promote_box, merge_row] + FILE_OUTPUTS)
        refresh_btn.click(on_refresh, VIEW_INPUTS, VIEW_OUTPUTS)

        # ----- Results -----

        flt.change(index_views, [flt, query, card_dd], [index, card_dd])
        query.change(index_views, [flt, query, card_dd], [index, card_dd], trigger_mode="always_last",
                     show_progress="hidden")
        card_dd.change(card_panel, card_dd, [card_md, related_dd, v_target])

        def open_related(filter_name, text, card_id):
            return index_views(filter_name, text, card_id).get(card_dd, gr.skip()) if card_id else gr.skip()

        related_dd.input(open_related, [flt, query, related_dd], card_dd)

        def reacter(value):
            def react(card_id, comment, profile: gr.OAuthProfile | None):
                if not card_id:
                    return "Choose a card first.", gr.skip()
                ok, message = attempt(backend.react, user_of(profile), card_id, value, comment)
                return message, ("" if ok else gr.skip())
            return react

        for value, button in react_btns.items():
            button.click(reacter(value), [card_dd, react_comment], [react_msg, react_comment]).then(
                views, VIEW_INPUTS, VIEW_OUTPUTS)

        def on_verify(card_id, verdict_value, target, body, profile: gr.OAuthProfile | None):
            if not card_id:
                return "Choose a claim first.", gr.skip()
            target = None if target in (None, "", NO_TARGET) else target
            ok, message = attempt(backend.verify, user_of(profile), card_id, verdict_value, body, target)
            return message, ("" if ok else gr.skip())

        v_btn.click(on_verify, [card_dd, verdict, v_target, v_body], [v_msg, v_body]).then(views, VIEW_INPUTS, VIEW_OUTPUTS)

        def promoter(card_id):
            def promote(reason, profile: gr.OAuthProfile | None):
                return attempt(backend.promote, user_of(profile), card_id, reason)[1]
            return promote

        def on_promote(card_id, reason, profile: gr.OAuthProfile | None):
            if not card_id:
                return "Choose a claim first.", gr.skip()
            ok, message = attempt(backend.promote, user_of(profile), card_id, reason)
            return message, ("" if ok else gr.skip())

        p_btn.click(on_promote, [card_dd, p_reason], [p_msg, p_reason]).then(views, VIEW_INPUTS, VIEW_OUTPUTS)

        # ----- Explain -----

        explain_btn.click(lambda c: (gr.Tabs(selected="explain"), gr.Dropdown(value=c), [], ""), card_dd,
                          [tabs, chat_card, chatbot, read_note])
        chat_card.input(lambda: ([], ""), None, [chatbot, read_note])  # a new card starts a new conversation

        def on_ask(text, history, card_id, level_name, profile: gr.OAuthProfile | None, token: gr.OAuthToken | None):
            text = (text or "").strip()
            if not text:
                return gr.skip(), gr.skip(), gr.skip()
            history = chat.plain_history(history)
            reply, note = chat.respond(backend, user_of(profile), token.token if token else None, card_id, history,
                                       text, level_name)
            return history + [{"role": "user", "content": text}, {"role": "assistant", "content": reply}], "", note

        question.submit(on_ask, [question, chatbot, chat_card, level], [chatbot, question, read_note])

        def on_to_card(history, card_id):
            asked, replied = chat.last_exchange(history)
            if not asked:
                return {read_note: "Ask the chat a question first."}
            return {tabs: gr.Tabs(selected="write"), w_kind: "question", w_statement: asked,
                    w_body: chat.question_card_body(card_id, asked, replied), w_depends: [card_id] if card_id else [],
                    w_msg: "Edit the card, then press *Write the card*. It is written under your name."}

        to_card_btn.click(on_to_card, [chatbot, chat_card], [read_note, tabs, w_kind, w_statement, w_body, w_depends, w_msg])

        # ----- Questions, Literature -----

        ask_btn.click(lambda: (gr.Tabs(selected="write"), "question"), None, [tabs, w_kind])
        def paper_panel(paper_id):
            try:
                return backend.paper_markdown(paper_id)
            except SpaceError as exc:
                return f"**{exc}**"

        paper_dd.change(paper_panel, paper_dd, paper_md)

        def triager(value):
            def triage(paper_id, profile: gr.OAuthProfile | None):
                if not paper_id:
                    return "Choose a paper first."
                return attempt(backend.react, user_of(profile), paper_id, value, "")[1]
            return triage

        for value, button in triage_btns.items():
            button.click(triager(value), paper_dd, triage_msg).then(views, VIEW_INPUTS, VIEW_OUTPUTS)

        # ----- Write a card -----

        w_kind.change(lambda k: (gr.Dropdown(visible=k == "claim"), gr.Dropdown(visible=k == "claim")), w_kind,
                      [w_answers, w_supersedes])
        for box in (w_statement, w_body):
            box.change(lambda s, b: f"> {s}\n\n{b}" if s or b else "", [w_statement, w_body], w_preview,
                       show_progress="hidden")

        def on_write(kind, statement, body, depends_on, answers, supersedes, profile: gr.OAuthProfile | None):
            ok, message = attempt(backend.write_card, user_of(profile), kind, statement, body, depends_on, answers,
                                  supersedes)
            if not ok:
                return message, gr.skip(), gr.skip(), gr.skip(), gr.skip(), gr.skip()
            return message, "", "", [], [], []

        w_btn.click(on_write, [w_kind, w_statement, w_body, w_depends, w_answers, w_supersedes],
                    [w_msg, w_statement, w_body, w_depends, w_answers, w_supersedes]).then(views, VIEW_INPUTS, VIEW_OUTPUTS)

        # ----- Edit -----

        e_file.change(load_file, e_file, FILE_OUTPUTS)
        e_reload.click(load_file, e_file, FILE_OUTPUTS)
        e_text.change(lambda t: t, e_text, e_preview, show_progress="hidden")

        def on_save(path, text, base, profile: gr.OAuthProfile | None):
            ok, message = attempt(backend.save_lead_file, user_of(profile), path, text, base)
            if not ok:
                return {e_msg: message}
            return {e_msg: message, **load_file(path)}  # main after the save (a proposal leaves main unchanged)

        e_save.click(on_save, [e_file, e_text, e_base], [e_msg] + FILE_OUTPUTS).then(views, VIEW_INPUTS, VIEW_OUTPUTS)

        def on_merge(number, path, profile: gr.OAuthProfile | None):
            ok, message = attempt(backend.merge_proposal, user_of(profile), number)
            return {e_merge_msg: message, **(load_file(path) if ok else {})}

        e_merge.click(on_merge, [e_pr, e_file], [e_merge_msg] + FILE_OUTPUTS).then(views, VIEW_INPUTS, VIEW_OUTPUTS)

    return demo


backend = Backend.from_env()
demo = build(backend)

if __name__ == "__main__":
    demo.launch()
