"""The PhysicsHive Space: the researcher's view of a research workspace, in a browser.

Five pages, each showing files (design, section 14):

- Project: project.md and conventions.md, each with an editor;
- Review (the first page, at /): the debriefs, newest first (open ones in full,
  as forms: answers, ticks, the note; closed ones folded);
- Draft: draft.tex rendered like an arXiv HTML paper, an editor with a preview
  beside it, and the PDF;
- Sessions: one line per session; each opens its note, rendered the same way;
- Literature: the overview, then the papers by topic with their one-line reason
  and a rating menu.

The session record (cards, artefacts, reviews, logs) keeps its own pages,
reached from the notes, the draft and the Sessions page. Nobody is sent there by
default. The Space applies nothing: it writes files, and the next session
applies what the researcher ticked. This file is the user interface only;
reading and writing the workspace is in backend.py.

Every write takes the signed-in user from the sign-in session itself
(`parse_huggingface_oauth`), never from a value the page sends.

Run it on a local workspace folder, without the Hub and without sign-in:
    PHYSICS_HIVE_LOCAL=/path/to/workspace PHYSICS_HIVE_LOCAL_USER=alice uvicorn app:app --reload
"""

import logging
import re
import secrets
from html import escape
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from huggingface_hub import attach_huggingface_oauth, parse_huggingface_oauth
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup
from mdit_py_plugins.dollarmath import dollarmath_plugin
from starlette.middleware.sessions import SessionMiddleware

import latex
from backend import Backend, SpaceError, log

HERE = Path(__file__).resolve().parent
# Workspace paths, card, paper, artefact and critique IDs, and session numbers. Only those that exist become links.
ID_RE = re.compile(r"[\w.-]+(?:/[\w.-]+)+\.\w+|\b(?:CL|CR|DE|P|D|C)-[\w.-]*[A-Za-z0-9]|\bS\d+\b")
NOTE_RE = re.compile(r"^sessions/(S\d+)/note\.tex$")


# ----- Markdown with equations and links -----


def href_of(word: str) -> str | None:
    """The page of an ID, or of a workspace file named in a code span. A session's ID opens its note."""
    if backend.snap is None:
        return None
    ws = backend.snap.ws
    if word in ws.cards:
        return f"/card/{word}"
    if word in ws.papers:
        return f"/paper/{word}"
    if word in ws.sessions:
        return f"/note/{word}" if ws.sessions[word].has_note else f"/session/{word}"
    if word in ws.artefacts:
        return f"/file/{ws.artefacts[word].path}"
    m = NOTE_RE.match(word)
    if m and m.group(1) in ws.sessions:
        return f"/note/{m.group(1)}"
    for rel in (word, f"critiques/{word}.md"):
        if "/" in rel and backend.file_path(rel):
            return f"/file/{rel}"
    if word in ("project.md", "conventions.md"):
        return "/project"
    if word == "draft.tex":
        return "/draft"
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


# Raw HTML in the workspace's files is shown as text: agents write them. Math goes to MathJax as \( \) and \[ \].
MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"]).use(dollarmath_plugin)
MD.core.ruler.push("link_ids", link_ids)
MD.add_render_rule("math_inline", lambda self, tokens, idx, options, env:
                   f'<span class="math">\\({escape(tokens[idx].content)}\\)</span>')
MD.add_render_rule("math_block", lambda self, tokens, idx, options, env:
                   f'<div class="math block">\\[{escape(tokens[idx].content)}\\]</div>\n')
MD.add_render_rule("math_block_label", lambda self, tokens, idx, options, env:
                   f'<div class="math block">\\[{escape(tokens[idx].content)}\\]</div>\n')


def md(text) -> Markup:
    """Markdown as HTML, without the HTML comments that the templates use for instructions."""
    return Markup(MD.render(re.sub(r"<!--.*?-->", "", str(text or ""), flags=re.S)))


def md_inline(text) -> Markup:
    return Markup(MD.renderInline(" ".join(str(text or "").split())))


# ----- the app -----

backend = Backend.from_env()
# How long each load and write takes, in the Space's logs: where a save spends its few seconds.
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def fresh(request: Request) -> None:
    """Load the workspace again when a page is viewed more than two minutes after the last load."""
    if request.method == "GET" and not request.url.path.startswith(("/oauth/", "/whoami")):
        backend.refresh_if_stale()


app = FastAPI(title="PhysicsHive", docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(fresh)])
if backend.local:
    app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))
else:
    attach_huggingface_oauth(app)  # adds the session, and the sign-in and sign-out pages
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters.update(md=md, md_inline=md_inline, latex_doc=lambda rendered: Markup(latex.document_html(rendered)))
LATEX_CSS = (HERE / "latex.css").read_text(encoding="utf-8") if (HERE / "latex.css").is_file() else ""


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
    here = quote(request.url.path)
    context.update(request=request, user=signed_in(request), local=backend.local, name=backend.project_name(),
                   status=backend.status_line(), csrf=csrf_token(request), awaiting=backend.awaiting_count(),
                   flash=request.session.pop("flash", None), here=request.url.path, latex_css=LATEX_CSS,
                   sign_in=f"/oauth/huggingface/login?_target_url={here}",
                   sign_out=f"/oauth/huggingface/logout?_target_url={here}")
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def done(request: Request, message: str, url: str) -> RedirectResponse:
    request.session["flash"] = message
    return RedirectResponse(url, status_code=303)


@app.exception_handler(SpaceError)
def show_problem(request: Request, exc: SpaceError) -> HTMLResponse:
    return page(request, "problem.html", status_code=503 if backend.snap is None else 404, problem=str(exc))


# ----- the five pages -----


