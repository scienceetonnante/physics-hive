"""Tests for scripts/literature.py that need no network.

API answers come from tests/fixtures/literature/ (real answers from INSPIRE,
arXiv and Semantic Scholar, trimmed). An autouse fixture makes any real HTTP
request fail, so a test that forgets to stub the network fails loudly.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import struct
import tarfile
import urllib.error
import zlib
from pathlib import Path

import pytest

import literature as lit
from cards import PAPER_ID_RE, split_front_matter

FIXTURES = Path(__file__).parent / "fixtures" / "literature"
SURVEYOR = Path(__file__).resolve().parents[1] / "commons" / "agents" / "surveyor.md"
REAL_HTTP_GET = lit.http_get  # kept before the fixture below replaces it, to test its retries


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to use the network")

    monkeypatch.setattr(lit, "http_get", refuse)


def inspire_fixture() -> dict:
    return json.loads((FIXTURES / "inspire_search.json").read_text())


# ----- identifiers -----


@pytest.mark.parametrize(
    "text, arxiv, version",
    [
        ("2301.01234", "2301.01234", ""),
        ("2301.01234v2", "2301.01234", "v2"),
        ("arXiv:2301.01234", "2301.01234", ""),
        ("0704.0001", "0704.0001", ""),
        ("hep-th/9711200", "hep-th/9711200", ""),
        ("hep-th/9711200v3", "hep-th/9711200", "v3"),
        ("hep-th_9711200", "hep-th/9711200", ""),
        ("P-hep-th_9711200", "hep-th/9711200", ""),
        ("P-1207.7214", "1207.7214", ""),
        ("math.AG/0101001", "math.AG/0101001", ""),
        ("cond-mat/0010317", "cond-mat/0010317", ""),
        ("https://arxiv.org/abs/1207.7214v2", "1207.7214", "v2"),
        ("https://arxiv.org/pdf/1706.03762.pdf", "1706.03762", ""),
        ("  1706.03762 ", "1706.03762", ""),
    ],
)
def test_arxiv_identifiers(text, arxiv, version):
    ref = lit.parse_paper_id(text)
    assert (ref.arxiv, ref.version, ref.inspire) == (arxiv, version, None)


@pytest.mark.parametrize("text", ["insp:451647", "inspire:451647", "P-insp-451647", "INSP:451647"])
def test_inspire_identifiers(text):
    ref = lit.parse_paper_id(text)
    assert (ref.arxiv, ref.inspire) == (None, 451647)


@pytest.mark.parametrize("text", ["", "foo", "1234.567", "hep-th/97112", "12345.6789", "insp:abc"])
def test_bad_identifiers(text):
    with pytest.raises(lit.LiteratureError, match="not a paper identifier"):
        lit.parse_paper_id(text)


def test_card_ids_and_folders():
    assert lit.card_id("hep-th/9711200") == "P-hep-th_9711200"
    assert lit.card_id("1207.7214") == "P-1207.7214"
    assert lit.card_id(None, 14236) == "P-insp-14236"
    assert lit.source_folder("hep-th/9711200") == "hep-th_9711200"
    for paper_id in ("P-hep-th_9711200", "P-1207.7214", "P-insp-14236", "P-math.AG_0101001"):
        assert PAPER_ID_RE.match(paper_id)


# ----- paper cards -----


def surveyor_template() -> tuple[list[str], list[str]]:
    """Header keys and section headings of the paper card in surveyor.md."""
    text = SURVEYOR.read_text()
    block = text.split("## Paper cards", 1)[1].split("```markdown", 1)[1].split("```", 1)[0]
    header = block.split("---")[1]
    keys = [line.split(":", 1)[0] for line in header.strip().splitlines()]
    sections = re.findall(r"^## (.+)$", block, re.MULTILINE)
    return keys, sections


def test_card_follows_the_surveyor_format():
    paper = lit.Paper(
        title="Wilson's loops and the $\\mathcal{N}=4$ theory: a review",
        arxiv="hep-th/9711200",
        inspire=451647,
        authors=["Juan Martin Maldacena", "Jan de Boer"],
        author_count=2,
        year=1997,
        doi="10.4310/ATMP.1998.v2.n2.a1",
    )
    text = lit.render_card(paper, "S3")
    meta, body = split_front_matter(text)
    keys, sections = surveyor_template()
    assert list(meta) == keys
    assert re.findall(r"^## (.+)$", body, re.MULTILINE) == sections
    assert body.replace("\n", "").replace("## ", "") == "".join(sections)  # sections are empty
    assert meta == {
        "id": "P-hep-th_9711200",
        "kind": "paper",
        "title": paper.title,  # apostrophe, colon and LaTeX survive the quoting
        "authors": ["Juan Martin Maldacena", "Jan de Boer"],
        "year": 1997,
        "arxiv": "hep-th/9711200",
        "inspire": 451647,
        "doi": "10.4310/ATMP.1998.v2.n2.a1",
        "why": "",  # written by the surveyor: one sentence for the lead
        "topic": "",
        "rating": "",
        "session": "S3",
    }


def test_card_without_session_arxiv_or_doi():
    paper = lit.Paper(title="Production of Very Massive Higgs Bosons", inspire=14236,
                      authors=["R.N. Cahn", "Sally Dawson"], author_count=2, year=1983)
    meta, _ = split_front_matter(lit.render_card(paper))
    assert meta["id"] == "P-insp-14236"
    assert meta["arxiv"] is None and meta["doi"] is None
    assert meta["session"] == "S<n>"


def test_card_authors_are_shortened():
    many = [f"Author {i}" for i in range(8)]
    assert lit.card_authors(lit.Paper(authors=many, author_count=8)) == many[:3] + ["et al."]
    assert lit.card_authors(lit.Paper(authors=many[:5], author_count=5)) == many[:5]
    atlas = lit.Paper(authors=many, author_count=2932, collaboration="ATLAS")
    assert lit.card_authors(atlas) == ["ATLAS Collaboration"]


def test_card_command_uses_inspire_then_the_active_session(tmp_path, monkeypatch):
    (tmp_path / "project.toml").write_text("[hub]\n")
    (tmp_path / ".active-session").write_text(json.dumps({"id": "S7"}))
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_get_json(url, params=None):
        seen.update(params)
        return inspire_fixture()

    monkeypatch.setattr(lit, "get_json", fake_get_json)
    data = lit.cmd_card("0710.1060")
    assert seen["q"] == "arxiv:0710.1060" and "authors.full_name" in seen["fields"]
    assert data["path"] == "literature/P-0710.1060.md"
    meta, _ = split_front_matter(data["text"])
    assert meta["inspire"] == 763100 and meta["session"] == "S7"
    assert data["source"] == "INSPIRE" and lit.card_hint(data) == "Save as literature/P-0710.1060.md."


# Semantic Scholar's answer for physics/0510206 (trimmed), a paper that INSPIRE does not hold.
S2_RECORD = {
    "paperId": "a59f7b7cc1fb22d7b17a2e426184161355908d86",
    "externalIds": {"ArXiv": "physics/0510206", "MAG": "2028714762", "DOI": "10.1119/1.2215616"},
    "title": "An accurate formula for the period of a simple pendulum oscillating beyond the small angle regime",
    "year": 2005,
    "journal": {"name": "American Journal of Physics", "pages": "892-895", "volume": "74"},
    "authors": [{"authorId": "94108149", "name": "F. M. Lima"}, {"authorId": "79010294", "name": "P. Arun"}],
    "abstract": "A simple approximate expression is derived for the dependence of the period of a simple pendulum "
                "on the amplitude.",
}


def fake_card_services(monkeypatch, arxiv_code: int, s2):
    """INSPIRE has no record; arXiv answers HTTP `arxiv_code`; Semantic Scholar answers `s2` (a record, or
    an exception to raise)."""
    calls = []

    def fake_get_json(url, params=None):
        calls.append(url)
        if "semanticscholar" in url:
            if isinstance(s2, Exception):
                raise s2
            return s2
        assert url == lit.INSPIRE_API
        return {"hits": {"total": 0, "hits": []}}

    def fake_http_get(url, params=None, **kwargs):
        calls.append(url)
        assert url == lit.ARXIV_API
        raise lit.HTTPStatusError(f"export.arxiv.org answered HTTP {arxiv_code}", arxiv_code)

    monkeypatch.setattr(lit, "get_json", fake_get_json)
    monkeypatch.setattr(lit, "http_get", fake_http_get)
    return calls


def test_card_falls_back_to_semantic_scholar_when_arxiv_rate_limits(monkeypatch, capsys):
    calls = fake_card_services(monkeypatch, 429, S2_RECORD)
    data = lit.cmd_card("physics/0510206", "S2")
    assert calls == [lit.INSPIRE_API, lit.ARXIV_API, f"{lit.S2_API}arXiv:physics/0510206"]
    assert data["source"] == "Semantic Scholar" and data["path"] == "literature/P-physics_0510206.md"
    meta, body = split_front_matter(data["text"])
    assert list(meta) == surveyor_template()[0]  # the card format is the usual one
    assert {k: meta[k] for k in ("id", "title", "authors", "year", "arxiv", "inspire", "doi", "session")} == {
        "id": "P-physics_0510206", "title": S2_RECORD["title"], "authors": ["F. M. Lima", "P. Arun"],
        "year": 2005, "arxiv": "physics/0510206", "inspire": None, "doi": "10.1119/1.2215616", "session": "S2"}
    assert data["paper"]["journal"] == "American Journal of Physics"
    assert data["paper"]["abstract"].startswith("A simple approximate expression")
    # The command line prints the card on stdout and, on stderr, where to save it and where the header came from.
    assert lit.main(["card", "physics/0510206", "--session", "S2"]) == 0
    out, err = capsys.readouterr()
    assert out == data["text"] + "\n"
    assert err == ("Save as literature/P-physics_0510206.md. "
                   "The header comes from Semantic Scholar: arXiv answered HTTP 429.\n")


def test_card_fallback_reports_what_failed(monkeypatch):
    # A preprint's journal, which Semantic Scholar gives as "ArXiv", is not a journal.
    fake_card_services(monkeypatch, 503, dict(S2_RECORD, journal={"name": "ArXiv", "volume": "abs/physics/0510206"}))
    assert lit.cmd_card("physics/0510206")["paper"]["journal"] is None
    # Semantic Scholar does not know the paper, or fails too: one error that says what each service answered.
    fake_card_services(monkeypatch, 429, lit.HTTPStatusError("api.semanticscholar.org answered HTTP 404", 404))
    with pytest.raises(lit.LiteratureError, match="INSPIRE and Semantic Scholar have no record of arXiv:physics/"
                                                  "0510206, and export.arxiv.org answered HTTP 429"):
        lit.cmd_card("physics/0510206")
    fake_card_services(monkeypatch, 429, lit.HTTPStatusError("api.semanticscholar.org answered HTTP 429", 429))
    with pytest.raises(lit.LiteratureError, match="Semantic Scholar failed too"):
        lit.cmd_card("physics/0510206")
    # Another error from arXiv (here a bad request) is reported as it is, without asking Semantic Scholar.
    calls = fake_card_services(monkeypatch, 400, S2_RECORD)
    with pytest.raises(lit.HTTPStatusError, match="HTTP 400"):
        lit.cmd_card("physics/0510206")
    assert calls == [lit.INSPIRE_API, lit.ARXIV_API]


def test_rate_limits_are_retried_after_the_pause_the_server_asks_for(monkeypatch):
    answers = [429, 503, 200]
    pauses = []

    class Opener:
        def open(self, request, timeout):
            code = answers.pop(0)
            if code != 200:
                headers = {"Retry-After": "7"} if code == 429 else {}
                raise urllib.error.HTTPError(request.full_url, code, "busy", headers, None)
            return io.BytesIO(b"{}")

    monkeypatch.setattr(lit, "_OPENER", Opener())
    monkeypatch.setattr(lit.time, "sleep", pauses.append)
    assert REAL_HTTP_GET(f"{lit.S2_API}arXiv:physics/0510206") == b"{}"
    assert pauses == [7, 10]  # as Retry-After asks, then the default pause of the second retry


# ----- parsing API answers -----


def test_parse_inspire_hits():
    papers = [lit.paper_from_inspire(h["metadata"]) for h in inspire_fixture()["hits"]["hits"]]
    first = papers[0]
    assert (first.arxiv, first.inspire, first.year) == ("0710.1060", 763100, 2007)
    assert first.authors == ["Luis F. Alday"] and first.author_count == 2
    assert first.title == "Comments on gluon scattering amplitudes via AdS/CFT"
    assert first.citations > 0 and first.inspire_core is True
    geant = papers[3]
    assert geant.arxiv is None and geant.collaboration == "GEANT4"
    assert lit.author_text(lit.asdict(geant)) == "Agostinelli et al. [GEANT4]"
    assert lit.author_text(lit.asdict(papers[1])) == "Maldacena"


def test_parse_arxiv_feed():
    total, papers = lit.parse_arxiv_feed((FIXTURES / "arxiv_feed.xml").read_bytes())
    assert total == 2
    maldacena, vaswani = papers
    assert (maldacena.arxiv, maldacena.year, maldacena.authors) == ("hep-th/9711200", 1997, ["Juan M. Maldacena"])
    assert maldacena.title == "The Large N Limit of Superconformal Field Theories and Supergravity"
    assert maldacena.doi == "10.1023/A:1026654312961"
    assert maldacena.abstract.startswith("We show that the large $N$ limit")
    assert vaswani.arxiv == "1706.03762" and vaswani.author_count == 8 and vaswani.doi is None
    assert lit.author_text(lit.asdict(vaswani)) == "Vaswani et al."


def test_arxiv_error_entry_is_reported():
    feed = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <id>http://arxiv.org/api/errors#incorrect_id_format_for_1234</id>
      <title>Error</title><summary>incorrect id format for 1234</summary></entry></feed>"""
    with pytest.raises(lit.LiteratureError, match="incorrect id format"):
        lit.parse_arxiv_feed(feed)


