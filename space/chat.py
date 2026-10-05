"""The explainer chat of the Space.

A lightweight open model, called through Hugging Face inference providers with
the reader's own sign-in token (so that the inference cost is theirs), explains
the project's results. It reads the workspace through four read-only tools
(open a card, open an artefact, open a paper card, search the index); none of
them writes. Opened from a card, it starts with that card and the summaries of
its artefacts.

The chat explains; it does not verify. Its answers carry no evidential weight,
and the page says so. In normal mode nothing is stored. In debug mode
(`CHAT_DEBUG=1`) each exchange is logged to the chat_debug dataset named in
project.toml, never to the workspace, and the page shows a banner.
"""

from __future__ import annotations

import json

from huggingface_hub import InferenceClient

from backend import Backend, SpaceError, clip, iso, now_utc, origin_text

DEFAULT_MODEL = "openai/gpt-oss-20b"
MAX_TOOL_ROUNDS = 6  # tool calls the model may chain before it must answer
MAX_TOOL_CHARS = 20_000  # longest tool result passed to the model
MAX_OPENING_CHARS = 40_000  # longest opening context (the card and its evidence summaries)
MAX_TOKENS = 4000  # reasoning models spend part of it before answering

LEVELS = {
    "Terse and technical": "the reader is a physicist. Answer tersely and technically, in a few sentences and "
                           "equations, without background they already know.",
    "Step by step": "the reader wants to follow the reasoning. Go step by step: say what each step does and why, "
                    "define the notation, and do not skip algebra.",
}

SYSTEM_PROMPT = """You are the explainer of a PhysicsIntern research project, in which humans and AI agents work on one physics question.

The project records its results as cards: claims (CL-…), questions (Q-…) and dead ends (DE-…). A claim's status is computed from other files: working; established (a lead promoted it); revised (a later claim supersedes it); refuted (a dead end refutes it). Its evidence is derivations (D-…) and computations (C-…), each with a one-page summary, full material (a LaTeX derivation or a Python script) and reviews, and human verifications. Paper cards (P-…) describe papers from the literature.

A reader of the project's web page asks you to explain a result. Follow these rules.

1. Answer from the project. Open what you need with the tools, and cite what you rely on: card IDs, artefact IDs with equation numbers (for example "D-S3-2, eq. (12)"), paper cards. Never invent an equation, a reference or a result.
2. When the project does not contain the answer, say so plainly, in a sentence of its own that starts with "The project does not contain". You may then add general background, labelled as such and kept apart from what the project says.
3. You explain; you do not verify. Do not say that a result is correct or proven: report its status and its evidence as the project records them. If a step does not seem to follow, say so; it may be a gap worth a question card.
4. Level: {level}

Write equations in LaTeX between $…$ (inline) or $$…$$ (display). Keep answers short unless the reader asks for detail."""


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties,
                                                            "required": required}}}


TOOLS = [
    _tool("open_card", "Open a card (claim CL-…, question Q-… or dead end DE-…): its statement, computed status, "
          "body, linked cards and evidence.",
          {"card_id": {"type": "string", "description": "The card ID, for example CL-S3-2."}}, ["card_id"]),
    _tool("open_artefact", "Open a derivation (D-…) or a computation (C-…): its one-page summary, its full "
          "material (the LaTeX derivation, the Python script and its outputs), or its reviews.",
          {"artefact_id": {"type": "string", "description": "The artefact ID, for example D-S3-2."},
           "part": {"type": "string", "enum": ["summary", "full", "reviews"], "description": "What to open."}},
          ["artefact_id"]),
    _tool("open_paper", "Open a paper card (P-<arXiv id>): the paper's question, method, main result, assumptions, "
          "conventions, and why it matters here.",
          {"paper_id": {"type": "string", "description": "The paper card ID, for example P-2301.01234."}}, ["paper_id"]),
    _tool("search_index", "Search the project's index (one line per card, artefact and paper) by keywords. "
          "Returns the matching lines, best matches first.",
          {"query": {"type": "string", "description": "A few keywords."}}, ["query"]),
]


