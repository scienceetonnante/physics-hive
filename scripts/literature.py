# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.12,<2", "pyyaml>=6"]
# ///
"""Literature tools: search INSPIRE and arXiv, follow citations, download sources.

Usage, from the workspace root:
  uv run .physics-hive/scripts/literature.py search-inspire "<query>"
  uv run .physics-hive/scripts/literature.py search-arxiv "<query>"
  uv run .physics-hive/scripts/literature.py references <paper>
  uv run .physics-hive/scripts/literature.py citations <paper>
  uv run .physics-hive/scripts/literature.py download <arXiv id>
  uv run .physics-hive/scripts/literature.py card <paper>
  uv run .physics-hive/scripts/literature.py search-cards "<query>"
  uv run .physics-hive/scripts/literature.py mcp

A paper is an arXiv identifier (2301.01234, 2301.01234v2, hep-th/9711200,
arXiv:2301.01234, a paper-card ID such as P-hep-th_9711200) or an INSPIRE
record number written insp:451647. Every command takes --json for structured
output. `mcp` runs the other commands as the tools of an MCP server over stdio.

Sources: INSPIRE-HEP for high-energy physics and gravitation, the arXiv API,
and Semantic Scholar for papers that INSPIRE does not cover as core records.
arXiv requests are spaced by at least 3 seconds, also across runs of this
script. Set SEMANTIC_SCHOLAR_API_KEY to raise the Semantic Scholar rate limit.
"""

from __future__ import annotations

import argparse
import gzip
import http.client
import io
import json
import os
import re
import shutil
import ssl
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cards import PAPER_ID_RE, FrontMatterError, find_root, split_front_matter  # noqa: E402

_VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.is_file() else "dev"
USER_AGENT = f"PhysicsHive/{VERSION} literature.py (+https://github.com/huggingface/physics-hive-claude-plugin)"

INSPIRE_API = "https://inspirehep.net/api/literature"
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_EPRINT = "https://arxiv.org/e-print/"
ARXIV_PDF = "https://arxiv.org/pdf/"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/"

TIMEOUT = 30  # seconds per HTTP request
ARXIV_HOSTS = {"export.arxiv.org", "arxiv.org"}
ARXIV_DELAY = 3.0  # arXiv asks for no more than one request every 3 seconds
ARXIV_STAMP = Path(tempfile.gettempdir()) / "physics-hive-arxiv-last-request"
MAX_BYTES = 200 * 1024 * 1024  # cap on a download and on an unpacked source archive
MAX_LIMIT = 250

# Fields asked from INSPIRE for lists of papers. `first_author` and
# `author_count` keep the answers small: collaboration papers have thousands
# of authors.
INSPIRE_LIST_FIELDS = ("control_number,titles,first_author,author_count,collaborations,"
                       "arxiv_eprints,citation_count,earliest_date,dois,core")
INSPIRE_CARD_FIELDS = INSPIRE_LIST_FIELDS + ",authors.full_name"
S2_FIELDS = "title,authors,year,citationCount,externalIds"

SortInspire = Literal["mostcited", "mostrecent"]
SortArxiv = Literal["relevance", "recent"]
Source = Literal["auto", "inspire", "semantic-scholar"]


class LiteratureError(Exception):
    """A failure reported to the caller as one line."""


class HTTPStatusError(LiteratureError):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


# ----- paper identifiers -----