def test_arxiv_query_building():
    assert lit.arxiv_search_query('large N "Wilson loop"') == 'all:large AND all:N AND all:"Wilson loop"'
    assert lit.arxiv_search_query("ti:anomaly AND cat:hep-th") == "ti:anomaly AND cat:hep-th"


def test_names():
    assert lit.first_last("Maldacena, Juan Martin") == "Juan Martin Maldacena"
    assert lit.first_last("'t Hooft, Gerard") == "Gerard 't Hooft"
    assert lit.surname("Jan de Boer") == "de Boer"
    assert lit.surname("de Boer, Jan") == "de Boer"
    assert lit.surname("Juan M. Maldacena") == "Maldacena"


def fake_services(monkeypatch, core: bool, s2_fails: bool = False):
    """Stub INSPIRE (one target record, then the fixture hits) and Semantic Scholar."""
    calls = []
    target = dict(inspire_fixture()["hits"]["hits"][0]["metadata"], core=core)

    def fake_get_json(url, params=None):
        calls.append(url)
        if "semanticscholar" in url:
            if s2_fails:
                raise lit.LiteratureError("api.semanticscholar.org answered HTTP 429 Too Many Requests")
            return json.loads((FIXTURES / "s2_references.json").read_text())
        if params["q"].startswith("arxiv:"):
            return {"hits": {"total": 1, "hits": [{"metadata": target}]}}
        assert params["q"] == "citedby:recid:763100"
        return inspire_fixture()

    monkeypatch.setattr(lit, "get_json", fake_get_json)
    return calls