class Tools:
    """The chat's read-only view of the workspace, as text for the model."""

    def __init__(self, backend: Backend):
        self.backend = backend
        self.snap = backend.current()

    def open_card(self, card_id: str) -> str:
        ws, regen = self.snap.ws, self.snap.m.regen
        card = ws.cards.get(str(card_id).strip())
        if card is None:
            return f"There is no card {card_id!r}. Use search_index to find card IDs."
        lines = [f"Card {card.id} ({card.kind}), status: {regen.status_text(ws, card.id)}."]
        recheck = regen.recheck_text(ws, card.id)
        if recheck:
            lines.append(recheck.capitalize() + ".")
        lines.append(f"Statement: {card.statement}")
        for label, ids in self.backend.related(card.id):
            linked = [f"{i} ({ws.status(i)}): {regen.one_line(ws.cards[i].statement, 200)}" if i in ws.cards else i
                      for i in ids]
            lines.append(f"{label}: " + "; ".join(linked))
        if card.kind == "claim":
            lines.append("Evidence: " + (", ".join(regen.evidence_parts(ws, card.id)) or "none"))
        lines.append(f"Origin: {origin_text(card)}.")
        lines += ["", "Body:", card.body.strip() or "(empty)"]
        return clip("\n".join(lines), MAX_TOOL_CHARS)

    def open_artefact(self, artefact_id: str, part: str = "summary") -> str:
        ws, regen = self.snap.ws, self.snap.m.regen
        art = ws.artefacts.get(str(artefact_id).strip())
        if art is None:
            return f"There is no artefact {artefact_id!r} (derivations are D-…, computations C-…)."
        if part == "full":
            if not art.full:
                return f"{art.id} has no full material next to its summary."
            return clip("\n\n".join(f"=== {p} ===\n{self.backend.read(p)}" for p in art.full), MAX_TOOL_CHARS)
        reviews = ws.reviews_of(art.id)
        if part == "reviews":
            if not reviews:
                return f"{art.id} has no review yet."
            return clip("\n\n".join(
                f"=== Review {regen.review_label(r)}: {r.verdict}; it concerns {', '.join(r.supports) or ', '.join(art.supports)} ===\n"
                f"{self.backend.body(r.path)}" for r in reviews), MAX_TOOL_CHARS)
        verdicts = "; ".join(f"{regen.review_label(r)} {r.verdict}" for r in reviews) or "none yet"
        head = (f"{art.id} ({art.kind}). Supports: {', '.join(art.supports) or 'nothing'}. "
                f"Full material: {', '.join(art.full) or 'none'}. Reviews: {verdicts}.")
        return clip(head + "\n\n" + self.backend.body(art.path), MAX_TOOL_CHARS)

    def open_paper(self, paper_id: str) -> str:
        paper = self.snap.ws.papers.get(str(paper_id).strip())
        if paper is None:
            return f"There is no paper card {paper_id!r}. Use search_index to find paper IDs."
        return clip(self.backend.read(paper.path), MAX_TOOL_CHARS)

    def search_index(self, query: str) -> str:
        words = [w.strip(".,;:!?()[]'\"").lower() for w in str(query).split()]
        words = [w for w in words if len(w) > 1]
        if not words:
            return "Give one or more keywords."
        lines = [line for line in self.snap.m.regen.render_index(self.snap.ws).splitlines() if line.startswith("- ")]
        scored = [(sum(w in line.lower() for w in words), i, line) for i, line in enumerate(lines)]
        hits = [line for score, _, line in sorted(scored, key=lambda t: (-t[0], t[1])) if score > 0][:15]
        return "\n".join(hits) if hits else f"Nothing in the index matches {query!r}."

    def call(self, name: str, arguments: dict) -> str:
        """Run one tool call from the model; failures come back as text the model can read."""
        try:
            if name == "open_card":
                return self.open_card(arguments.get("card_id", ""))
            if name == "open_artefact":
                return self.open_artefact(arguments.get("artefact_id", ""), arguments.get("part") or "summary")
            if name == "open_paper":
                return self.open_paper(arguments.get("paper_id", ""))
            if name == "search_index":
                return self.search_index(arguments.get("query", ""))
        except Exception as exc:
            return f"The tool {name} failed: {type(exc).__name__}: {exc}"
        return f"There is no tool {name!r}."

    def opening(self, card_id: str | None) -> str:
        """What the chat starts with: the card at hand and the summaries of its evidence."""
        ws = self.snap.ws
        if not card_id or card_id not in ws.cards:
            return ""
        parts = [self.open_card(card_id)]
        for ev in ws.evidence(card_id):
            if ev.artefact:
                parts.append(self.open_artefact(ev.artefact, "summary"))
            elif ev.verification is not None:
                r = ev.verification
                parts.append(f"Human verification {self.snap.m.regen.review_label(r)}: {r.verdict}\n{self.backend.body(r.path)}")
        return clip("\n\n".join(parts), MAX_OPENING_CHARS)


# ----- one answer -----


def chat_model(backend: Backend) -> str:
    return backend.chat_model() or DEFAULT_MODEL


def system_prompt(level: str, opening: str) -> str:
    prompt = SYSTEM_PROMPT.format(level=LEVELS.get(level, next(iter(LEVELS.values()))))
    if opening:
        return prompt + "\n\nThe reader opened the chat from this card. Its contents and the summaries of its evidence:\n\n" + opening
    return prompt + "\n\nThe reader has not chosen a card."