NEW_ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
OLD_ARXIV_RE = re.compile(r"^([a-z][a-z-]*(?:\.[A-Za-z]{2})?)[/_](\d{7})(v\d+)?$")
INSPIRE_REF_RE = re.compile(r"^(?:insp|inspire)[:_-]?(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class PaperRef:
    """A paper named by its arXiv identifier (without version) or its INSPIRE record."""

    arxiv: str | None = None
    version: str = ""  # "v2", or "" for the latest version
    inspire: int | None = None

    @property
    def label(self) -> str:
        return f"arXiv:{self.arxiv}" if self.arxiv else f"INSPIRE record {self.inspire}"


def parse_paper_id(text: str) -> PaperRef:
    """Read an arXiv identifier, an `insp:<record>` reference or a paper-card ID."""
    s = text.strip()
    s = re.sub(r"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|e-print|src)/", "", s)
    s = re.sub(r"\.pdf$", "", s)
    s = re.sub(r"^arxiv:", "", s, flags=re.IGNORECASE)
    s = s.removeprefix("P-")
    if m := INSPIRE_REF_RE.match(s):
        return PaperRef(inspire=int(m.group(1)))
    if m := NEW_ARXIV_RE.match(s):
        return PaperRef(arxiv=m.group(1), version=m.group(2) or "")
    if m := OLD_ARXIV_RE.match(s):
        return PaperRef(arxiv=f"{m.group(1)}/{m.group(2)}", version=m.group(3) or "")
    raise LiteratureError(
        f"not a paper identifier: {text!r} (expected an arXiv ID such as 2301.01234 or hep-th/9711200, "
        "or insp:<INSPIRE record number>)"
    )


def card_id(arxiv: str | None, inspire: int | None = None) -> str:
    """Paper-card ID: P-<arXiv id> with `/` replaced by `_`, or P-insp-<record>."""
    if arxiv:
        return "P-" + arxiv.replace("/", "_")
    if inspire:
        return f"P-insp-{inspire}"
    raise LiteratureError("a paper card needs an arXiv ID or an INSPIRE record number")


def source_folder(arxiv: str) -> str:
    """Name of the folder under literature/sources/ for an arXiv paper."""
    return arxiv.replace("/", "_")


# ----- papers -----


@dataclass
class Paper:
    title: str = ""
    arxiv: str | None = None
    inspire: int | None = None
    authors: list[str] = field(default_factory=list)  # "First Last"; for INSPIRE lists, only the first author
    author_count: int | None = None
    collaboration: str | None = None
    year: int | None = None
    citations: int | None = None
    doi: str | None = None
    abstract: str | None = None
    inspire_core: bool | None = None  # INSPIRE curates core (HEP) records fully, references included


def one_line(text: str | None) -> str:
    return " ".join(str(text or "").split())


def shorten(text: str, limit: int) -> str:
    text = one_line(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def first_last(name: str) -> str:
    """Turn INSPIRE's 'Maldacena, Juan Martin' into 'Juan Martin Maldacena'."""
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    return name.strip()


def surname(name: str) -> str:
    """Family name, keeping lowercase particles: 'Jan de Boer' gives 'de Boer'."""
    if "," in name:
        return name.split(",", 1)[0].strip()
    words = name.split()
    if not words:
        return ""
    i = len(words) - 1
    while i > 0 and words[i - 1][:1].islower():
        i -= 1
    return " ".join(words[i:])


def paper_from_inspire(meta: dict) -> Paper:
    def first(key: str, sub: str = "value"):
        items = meta.get(key) or []
        return items[0].get(sub) if items else None

    if meta.get("authors"):
        authors = [first_last(a.get("full_name", "")) for a in meta["authors"]]
    elif meta.get("first_author"):
        authors = [first_last(meta["first_author"].get("full_name", ""))]
    else:
        authors = []
    date = str(meta.get("earliest_date") or "")
    return Paper(
        title=one_line(first("titles", "title")),
        arxiv=first("arxiv_eprints"),
        inspire=meta.get("control_number"),
        authors=authors,
        author_count=meta.get("author_count") or len(authors) or None,
        collaboration=first("collaborations"),
        year=int(date[:4]) if date[:4].isdigit() else None,
        citations=meta.get("citation_count"),
        doi=first("dois"),
        inspire_core=meta.get("core"),
    )


def paper_from_s2(item: dict) -> Paper:
    ids = item.get("externalIds") or {}
    authors = [a.get("name", "") for a in item.get("authors") or []]
    return Paper(
        title=one_line(item.get("title")),
        arxiv=ids.get("ArXiv"),
        authors=authors,
        author_count=len(authors) or None,
        year=item.get("year"),
        citations=item.get("citationCount"),
        doi=ids.get("DOI"),
    )


ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom",
        "os": "http://a9.com/-/spec/opensearch/1.1/"}


def parse_arxiv_feed(xml_text: bytes | str) -> tuple[int, list[Paper]]:
    """Total number of results and the papers of an arXiv API Atom feed."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise LiteratureError(f"arXiv sent an answer that is not valid XML ({exc})") from None
    papers = []
    for entry in root.findall("a:entry", ATOM):
        entry_id = entry.findtext("a:id", "", ATOM)
        if "/api/errors" in entry_id:
            raise LiteratureError(f"arXiv rejected the query: {one_line(entry.findtext('a:summary', '', ATOM))}")
        match = re.search(r"arxiv\.org/abs/(.+?)(v\d+)?$", entry_id)
        if not match:
            continue
        published = entry.findtext("a:published", "", ATOM)
        authors = [one_line(a.findtext("a:name", "", ATOM)) for a in entry.findall("a:author", ATOM)]
        papers.append(Paper(
            title=one_line(entry.findtext("a:title", "", ATOM)),
            arxiv=match.group(1),
            authors=authors,
            author_count=len(authors) or None,
            year=int(published[:4]) if published[:4].isdigit() else None,
            doi=entry.findtext("arxiv:doi", None, ATOM),
            abstract=one_line(entry.findtext("a:summary", "", ATOM)) or None,
        ))
    total_text = root.findtext("os:totalResults", "", ATOM)
    total = int(total_text) if total_text.isdigit() else len(papers)
    return total, papers


# ----- HTTP -----


class _KeepAliveHTTPSConnection(http.client.HTTPSConnection):
    """urllib always sends `Connection: close`; Semantic Scholar drops some such requests unanswered."""

    def putheader(self, header, *values):
        if header.lower() == "connection":
            values = ("keep-alive",)
        super().putheader(header, *values)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_KeepAliveHTTPSConnection, req, context=self._context)


_OPENER = urllib.request.build_opener(_HTTPSHandler())  # keeps the default proxy and redirect handling


def _wait_for_arxiv() -> None:
    """Space arXiv requests by ARXIV_DELAY seconds, using a time stamp file shared by all runs."""
    try:
        last = ARXIV_STAMP.stat().st_mtime
    except OSError:
        last = 0.0
    wait = last + ARXIV_DELAY - time.time()
    if wait > 0:
        time.sleep(min(wait, ARXIV_DELAY))
    try:
        ARXIV_STAMP.touch()
    except OSError:
        pass


def http_get(url: str, params: dict | None = None, *, accept: str | None = None, retries: int = 2) -> bytes:
    """GET a URL and return the body. Retries on rate limits and server errors."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    host = urllib.parse.urlparse(url).hostname or url
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    if host == "api.semanticscholar.org" and os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
        headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
    for attempt in range(retries + 1):
        if host in ARXIV_HOSTS:
            _wait_for_arxiv()
        try:
            with _OPENER.open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as resp:
                body = resp.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                retry_after = exc.headers.get("Retry-After", "")
                time.sleep(min(int(retry_after), 30) if retry_after.isdigit() else 5 * (attempt + 1))
                continue
            hint = ""
            if exc.code == 429:
                hint = " (rate limited; wait a minute and retry"
                hint += ", or set SEMANTIC_SCHOLAR_API_KEY)" if host == "api.semanticscholar.org" else ")"
            raise HTTPStatusError(f"{host} answered HTTP {exc.code} {exc.reason}{hint}", exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise LiteratureError(
                    f"could not verify the certificate of {host} ({reason.verify_message}); "
                    "set SSL_CERT_FILE to a CA bundle"
                ) from None
            raise LiteratureError(f"could not reach {host}: {reason}") from None
        if len(body) > MAX_BYTES:
            raise LiteratureError(f"the answer from {host} is larger than {MAX_BYTES // 2**20} MB")
        return body
    raise LiteratureError(f"{host} kept failing")  # not reached


def get_json(url: str, params: dict | None = None) -> dict:
    body = http_get(url, params, accept="application/json")
    try:
        return json.loads(body)
    except ValueError:
        host = urllib.parse.urlparse(url).hostname
        raise LiteratureError(f"{host} sent an answer that is not JSON") from None


# ----- INSPIRE, arXiv and Semantic Scholar -----


def inspire_search(query: str, limit: int, sort: str, fields: str = INSPIRE_LIST_FIELDS) -> tuple[int, list[Paper]]:
    data = get_json(INSPIRE_API, {"q": query, "size": clamp(limit), "sort": sort, "fields": fields})
    hits = data.get("hits") or {}
    total = hits.get("total") or 0
    if isinstance(total, dict):  # some Elasticsearch versions report {"value": n}
        total = total.get("value", 0)
    return int(total), [paper_from_inspire(h.get("metadata") or {}) for h in hits.get("hits") or []]


def inspire_lookup(ref: PaperRef, fields: str = INSPIRE_LIST_FIELDS) -> Paper | None:
    """The INSPIRE record of a paper, or None if INSPIRE does not know it."""
    query = f"arxiv:{ref.arxiv}" if ref.arxiv else f"recid:{ref.inspire}"
    _total, papers = inspire_search(query, 1, "mostrecent", fields)
    return papers[0] if papers else None


def arxiv_lookup(ref: PaperRef) -> Paper | None:
    _total, papers = parse_arxiv_feed(http_get(ARXIV_API, {"id_list": ref.arxiv + ref.version, "max_results": 1}))
    return papers[0] if papers else None


ARXIV_FIELD_RE = re.compile(r"\b(?:ti|au|abs|co|jr|cat|rn|id|all):|\b(?:AND|OR|ANDNOT)\b")


def arxiv_search_query(text: str) -> str:
    """Pass arXiv query syntax through; turn free text into `all:` terms joined by AND."""
    if ARXIV_FIELD_RE.search(text):
        return text
    terms = re.findall(r'"[^"]+"|\S+', text)
    return " AND ".join(f"all:{term}" for term in terms)


def s2_links(arxiv: str, direction: str) -> tuple[list[Paper], str, bool]:
    """References or citations from Semantic Scholar, the paper's title if given, and
    whether the list was cut (Semantic Scholar sends at most 1000, newest first)."""
    try:
        data = get_json(f"{S2_API}arXiv:{arxiv}/{direction}", {"fields": S2_FIELDS, "limit": 1000})
    except HTTPStatusError as exc:
        if exc.code == 404:
            raise LiteratureError(f"Semantic Scholar has no record of arXiv:{arxiv}") from None
        raise
    key = "citedPaper" if direction == "references" else "citingPaper"
    papers = [paper_from_s2(item[key]) for item in data.get("data") or [] if (item.get(key) or {}).get("title")]
    title = one_line(((data.get("citingPaperInfo") or data.get("citedPaperInfo") or {}).get("title")))
    return papers, title, data.get("next") is not None


def clamp(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


# ----- commands -----


def cmd_search_inspire(query: str, limit: int = 10, sort: SortInspire = "mostcited") -> dict:
    total, papers = inspire_search(query, limit, sort)
    return {"command": "search-inspire", "source": "INSPIRE", "query": query, "sort": sort, "total": total,
            "results": [asdict(p) for p in papers]}


def cmd_search_arxiv(query: str, limit: int = 10, sort: SortArxiv = "relevance") -> dict:
    params = {"search_query": arxiv_search_query(query), "start": 0, "max_results": clamp(limit),
              "sortBy": "relevance" if sort == "relevance" else "submittedDate", "sortOrder": "descending"}
    total, papers = parse_arxiv_feed(http_get(ARXIV_API, params))
    return {"command": "search-arxiv", "source": "arXiv", "query": query, "sort": sort, "total": total,
            "results": [asdict(p) for p in papers]}


def cmd_links(direction: str, paper: str, limit: int = 25, sort: SortInspire = "mostcited",
              source: Source = "auto") -> dict:
    """References (direction 'references') or citing papers ('citations') of a paper.

    INSPIRE curates the references and citations of its core records (high-energy
    physics and gravitation). Other papers, including the non-core records INSPIRE
    keeps because HEP papers cite them, go to Semantic Scholar.
    """
    ref = parse_paper_id(paper)
    target = None if source == "semantic-scholar" else inspire_lookup(ref)
    if source == "inspire" and target is None:
        raise LiteratureError(f"INSPIRE has no record of {ref.label}")
    from_inspire = None
    if target is not None and (source == "inspire" or target.inspire_core):
        from_inspire = inspire_links(direction, target, limit, sort)
        if from_inspire["total"] or source == "inspire" or not target.arxiv:
            return from_inspire

    arxiv = ref.arxiv or (target.arxiv if target else None)
    if not arxiv:
        raise LiteratureError(f"Semantic Scholar needs an arXiv ID, and {ref.label} has none")
    try:
        papers, title, cut = s2_links(arxiv, direction)
    except LiteratureError as exc:
        if target is None or source == "semantic-scholar":
            raise
        result = from_inspire or inspire_links(direction, target, limit, sort)
        result["note"] = f"Semantic Scholar failed ({exc}); INSPIRE may list only part of them"
        return result
    papers.sort(key=lambda p: (p.citations or 0) if sort == "mostcited" else (p.year or 0), reverse=True)
    note = f"Semantic Scholar sent only its newest {len(papers)}; older ones are missing" if cut else ""
    return {"command": direction, "paper": asdict(target) if target else {"arxiv": arxiv, "title": title},
            "source": "Semantic Scholar", "sort": sort, "total": len(papers), "note": note,
            "results": [asdict(p) for p in papers[: clamp(limit)]]}


def inspire_links(direction: str, target: Paper, limit: int, sort: str) -> dict:
    query = ("citedby" if direction == "references" else "refersto") + f":recid:{target.inspire}"
    total, papers = inspire_search(query, limit, sort)
    note = "" if target.inspire_core else "INSPIRE covers this paper only partly (not a core record)"
    return {"command": direction, "paper": asdict(target), "source": "INSPIRE", "sort": sort, "total": total,
            "note": note, "results": [asdict(p) for p in papers]}


def cmd_card(paper: str, session: str | None = None) -> dict:
    """A paper-card skeleton with the bibliographic header filled in."""
    ref = parse_paper_id(paper)
    found = inspire_lookup(ref, INSPIRE_CARD_FIELDS)
    if found is None and ref.arxiv:
        found = arxiv_lookup(ref)
    if found is None:
        raise LiteratureError(f"neither INSPIRE nor arXiv knows {ref.label}")
    if ref.arxiv and not found.arxiv:
        found.arxiv = ref.arxiv
    session = session or active_session()
    text = render_card(found, session)
    paper_id = card_id(found.arxiv, found.inspire)
    return {"command": "card", "id": paper_id, "path": f"literature/{paper_id}.md", "paper": asdict(found),
            "text": text}


def cmd_download(paper: str, force: bool = False) -> dict:
    """Fetch the LaTeX source (or else the PDF) into literature/sources/<id>/."""
    ref = parse_paper_id(paper)
    if not ref.arxiv:
        raise LiteratureError("download needs an arXiv ID; papers outside arXiv must be fetched by hand")
    root = workspace_root()
    dest = root / "literature" / "sources" / source_folder(ref.arxiv)
    if dest.is_dir() and any(dest.iterdir()) and not force:
        return describe_folder(root, dest, ref, "already downloaded")

    # Unpack into a side folder first, so that a failed download leaves nothing half-written.
    partial = dest.with_name(dest.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    kind, skipped = None, []
    try:
        try:
            body = http_get(ARXIV_EPRINT + ref.arxiv + ref.version)
            kind, skipped = unpack_eprint(body, partial, source_folder(ref.arxiv))
        except HTTPStatusError as exc:
            if exc.code not in (403, 404):
                raise
        if kind is None:  # no usable source: fall back to the PDF
            shutil.rmtree(partial)
            partial.mkdir()
            try:
                pdf = http_get(ARXIV_PDF + ref.arxiv + ref.version)
            except HTTPStatusError as exc:
                if exc.code == 404:
                    raise LiteratureError(f"arXiv has no paper {ref.arxiv}{ref.version}") from None
                raise
            if not pdf.startswith(b"%PDF"):
                raise LiteratureError(f"arXiv has neither a LaTeX source nor a PDF for {ref.label}")
            (partial / f"{source_folder(ref.arxiv)}.pdf").write_bytes(pdf)
        shutil.rmtree(dest, ignore_errors=True)
        partial.rename(dest)
    finally:
        shutil.rmtree(partial, ignore_errors=True)
    result = describe_folder(root, dest, ref, "downloaded")
    result["skipped"] = skipped
    return result


def cmd_search_cards(query: str, limit: int = 10) -> dict:
    """Keyword search over paper cards, the literature overview and cards in claims/."""
    root = workspace_root()
    return {"command": "search-cards", "query": query, **search_cards(root, query, clamp(limit))}


# ----- paper cards -----

CARD_SECTIONS = ("Question", "Method", "Main result", "Assumptions", "Conventions", "Relevance")


def yaml_quote(text: str) -> str:
    """A YAML single-quoted scalar (LaTeX backslashes survive; ' is doubled)."""
    return "'" + one_line(text).replace("'", "''") + "'"


def card_authors(paper: Paper) -> list[str]:
    """Authors for the card header: all of them up to five, else the first three and 'et al.'."""
    count = paper.author_count or len(paper.authors)
    if paper.collaboration and count > 10:
        return [f"{paper.collaboration} Collaboration"]
    if count > 5:
        return paper.authors[:3] + ["et al."]
    return paper.authors


def render_card(paper: Paper, session: str | None = None) -> str:
    paper_id = card_id(paper.arxiv, paper.inspire)
    if not PAPER_ID_RE.match(paper_id):
        raise LiteratureError(f"cannot build a valid paper-card ID from {paper_id!r}")
    lines = [
        "---",
        f"id: {paper_id}",
        "kind: paper",
        f"title: {yaml_quote(paper.title)}",
        "authors: [" + ", ".join(yaml_quote(a) for a in card_authors(paper)) + "]",
        f"year: {paper.year if paper.year else 'null'}",
        f"arxiv: {yaml_quote(paper.arxiv) if paper.arxiv else 'null'}",
        f"inspire: {paper.inspire if paper.inspire else 'null'}",
        f"doi: {yaml_quote(paper.doi) if paper.doi else 'null'}",
        "why: ''",
        "topic: ''",
        "rating: ''",
        f"session: {session or 'S<n>'}",
        "---",
    ]
    for heading in CARD_SECTIONS:
        lines += [f"## {heading}", ""]
    return "\n".join(lines)


def workspace_root() -> Path:
    try:
        return find_root()
    except SystemExit as exc:  # find_root exits; an MCP tool must raise instead
        raise LiteratureError(str(exc)) from None


def active_session() -> str | None:
    """ID of the session open in this checkout (from .active-session), if any."""
    try:
        info = json.loads((find_root() / ".active-session").read_text(encoding="utf-8"))
        return str(info["id"])
    except (SystemExit, OSError, ValueError, KeyError, TypeError):
        return None


# ----- source archives -----


def gzip_member_name(data: bytes) -> str | None:
    """The original file name stored in a gzip header, if any."""
    if len(data) < 10 or data[:2] != b"\x1f\x8b":
        return None
    flags, pos = data[3], 10
    if flags & 0x04:  # FEXTRA
        pos += 2 + int.from_bytes(data[10:12], "little")
    if not flags & 0x08:  # no FNAME
        return None
    end = data.find(b"\0", pos)
    return data[pos:end].decode("latin-1") if end > pos else None


def safe_file_name(name: str | None) -> str | None:
    """A plain file name (no folders, no hidden or odd characters), or None."""
    base = PurePosixPath((name or "").replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._+-]", "_", base).lstrip(".")
    return base or None


def gunzip(data: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        out = f.read(MAX_BYTES + 1)
    if len(out) > MAX_BYTES:
        raise LiteratureError(f"the source archive unpacks to more than {MAX_BYTES // 2**20} MB")
    return out


def safe_extract_tar(data: bytes, dest: Path) -> tuple[list[str], list[str]]:
    """Extract regular files and folders of a tar archive inside `dest`.

    Links, devices, absolute paths and paths that climb out of `dest` with `..`
    are skipped. Returns the files written and the members skipped.
    """
    dest = dest.resolve()
    written, skipped, total = [], [], 0
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            name = member.name.replace("\\", "/")
            parts = PurePosixPath(name).parts
            bad_path = name.startswith("/") or ".." in parts or "\0" in name or not parts
            target = (dest / name).resolve()
            if bad_path or not target.is_relative_to(dest) or target == dest or not (member.isfile() or member.isdir()):
                skipped.append(member.name)
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            total += member.size
            if total > MAX_BYTES:
                raise LiteratureError(f"the source archive unpacks to more than {MAX_BYTES // 2**20} MB")
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            written.append(target.relative_to(dest).as_posix())
    return written, skipped


def is_tar(data: bytes) -> bool:
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            return tar.next() is not None
    except (tarfile.TarError, EOFError, OSError):
        return False


def unpack_eprint(data: bytes, folder: Path, stem: str) -> tuple[str | None, list[str]]:
    """Unpack what arXiv's e-print endpoint returned into `folder`.

    It is a gzipped tar archive, a single gzipped TeX file, or a PDF for papers
    submitted without source. Returns ("source" or "pdf" or None, members skipped).
    """
    name = gzip_member_name(data)
    if data[:2] == b"\x1f\x8b":
        data = gunzip(data)
    if data[:4] == b"%PDF":
        (folder / f"{stem}.pdf").write_bytes(data)
        return "pdf", []
    if data[:4] == b"%!PS" or data.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
        return None, []  # PostScript only, or an error page: no usable source
    if is_tar(data):
        written, skipped = safe_extract_tar(data, folder)
        return ("source" if written else None), skipped
    filename = safe_file_name(name) or f"{stem}.tex"
    if not filename.endswith((".tex", ".TEX", ".ltx")):
        filename = Path(filename).stem + ".tex"
    (folder / filename).write_bytes(data)
    return "source", []


def find_main_tex(folder: Path) -> Path | None:
    """The main TeX file: one with \\documentclass and \\begin{document}, near the top, largest first."""
    texs = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in (".tex", ".ltx")]
    if not texs:
        return None

    def score(path: Path) -> tuple:
        text = path.read_text(encoding="utf-8", errors="replace")
        return (bool(re.search(r"\\document(?:class|style)", text)), "\\begin{document}" in text,
                -len(path.relative_to(folder).parts), path.stem.lower() in ("main", "ms", "paper", "article"),
                path.stat().st_size)

    return max(texs, key=score)


def describe_folder(root: Path, folder: Path, ref: PaperRef, status: str) -> dict:
    files = sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: p.relative_to(folder).as_posix())
    pdfs = [p for p in files if p.suffix.lower() == ".pdf"]
    main = find_main_tex(folder)
    kind = "source" if main else ("pdf" if pdfs else "unknown")
    main = main or (pdfs[0] if pdfs else None)
    return {
        "command": "download",
        "paper": ref.label,
        "status": status,
        "kind": kind,
        "folder": folder.relative_to(root).as_posix() + "/",
        "main": main.relative_to(root).as_posix() if main else None,
        "files": [{"path": p.relative_to(folder).as_posix(), "bytes": p.stat().st_size} for p in files],
    }


# ----- local search over cards -----

STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on",
              "or", "that", "the", "to", "with"}


def search_cards(root: Path, query: str, limit: int = 10) -> dict:
    """Rank paper cards, the literature overview and claims/ cards by the query's words.

    A word counts where a word of the file starts with it ("gauge" finds
    "gauges"). Files matching more distinct words rank first; then words in the
    header (id, title, statement, authors) weigh three times words in the body.
    """
    terms = [t for t in dict.fromkeys(re.findall(r"\w+", query.lower())) if t not in STOP_WORDS and len(t) > 1]
    if not terms:
        raise LiteratureError("the query has no words to search for")
    patterns = [re.compile(r"\b" + re.escape(t), re.IGNORECASE) for t in terms]
    lit, claims = root / "literature", root / "claims"
    paths = sorted(lit.glob("P-*.md")) + sorted(lit.glob("overview.md")) + sorted(claims.glob("*.md"))
    hits = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            meta, body = split_front_matter(text)
        except FrontMatterError:
            meta, body = {}, text
        head = " ".join(one_line(meta.get(k)) for k in ("id", "title", "statement", "authors") if meta.get(k))
        matched, score = 0, 0
        for pattern in patterns:
            in_head, in_body = len(pattern.findall(head)), len(pattern.findall(body))
            if in_head or in_body:
                matched += 1
                score += 3 * min(in_head, 3) + min(in_body, 10)
        if not matched:
            continue
        overview = path.name == "overview.md"
        hits.append({
            "path": path.relative_to(root).as_posix(),
            "kind": str(meta.get("kind") or ("overview" if overview else "file")),
            "title": one_line(meta.get("title") or meta.get("statement") or
                              ("literature overview" if overview else first_heading(body) or path.stem)),
            "matched": matched,
            "score": score,
            "snippet": best_snippet(body, patterns),
        })
    hits.sort(key=lambda h: (-h["matched"], -h["score"], h["path"]))
    return {"terms": terms, "searched": len(paths), "total": len(hits), "results": hits[:limit]}


def first_heading(body: str) -> str:
    match = re.search(r"^#+\s+(.+)$", body, re.MULTILINE)
    return match.group(1) if match else ""


def best_snippet(body: str, patterns: list[re.Pattern], width: int = 200) -> str:
    """The body line with the most query words, cut to about `width` characters around the first match."""
    best, best_count = "", 0
    for line in body.splitlines():
        if line.startswith("#"):
            continue
        count = sum(1 for p in patterns if p.search(line))
        if count > best_count:
            best, best_count = line, count
    if not best:
        return ""
    best = one_line(best)
    starts = [m.start() for p in patterns if (m := p.search(best))]
    start = max(0, min(starts) - width // 4) if starts else 0
    snippet = best[start : start + width]
    return ("…" if start > 0 else "") + snippet + ("…" if start + width < len(best) else "")


# ----- text output -----


def author_text(p: dict) -> str:
    names = [surname(a) for a in p.get("authors") or [] if a]
    count = p.get("author_count") or len(names)
    if not names:
        text = "unknown authors"
    elif count <= 3 and len(names) == count:
        text = ", ".join(names)
    else:
        text = f"{names[0]} et al."
    return text + (f" [{p['collaboration']}]" if p.get("collaboration") else "")


def format_paper(i: int, p: dict, abstract: bool = False) -> str:
    parts = [p.get("arxiv") or "no arXiv ID"]
    if p.get("inspire"):
        parts.append(f"insp:{p['inspire']}")
    if p.get("year"):
        parts.append(str(p["year"]))
    if p.get("citations") is not None:
        parts.append(f"{p['citations']} citations")
    parts.append(author_text(p))
    lines = [f"{i:>2}. " + " | ".join(parts), "    " + (p.get("title") or "(no title)")]
    if abstract and p.get("abstract"):
        lines.append("    " + shorten(p["abstract"], 320))
    return "\n".join(lines)


def format_papers(data: dict) -> str:
    results = data["results"]
    order = {"mostcited": "most cited first", "mostrecent": "most recent first", "relevance": "best match first",
             "recent": "most recent first"}[data["sort"]]
    if data["command"] in ("search-inspire", "search-arxiv"):
        head = f'{data["source"]}: {data["total"]} results for "{data["query"]}"'
    else:
        target = data.get("paper") or {}
        label = f"arXiv:{target['arxiv']}" if target.get("arxiv") else f"insp:{target.get('inspire')}"
        title = f' ("{shorten(target["title"], 80)}")' if target.get("title") else ""
        what = "papers cited by" if data["command"] == "references" else "papers citing"
        head = f"{data['source']}: {data['total']} {what} {label}{title}"
    head += f"; showing {len(results)}, {order}." if results else "."
    if data.get("note"):
        head += f" Note: {data['note']}."
    body = [format_paper(i, p, abstract=data["command"] == "search-arxiv") for i, p in enumerate(results, 1)]
    return "\n".join([head, *body])


def format_download(data: dict) -> str:
    files = data["files"]
    what = {"source": "LaTeX source", "pdf": "PDF only (no LaTeX source on arXiv)"}.get(data["kind"], "files")
    count = f"{len(files)} file" + ("s" if len(files) != 1 else "")
    lines = [f"{data['paper']}: {data['status']}, {what}, in {data['folder']} ({count})"]
    if data.get("main"):
        lines.append(f"Main file: {data['main']}")
    for f in files[:40]:
        lines.append(f"  {f['path']}  ({max(1, round(f['bytes'] / 1024))} KB)")
    if len(files) > 40:
        lines.append(f"  … and {len(files) - 40} more")
    if data.get("skipped"):
        lines.append(f"Skipped {len(data['skipped'])} unsafe archive members (links or paths outside the folder).")
    return "\n".join(lines)


def card_hint(data: dict) -> str:
    hint = f"Save as {data['path']}"
    if "session: S<n>" in data["text"]:
        hint += " and replace S<n> by the session ID"
    return hint + "."


def format_search_cards(data: dict) -> str:
    results = data["results"]
    head = f'{data["total"]} of {data["searched"]} cards and the overview match "{data["query"]}"'
    lines = [head + (f"; showing {len(results)}." if results else ".")]
    for hit in results:
        lines.append(f"{hit['path']}  [{hit['kind']}] {shorten(hit['title'], 160)}")
        if hit["snippet"]:
            lines.append(f"    {hit['snippet']}")
    return "\n".join(lines)


# ----- MCP server -----


def serve_mcp() -> None:
    """Run the commands as MCP tools over stdio. Tools return the same text as the CLI."""
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    server = FastMCP("literature", instructions=(
        "Physics literature tools: search INSPIRE-HEP and arXiv, follow references and citations, "
        "download arXiv LaTeX sources into literature/sources/, draft paper cards, and search the "
        "workspace's own paper cards, literature overview and claim cards. Papers are named by arXiv ID "
        "(2301.01234, hep-th/9711200) or insp:<INSPIRE record number>."
    ), log_level="WARNING")
    reads_web = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

    @server.tool(annotations=reads_web)
    def search_inspire(query: str, limit: int = 10, sort: SortInspire = "mostcited") -> str:
        """Search INSPIRE-HEP (high-energy physics, gravitation, nuclear and astro). The query is free text or
        INSPIRE syntax, e.g. 't holographic entanglement and a Takayanagi'. Lists arXiv ID, INSPIRE record,
        year, citations, authors and title."""
        return format_papers(cmd_search_inspire(query, limit, sort))

    @server.tool(annotations=reads_web)
    def search_arxiv(query: str, limit: int = 10, sort: SortArxiv = "relevance") -> str:
        """Search arXiv. Free text, or arXiv syntax such as 'ti:anomaly AND cat:hep-th'. Lists arXiv ID,
        year, authors, title and the start of the abstract."""
        return format_papers(cmd_search_arxiv(query, limit, sort))

    @server.tool(annotations=reads_web)
    def references(paper: str, limit: int = 25, sort: SortInspire = "mostcited", source: Source = "auto") -> str:
        """Papers cited by a paper (arXiv ID or insp:<record>). Uses INSPIRE, or Semantic Scholar for papers
        INSPIRE does not cover."""
        return format_papers(cmd_links("references", paper, limit, sort, source))

    @server.tool(annotations=reads_web)
    def citations(paper: str, limit: int = 25, sort: SortInspire = "mostcited", source: Source = "auto") -> str:
        """Papers citing a paper (arXiv ID or insp:<record>). Uses INSPIRE, or Semantic Scholar for papers
        INSPIRE does not cover."""
        return format_papers(cmd_links("citations", paper, limit, sort, source))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                                             openWorldHint=True))
    def download(paper: str, force: bool = False) -> str:
        """Download an arXiv paper's LaTeX source (or its PDF when there is no source) into
        literature/sources/<id>/. Lists the files and the main .tex file. Skips papers already downloaded
        unless force is true."""
        return format_download(cmd_download(paper, force))

    @server.tool(annotations=reads_web)
    def card(paper: str, session: str | None = None) -> str:
        """Paper-card skeleton for literature/P-<id>.md, with title, authors, year, arXiv, INSPIRE and DOI
        filled in, and why, topic, rating and the sections to write. Pass the session ID (e.g. S12) to fill
        `session:`."""
        data = cmd_card(paper, session)
        return f"{card_hint(data)}\n\n{data['text']}"

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def search_cards(query: str, limit: int = 10) -> str:
        """Keyword search over this workspace's paper cards, literature overview and claim cards. Lists the
        best matches with their path and a snippet."""
        return format_search_cards(cmd_search_cards(query, limit))

    server.run("stdio")


# ----- command line -----


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("--json", action="store_true", help="print structured JSON instead of text")
        return p

    p = add("search-inspire", "search INSPIRE-HEP (free text or INSPIRE syntax)")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--sort", choices=["mostcited", "mostrecent"], default="mostcited")

    p = add("search-arxiv", "search arXiv (free text or arXiv syntax such as ti:, au:, cat:)")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--sort", choices=["relevance", "recent"], default="relevance")

    for name, what in (("references", "papers cited by a paper"), ("citations", "papers citing a paper")):
        p = add(name, f"{what} (INSPIRE first, Semantic Scholar for papers INSPIRE does not cover)")
        p.add_argument("paper", help="arXiv ID or insp:<INSPIRE record number>")
        p.add_argument("--limit", type=int, default=25, help=f"number of papers to show (at most {MAX_LIMIT})")
        p.add_argument("--sort", choices=["mostcited", "mostrecent"], default="mostcited")
        p.add_argument("--source", choices=["auto", "inspire", "semantic-scholar"], default="auto")

    p = add("download", "download the LaTeX source (or the PDF) into literature/sources/<id>/")
    p.add_argument("paper", help="arXiv ID")
    p.add_argument("--force", action="store_true", help="download again even if the folder exists")

    p = add("card", "print a paper-card skeleton with the bibliographic header filled in")
    p.add_argument("paper", help="arXiv ID or insp:<INSPIRE record number>")
    p.add_argument("--session", help="session ID for the header (default: the active session, if any)")

    p = add("search-cards", "keyword search over paper cards, the literature overview and claims/ cards")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)

    sub.add_parser("mcp", help="run the commands as an MCP server over stdio")
    return parser


def run(args: argparse.Namespace) -> tuple[dict, str]:
    """Run one command; return its data and its text form."""
    c = args.command
    if c == "search-inspire":
        data = cmd_search_inspire(args.query, args.limit, args.sort)
    elif c == "search-arxiv":
        data = cmd_search_arxiv(args.query, args.limit, args.sort)
    elif c in ("references", "citations"):
        data = cmd_links(c, args.paper, args.limit, args.sort, args.source)
    elif c == "download":
        return (data := cmd_download(args.paper, args.force)), format_download(data)
    elif c == "card":
        data = cmd_card(args.paper, args.session)
        print(card_hint(data), file=sys.stderr)  # stdout holds only the card, so `card … > file` works
        return data, data["text"]
    elif c == "search-cards":
        return (data := cmd_search_cards(args.query, args.limit)), format_search_cards(data)
    else:
        raise LiteratureError(f"unknown command {c!r}")
    return data, format_papers(data)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        serve_mcp()
        return 0
    try:
        data, text = run(args)
    except LiteratureError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # an unexpected answer from a service: one line, not a traceback
        print(f"ERROR: unexpected failure ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
