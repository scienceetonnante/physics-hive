"""The PhysicsIntern Space: a browser interface to a shared research workspace.

Two pages, and one page per object. *Status* says where the project stands and
what waits for a person; *Results* lists every card. Each card, paper, session,
proposal and file has its own page, so that any of them can be sent as a link,
and every card ID in a text links to its card.

People write in two ways, and both become cards that the next session reads:
*Write to the agents* (a question card, linked to the card at hand) and
*Answer* (a claim card that answers an open question). Leads also edit their
files, merge or close proposals, and promote claims. This file is the user
interface only: reading and writing the workspace is in backend.py.

Every write takes the signed-in user from the sign-in session itself
(`parse_huggingface_oauth`), never from a value the page sends.

Run it on a local workspace folder, without the Hub and without sign-in:
    PHYSICS_INTERN_LOCAL=/path/to/workspace PHYSICS_INTERN_LOCAL_USER=alice uvicorn app:app --reload
"""

import re
import secrets
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from huggingface_hub import attach_huggingface_oauth, parse_huggingface_oauth
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup
from mdit_py_plugins.dollarmath import dollarmath_plugin
from starlette.middleware.sessions import SessionMiddleware

from backend import Backend, SpaceError

HERE = Path(__file__).resolve().parent
# Workspace paths, card, paper, artefact and critique IDs, session numbers and pull request numbers.
# Only those that exist become links.
ID_RE = re.compile(r"[\w.-]+(?:/[\w.-]+)+\.\w+|\b(?:CL|CR|DE|Q|P|D|C)-[\w.-]*[A-Za-z0-9]|\bS\d+\b|(?<![\w&])#\d+\b")


# ----- Markdown with equations and links -----


def href_of(word: str) -> str | None:
    """The page of an ID, or of a workspace file named in a code span."""
    if backend.snap is None:
        return None
    ws = backend.snap.ws
    if word in ws.cards:
        return f"/card/{word}"
    if word in ws.papers:
        return f"/paper/{word}"
    if word in ws.sessions:
        return f"/session/{word}"
    if word in ws.artefacts:
        return f"/file/{ws.artefacts[word].path}"
    if word.startswith("#") and int(word[1:]) in {pr["num"] for pr in backend.proposal_prs()}:
        return f"/proposal/{word[1:]}"
    for rel in (word, f"critiques/{word}.md"):
        if "/" in rel and backend.file_path(rel):
            return f"/file/{rel}"
    return None


def link(content: Token, href: str) -> list[Token]:
    return [Token("link_open", "a", 1, attrs={"href": href}), content, Token("link_close", "a", -1)]


def link_ids(state) -> None:
    """Turn every existing ID in the text, and every code span naming a workspace file, into a link."""
    for block in state.tokens:
        if block.type != "inline" or not block.children:
            continue
        children, in_link = [], 0
        for child in block.children:
            in_link += {"link_open": 1, "link_close": -1}.get(child.type, 0)
            if in_link or child.type not in ("text", "code_inline"):
                children.append(child)
            elif child.type == "code_inline":
                href = href_of(child.content)
                children += link(child, href) if href else [child]
            else:
                start = 0
                for m in ID_RE.finditer(child.content):
                    href = href_of(m.group())
                    if href:
                        children.append(Token("text", "", 0, content=child.content[start:m.start()]))
                        children += link(Token("text", "", 0, content=m.group()), href)
                        start = m.end()
                children.append(Token("text", "", 0, content=child.content[start:]))
        block.children = children


# Raw HTML in the workspace's files is shown as text: agents write them.
MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"]).use(dollarmath_plugin)
MD.core.ruler.push("link_ids", link_ids)


def md(text) -> Markup:
    return Markup(MD.render(str(text or "")))


def md_inline(text) -> Markup:
    return Markup(MD.renderInline(" ".join(str(text or "").split())))


# ----- the app -----

backend = Backend.from_env()


def fresh(request: Request) -> None:
    """Load the workspace again when a page is viewed more than two minutes after the last load."""
    if request.method == "GET" and not request.url.path.startswith("/oauth/"):
        backend.refresh_if_stale()


app = FastAPI(title="PhysicsIntern", docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(fresh)])
if backend.local:
    app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
else:
    attach_huggingface_oauth(app)  # adds the session, and the sign-in and sign-out pages
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters.update(md=md, md_inline=md_inline)


def signed_in(request: Request) -> str | None:
    if backend.local:
        return backend.user(None)
    info = parse_huggingface_oauth(request)
    return info.user_info.preferred_username if info else None


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(16)
    return token


def check_form(request: Request, token: str) -> str | None:
    """The user behind a form, once the form is known to come from this Space's own page."""
    if not token or token != request.session.get("csrf"):
        raise SpaceError("This page was out of date. Reload it and try again.")
    return signed_in(request)


def page(request: Request, template: str, status_code: int = 200, **context) -> HTMLResponse:
    user = signed_in(request)
    here = quote(request.url.path)
    context.update(request=request, user=user, lead=backend.is_lead(user), local=backend.local,
                   name=backend.project_name(), status=backend.status_markdown(), csrf=csrf_token(request),
                   flash=request.session.pop("flash", None), here=request.url.path,
                   sign_in=f"/oauth/huggingface/login?_target_url={here}",
                   sign_out=f"/oauth/huggingface/logout?_target_url={here}")
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def done(request: Request, message: str, url: str) -> RedirectResponse:
    request.session["flash"] = message
    return RedirectResponse(url, status_code=303)