def message_text(content) -> str:
    """The text of a chat message, whether Gradio gives it as a string or as a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if isinstance(content, (list, tuple)):
        return "\n".join(message_text(part) for part in content if part)
    return "" if content is None else str(content)


def plain_history(history) -> list[dict]:
    """The conversation as plain {role, content} messages, user and assistant only."""
    out = []
    for message in history or []:
        role = message.get("role") if isinstance(message, dict) else None
        text = message_text(message.get("content")) if role else ""
        if role in ("user", "assistant") and text.strip():
            out.append({"role": role, "content": text})
    return out


def _arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def answer(backend: Backend, card_id: str | None, history: list[dict], question: str, level: str,
           token: str | None, client=None) -> tuple[str, list[dict]]:
    """Ask the model, letting it call the read-only tools. Returns the reply and the tool calls made."""
    tools = Tools(backend)
    client = client or InferenceClient(model=chat_model(backend), token=token)
    messages = [{"role": "system", "content": system_prompt(level, tools.opening(card_id))}]
    messages += plain_history(history) + [{"role": "user", "content": question}]
    calls: list[dict] = []
    for round_number in range(MAX_TOOL_ROUNDS + 1):
        last = round_number == MAX_TOOL_ROUNDS  # after this many rounds the model must answer
        response = client.chat_completion(messages, tools=TOOLS, tool_choice="none" if last else "auto",
                                          max_tokens=MAX_TOKENS)
        message = response.choices[0].message
        tool_calls = [] if last else list(message.tool_calls or [])
        if not tool_calls:
            return (message.content or "").strip() or "(The model returned no text.)", calls
        messages.append({"role": "assistant", "content": message.content or "", "tool_calls": [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": json.dumps(_arguments(c.function.arguments))}}
            for c in tool_calls]})
        for c in tool_calls:
            arguments = _arguments(c.function.arguments)
            calls.append({"name": c.function.name, "arguments": arguments})
            messages.append({"role": "tool", "tool_call_id": c.id, "content": tools.call(c.function.name, arguments)})
    return "(The model did not answer.)", calls


def describe(call: dict) -> str:
    args = call["arguments"]
    if call["name"] == "search_index":
        return f"search “{args.get('query', '')}”"
    target = args.get("card_id") or args.get("artefact_id") or args.get("paper_id") or "?"
    part = args.get("part")
    return f"{target} ({part})" if part and part != "summary" else target


def respond(backend: Backend, user: str | None, token: str | None, card_id: str | None, history, question: str,
            level: str, client=None) -> tuple[str, str]:
    """Answer one question for the page: (reply, a note on what the chat read). Logs it in debug mode."""
    question = (question or "").strip()
    if not backend.local and (not user or not token):
        return ("Sign in with your Hugging Face account to use the chat: it runs on your own inference credits.", "")
    calls: list[dict] = []
    try:
        reply, calls = answer(backend, card_id, history, question, level, token, client)
    except SpaceError as exc:
        reply = str(exc)
    except Exception as exc:
        reply = (f"The chat model could not answer ({type(exc).__name__}: {exc}). If the error mentions 401 or 403, "
                 "sign out and sign in again, so that the Space may use your inference credits.")
    if backend.chat_debug:
        record = {"date": iso(now_utc()), "user": user or "local", "card": card_id, "level": level,
                  "model": chat_model(backend) if backend.snap else None, "question": question, "answer": reply,
                  "tool_calls": calls, "earlier_messages": len(plain_history(history))}
        try:
            backend.log_chat(record)
        except Exception as exc:  # a debug log must never break the chat
            print(f"chat debug log failed: {exc}")
    note = ("Read for this answer: " + ", ".join(describe(c) for c in calls) + ".") if calls else ""
    return reply, note


# ----- the question-card button -----


def last_exchange(history) -> tuple[str, str]:
    """The reader's last question and the chat's answer to it ('' when there is none)."""
    messages = plain_history(history)
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
            reply = messages[i + 1]["content"] if i + 1 < len(messages) else ""
            return messages[i]["content"], reply
    return "", ""


def question_card_body(card_id: str | None, question: str, reply: str) -> str:
    """Body of the question card that the button under the chat pre-fills."""
    quoted = "\n".join("> " + line for line in reply.strip().splitlines()) or "> (no answer)"
    about = f" about {card_id}" if card_id else ""
    return (f"Asked in the explainer chat{about}:\n\n> {question.strip()}\n\n"
            f"The chat answered (an explanation, not a verification):\n\n{quoted}\n")