def latest_page(request: Request, **extra) -> HTMLResponse:
    return page(request, "latest.html", debriefs=backend.debriefs(), running=backend.running(), **extra)


@app.get("/", response_class=HTMLResponse)
def latest(request: Request):
    return latest_page(request)


@app.get("/project", response_class=HTMLResponse)
def project(request: Request):
    return page(request, "project.html", **backend.project())


@app.get("/draft", response_class=HTMLResponse)
def draft(request: Request):
    return page(request, "draft.html", **backend.draft())


@app.get("/draft/edit", response_class=HTMLResponse)
def draft_edit(request: Request):
    data = backend.draft()
    return page(request, "draft_edit.html", text=data["tex"], base=data["tex"], html=data["html"])


@app.get("/draft.pdf")
def draft_pdf(request: Request):
    data, name = backend.pdf("draft.tex")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.post("/preview", response_class=HTMLResponse)
def preview(request: Request, text: str = Form(""), csrf: str = Form("")):
    check_form(request, csrf)
    rendered = backend.render_tex(text, flags=True)
    return templates.TemplateResponse(request, "latex_body.html", {"html": rendered, "request": request})


@app.get("/sessions", response_class=HTMLResponse)
def sessions(request: Request):
    return page(request, "sessions.html", sessions=backend.sessions(), running=backend.running())


@app.get("/note/{session_id}", response_class=HTMLResponse)
def note(request: Request, session_id: str, source: int = 0):
    return page(request, "note.html", source=bool(source), **backend.note(session_id))


@app.get("/note/{session_id}/pdf")
def note_pdf(request: Request, session_id: str):
    data, name = backend.pdf(f"sessions/{session_id}/note.tex")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.get("/literature", response_class=HTMLResponse)
def literature(request: Request):
    return page(request, "literature.html", **backend.literature())


# ----- the session record -----


@app.get("/card/{card_id}", response_class=HTMLResponse)
def card(request: Request, card_id: str):
    return page(request, "card.html", **backend.card(card_id))


@app.get("/paper/{paper_id}", response_class=HTMLResponse)
def paper(request: Request, paper_id: str):
    return page(request, "paper.html", **backend.paper(paper_id))


@app.get("/session/{session_id}", response_class=HTMLResponse)
def session(request: Request, session_id: str):
    return page(request, "session.html", **backend.session(session_id))


@app.get("/file/{rel:path}", response_class=HTMLResponse)
def file(request: Request, rel: str):
    return page(request, "file.html", **backend.file(rel))


def local_path(url: str) -> str:
    """A path on this Space, never another site."""
    return url if url.startswith("/") and not url.startswith("//") else "/"


@app.get("/refresh")
def refresh(request: Request, back: str = "/"):
    backend.refresh()
    return RedirectResponse(local_path(back), status_code=303)


# ----- sign-in from the Hub's page -----
# On huggingface.co the Space is shown in a frame; sign-in opens a new tab (base.html). The Hub's sign-in page
# cuts the link between the two tabs, so the new tab lands on /signed-in, and the first tab asks /whoami until
# the sign-in shows, then reloads.


@app.get("/whoami")
def whoami(request: Request):
    return {"user": signed_in(request)}


@app.get("/signed-in", response_class=HTMLResponse)
def signed_in_page(request: Request, back: str = "/"):
    return page(request, "signed_in.html", back=local_path(back))


# ----- writes -----


def back_of(rel: str) -> str:
    if rel in ("project.md", "conventions.md"):
        return "/project"
    if rel == "literature/seeds.md":
        return "/literature"
    if rel == "draft.tex":
        return "/draft"
    m = re.match(r"^sessions/(S\d+)/debrief\.md$", rel)
    return f"/#{m.group(1)}" if m else "/"


@app.get("/edit/{rel:path}", response_class=HTMLResponse)
def edit(request: Request, rel: str):
    if not backend.editable(rel):
        raise SpaceError(f"{rel} is not one of the files you edit here.")
    if rel == "draft.tex":
        return RedirectResponse("/draft/edit", status_code=303)
    text = backend.read(rel)
    return page(request, "edit.html", path=rel, text=text, base=text, back=back_of(rel))


@app.post("/edit/{rel:path}")
def save(request: Request, rel: str, text: str = Form(""), base: str = Form(""), csrf: str = Form("")):
    try:
        message = backend.save_file(check_form(request, csrf), rel, text, base)
    except SpaceError as exc:
        if rel == "draft.tex":
            return page(request, "draft_edit.html", text=text, base=base, html=backend.render_tex(text, flags=True),
                        error=str(exc))
        return page(request, "edit.html", path=rel, text=text, base=base, back=back_of(rel), error=str(exc))
    return done(request, message, back_of(rel))


@app.post("/debrief/{session_id}")
async def answer(request: Request, session_id: str):
    form = await request.form()
    answers = {int(k.split("-", 1)[1]): str(v) for k, v in form.items() if re.match(r"^answer-\d+$", k)}
    ticked = {int(k.split("-", 1)[1]) for k in form.keys() if re.match(r"^tick-\d+$", k)}
    try:
        message = backend.save_debrief(check_form(request, str(form.get("csrf", ""))), session_id, answers, ticked,
                                       str(form.get("note", "")), str(form.get("base", "")))
    except SpaceError as exc:
        return latest_page(request, error=str(exc), error_for=session_id)
    return done(request, message, f"/#{session_id}")


@app.post("/rate")
def rate(request: Request, paper_id: str = Form(""), rating: str = Form(""), back: str = Form("/literature"),
         csrf: str = Form("")):
    message = backend.rate(check_form(request, csrf), paper_id, rating)
    return done(request, message, local_path(back) if back else "/literature")