@app.exception_handler(SpaceError)
def show_problem(request: Request, exc: SpaceError) -> HTMLResponse:
    return page(request, "problem.html", status_code=503 if backend.snap is None else 404, problem=str(exc))


# ----- pages -----


def status_page(request: Request, **extra) -> HTMLResponse:
    return page(request, "status.html", problem_text=backend.lead_text("problem.md"),
                plan=backend.lead_text("plan.md"), conventions=backend.lead_text("conventions.md"),
                attention=backend.attention(), counts=backend.counts(), sessions=backend.sessions(),
                running=backend.open_sessions(), commits=backend.commits, **extra)


def card_page(request: Request, card_id: str, **extra) -> HTMLResponse:
    return page(request, "card.html", **backend.card(card_id), **extra)


def paper_page(request: Request, paper_id: str, **extra) -> HTMLResponse:
    return page(request, "paper.html", **backend.paper(paper_id), **extra)


@app.get("/", response_class=HTMLResponse)
def status(request: Request):
    return status_page(request)


@app.get("/results", response_class=HTMLResponse)
def results(request: Request):
    return page(request, "results.html", **backend.results(), seeds=backend.lead_text("literature/seeds.md"))


@app.get("/card/{card_id}", response_class=HTMLResponse)
def card(request: Request, card_id: str):
    return card_page(request, card_id)


@app.get("/paper/{paper_id}", response_class=HTMLResponse)
def paper(request: Request, paper_id: str):
    return paper_page(request, paper_id)


@app.get("/session/{session_id}", response_class=HTMLResponse)
def session(request: Request, session_id: str):
    return page(request, "session.html", **backend.session(session_id))


@app.get("/proposal/{number}", response_class=HTMLResponse)
def proposal(request: Request, number: str):
    return page(request, "proposal.html", pr=backend.proposal(number))


@app.get("/file/{rel:path}", response_class=HTMLResponse)
def file(request: Request, rel: str):
    return page(request, "file.html", **backend.file(rel))


@app.get("/edit/{rel:path}", response_class=HTMLResponse)
def edit(request: Request, rel: str):
    text = backend.lead_file(rel)
    return page(request, "edit.html", path=rel, text=text, base=text, preview=None)


@app.get("/refresh")
def refresh(request: Request, back: str = "/"):
    backend.refresh()
    return RedirectResponse(back if back.startswith("/") and not back.startswith("//") else "/", status_code=303)


# ----- writes -----


@app.post("/ask")
def ask(request: Request, text: str = Form(""), about: str = Form(""), csrf: str = Form("")):
    back = f"/card/{about}" if about in backend.current().ws.cards else (
        f"/paper/{about}" if about in backend.current().ws.papers else "/")
    try:
        message = backend.ask(check_form(request, csrf), text, about or None)
    except SpaceError as exc:
        extra = {"error": str(exc), "draft": text, "draft_for": "ask"}
        if back.startswith("/card/"):
            return card_page(request, about, **extra)
        if back.startswith("/paper/"):
            return paper_page(request, about, **extra)
        return status_page(request, **extra)
    return done(request, message, back)


@app.post("/card/{card_id}/answer")
def answer(request: Request, card_id: str, text: str = Form(""), csrf: str = Form("")):
    try:
        message = backend.answer(check_form(request, csrf), card_id, text)
    except SpaceError as exc:
        return card_page(request, card_id, error=str(exc), draft=text, draft_for="answer")
    return done(request, message, f"/card/{card_id}")


@app.post("/card/{card_id}/promote")
def promote(request: Request, card_id: str, reason: str = Form(""), csrf: str = Form("")):
    try:
        message = backend.promote(check_form(request, csrf), card_id, reason)
    except SpaceError as exc:
        return card_page(request, card_id, error=str(exc), draft=reason, draft_for="promote")
    return done(request, message, f"/card/{card_id}")


@app.post("/edit/{rel:path}")
def save(request: Request, rel: str, text: str = Form(""), base: str = Form(""), action: str = Form("save"),
         csrf: str = Form("")):
    if action == "preview":
        return page(request, "edit.html", path=rel, text=text, base=base, preview=text)
    try:
        message = backend.save_lead_file(check_form(request, csrf), rel, text, base)
    except SpaceError as exc:
        return page(request, "edit.html", path=rel, text=text, base=base, preview=None, error=str(exc))
    return done(request, message, "/results" if rel == "literature/seeds.md" else "/")


@app.post("/proposal/{number}/{action}")
def settle(request: Request, number: str, action: str, csrf: str = Form("")):
    settle_with = {"merge": backend.merge_proposal, "close": backend.close_proposal}.get(action)
    try:
        if settle_with is None:
            raise SpaceError(f"A proposal is merged or closed, not {action!r}.")
        message = settle_with(check_form(request, csrf), number)
    except SpaceError as exc:
        return page(request, "proposal.html", pr=backend.proposal(number), error=str(exc))
    return done(request, message, "/")