def test_references_of_a_core_record_come_from_inspire(monkeypatch):
    calls = fake_services(monkeypatch, core=True)
    data = lit.cmd_links("references", "0710.1060", limit=3)
    assert data["source"] == "INSPIRE" and data["total"] == 6
    assert not any("semanticscholar" in url for url in calls)
    text = lit.format_papers(data)
    assert text.splitlines()[0].startswith("INSPIRE: 6 papers cited by arXiv:0710.1060")
    assert " 2. hep-th/0309246 | insp:629588 | 2003 |" in text


def test_references_of_a_non_core_record_come_from_semantic_scholar(monkeypatch):
    fake_services(monkeypatch, core=False)
    data = lit.cmd_links("references", "0710.1060", limit=2)
    assert data["source"] == "Semantic Scholar" and data["total"] == 3
    assert [p["arxiv"] for p in data["results"]] == ["1705.03122", "1705.04304"]  # most cited first


def test_semantic_scholar_failure_falls_back_to_inspire(monkeypatch):
    fake_services(monkeypatch, core=False, s2_fails=True)
    data = lit.cmd_links("references", "0710.1060")
    assert data["source"] == "INSPIRE" and "Semantic Scholar failed" in data["note"]


def test_errors_are_one_line_without_traceback(capsys):
    assert lit.main(["references", "not-a-paper"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("ERROR: not a paper identifier") and "Traceback" not in err and err.count("\n") == 1


# ----- search over cards -----


def test_search_cards_ranks_and_snippets(toy, monkeypatch, capsys):
    toy.write("literature/P-hep-th_9711200.md",
              {"id": "P-hep-th_9711200", "kind": "paper", "title": "The Large N limit of superconformal field theories",
               "authors": ["Juan Martin Maldacena"]},
              "## Main result\nType IIB supergravity on AdS5 x S5 is dual to N=4 super-Yang-Mills.\n")
    toy.write("literature/P-1207.7214.md", {"id": "P-1207.7214", "kind": "paper", "title": "Observation of a new particle"},
              "## Main result\nA boson near 126 GeV.\n")
    (toy.root / "literature" / "overview.md").write_text(
        "# Overview of the literature\n\n## Holography\nThe sign of the supergravity action differs between papers.\n")
    toy.card("CL-S2-1", statement="At large N the central charge scales as $N^2$.")

    result = lit.search_cards(toy.root, "large N supergravity")
    paths = [hit["path"] for hit in result["results"]]
    assert paths[0] == "literature/P-hep-th_9711200.md"  # matches all three words
    assert set(paths) == {"literature/P-hep-th_9711200.md", "literature/overview.md", "claims/CL-S2-1.md"}
    overview = next(hit for hit in result["results"] if hit["kind"] == "overview")
    assert overview["title"] == "literature overview"
    assert "supergravity action" in overview["snippet"]
    assert result["searched"] == 4

    monkeypatch.chdir(toy.root / "claims")  # the workspace root is found from a subfolder
    assert lit.main(["search-cards", "boson", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [hit["path"] for hit in data["results"]] == ["literature/P-1207.7214.md"]


def test_search_cards_outside_a_workspace(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert lit.main(["search-cards", "anything"]) == 1
    assert "No project.toml" in capsys.readouterr().err


# ----- source archives -----


def make_tar(members: list[tarfile.TarInfo | tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for member in members:
            if isinstance(member, tarfile.TarInfo):
                tar.addfile(member)
            else:
                name, data = member
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def link(name: str, target: str, kind: bytes) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type, info.linkname = kind, target
    return info


def test_safe_extraction_skips_unsafe_members(tmp_path):
    dest = tmp_path / "src"
    dest.mkdir()
    data = make_tar([
        ("main.tex", b"\\documentclass{article}\\begin{document}x\\end{document}"),
        ("sections/intro.tex", b"intro"),
        ("../evil.tex", b"escape"),
        ("/abs.tex", b"absolute"),
        ("sections/../../evil2.tex", b"escape"),
        link("passwd", "/etc/passwd", tarfile.SYMTYPE),
        link("hard", "/etc/passwd", tarfile.LNKTYPE),
    ])
    kind, skipped = lit.unpack_eprint(data, dest, "1234.56789")
    assert kind == "source"
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert files == ["src/main.tex", "src/sections/intro.tex"]
    assert set(skipped) == {"../evil.tex", "/abs.tex", "sections/../../evil2.tex", "passwd", "hard"}
    assert not (dest / "passwd").exists()
    assert lit.find_main_tex(dest) == dest / "main.tex"


def gzip_with_name(name: bytes, content: bytes) -> bytes:
    """A gzip stream whose header stores `name` as is (GzipFile would keep only the base name)."""
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = deflate.compress(content) + deflate.flush()
    header = b"\x1f\x8b\x08\x08" + b"\0\0\0\0" + b"\x02\x03" + name + b"\0"
    return header + body + struct.pack("<II", zlib.crc32(content), len(content))


def test_single_gzipped_tex_keeps_a_safe_name(tmp_path):
    data = gzip_with_name(b"../../conffo.tex", b"\\input harvmac\n\\bye\n")
    assert lit.gzip_member_name(data) == "../../conffo.tex"
    kind, _ = lit.unpack_eprint(data, tmp_path, "hep-th_9711200")
    assert kind == "source"
    assert [p.name for p in tmp_path.iterdir()] == ["conffo.tex"]


def test_eprint_without_source(tmp_path):
    assert lit.unpack_eprint(b"%PDF-1.4 ...", tmp_path, "x")[0] == "pdf"
    assert (tmp_path / "x.pdf").exists()
    assert lit.unpack_eprint(gzip.compress(b"%!PS-Adobe-2.0"), tmp_path, "y")[0] is None
    assert lit.unpack_eprint(b"<!DOCTYPE html><html>error</html>", tmp_path, "z")[0] is None


def test_find_main_tex_prefers_the_document(tmp_path):
    (tmp_path / "macros.tex").write_text("\\newcommand{\\x}{y}" * 100)
    (tmp_path / "paper.tex").write_text("\\documentclass{revtex4}\\begin{document}\\input{macros}\\end{document}")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "old.tex").write_text("\\documentclass{article}\\begin{document}\\end{document}")
    assert lit.find_main_tex(tmp_path) == tmp_path / "paper.tex"


def test_download_into_the_workspace(toy, monkeypatch):
    monkeypatch.chdir(toy.root)
    tarball = make_tar([("ms.tex", b"\\documentclass{article}\\begin{document}\\end{document}"), ("fig.png", b"png")])
    requested = []

    def fake_http_get(url, params=None, **kwargs):
        requested.append(url)
        return tarball

    monkeypatch.setattr(lit, "http_get", fake_http_get)
    data = lit.cmd_download("hep-th/9711200v2")
    assert requested == ["https://arxiv.org/e-print/hep-th/9711200v2"]
    assert data["folder"] == "literature/sources/hep-th_9711200/"
    assert data["main"] == "literature/sources/hep-th_9711200/ms.tex" and data["kind"] == "source"
    assert [f["path"] for f in data["files"]] == ["fig.png", "ms.tex"]
    assert "Main file: literature/sources/hep-th_9711200/ms.tex" in lit.format_download(data)

    again = lit.cmd_download("hep-th/9711200")
    assert again["status"] == "already downloaded" and len(requested) == 1
    assert not list((toy.root / "literature" / "sources").glob("*.partial"))


def test_download_falls_back_to_the_pdf(toy, monkeypatch):
    monkeypatch.chdir(toy.root)

    def fake_http_get(url, params=None, **kwargs):
        if "/e-print/" in url:
            raise lit.HTTPStatusError("arxiv.org answered HTTP 404 Not Found", 404)
        return b"%PDF-1.5 body"

    monkeypatch.setattr(lit, "http_get", fake_http_get)
    data = lit.cmd_download("2301.01234")
    assert data["kind"] == "pdf" and data["main"] == "literature/sources/2301.01234/2301.01234.pdf"
