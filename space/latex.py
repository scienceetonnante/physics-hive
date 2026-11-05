r"""Convert the LaTeX subset of PhysicsHive notes and drafts into an HTML fragment.

Agents write short research notes (sessions/S<n>/note.tex) and a shared draft paper
(draft.tex) in plain LaTeX: amsmath, sections, lists, tables, footnotes, \cite, \ref,
\eqref, \card, and the environments result, conjecture, theorem and proof (also lemma,
proposition, corollary, definition, remark). The Space shows them as web pages styled
like arXiv's HTML papers, with latex.css.

This module does not typeset math. It passes math through, HTML-escaped, as \(...\),
\[...\] or the raw \begin{equation}...\end{equation} text, and MathJax 3 finds it in the
page. MathJax must be configured with inlineMath [['\\(','\\)']], displayMath
[['\\[','\\]']], tags 'ams', processEnvironments and processRefs: it then numbers the
equations and resolves the \ref and \eqref to equation labels that this module leaves in
the text. Everything else (sections, numbering, labels, footnotes, citations, lists,
tables, theorem-like blocks) is converted here.

Public interface:
    render(tex, bib=None, card_href=None, card_note=None, paper_href=None) -> Rendered
    parse_bib(text) -> {key: {field: value}}   (field names lowercase, plus "entrytype")
    document_html(rendered) -> str             (one <article class="ltx-document">)

The converter never raises on malformed input: it renders what it can and lists what it
could not handle in Rendered.problems. All text is HTML-escaped; the only tags in the
output are the ones generated here. Preamble \newcommand definitions go to MathJax in a
hidden element at the start of the body; document_html moves it above the title so that
math in the title and abstract can use them too.

CSS classes (styled in latex.css):
    ltx-document        the whole article (document_html)
    ltx-title, ltx-authors, ltx-date, ltx-abstract   title block and abstract (document_html)
    ltx-macros          hidden div with the \newcommand definitions for MathJax
    ltx-section, ltx-subsection, ltx-subsubsection   h2, h3, h4 headings
    ltx-num             the number inside a heading ("2", "2.1", "Appendix A")
    ltx-paragraph       run-in heading of \paragraph
    ltx-eq              display math (a div, or a span inside inline content)
    ltx-thm             theorem-like block, with ltx-thm-<kind> (ltx-thm-result, ...) and
    ltx-thm-it          for an italic body; ltx-thm-head for "Result 1 (title)."
    ltx-proof, ltx-proof-head, ltx-qed, ltx-qed-line   proof block, heading, end mark
    ltx-flag            warning at the top of a theorem-like block (from card_note)
    ltx-card            card tag (a link, or code without link); ltx-card-flagged if noted
    ltx-list            ul, ol and dl lists; ltx-description on dl; ltx-item-labelled and
    ltx-item-label      for \item[label] in itemize and enumerate
    ltx-table           figure of a table environment; ltx-caption-head for "Table 1."
    ltx-caption         a \caption outside a table
    ltx-tabular-wrap    scrolling wrapper of ltx-tabular; cells ltx-al-l, ltx-al-c, ltx-al-r;
    ltx-rule            body row that follows an \hline or \midrule
    ltx-center, ltx-quote, ltx-sc, ltx-sf   center and quote blocks, small caps, sans serif
    ltx-link            external link (\url, \href, bibliography)
    ltx-ref             link to a section, theorem-like block or table
    ltx-cite            citation link; ltx-cite-missing for an unknown key ("?")
    ltx-fn              footnote marker (sup); ltx-fn-text is the footnote text next to it,
                        hidden: the page shows it by adding class ltx-open to the marker
    ltx-footnotes       footnote list at the end of the body; ltx-fn-back back-link
    ltx-bibliography    References section; ltx-bib (ol), ltx-bib-label, ltx-bib-title
    ltx-source          the escaped source, shown only if the converter itself fails
"""

from __future__ import annotations

import datetime
import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional

__all__ = ["TocEntry", "Rendered", "render", "parse_bib", "document_html"]


@dataclass
class TocEntry:
    """One heading of the table of contents."""
    level: int    # 1 for \section, 2 for \subsection, 3 for \subsubsection
    number: str   # "1", "1.2", "A", "" for starred headings and References
    title: str    # HTML, without footnote markers or links
    anchor: str   # id of the heading


@dataclass
class Rendered:
    """The converted document. All strings are HTML except problems (plain text)."""
    title: str = ""
    authors: str = ""
    date: str = ""
    abstract: str = ""
    body: str = ""
    toc: list[TocEntry] = field(default_factory=list)
    cards: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------- tables

THEOREMS = {  # environment -> (heading, italic body)
    "result": ("Result", True), "conjecture": ("Conjecture", True),
    "theorem": ("Theorem", True), "lemma": ("Lemma", True),
    "proposition": ("Proposition", True), "corollary": ("Corollary", True),
    "definition": ("Definition", False), "remark": ("Remark", False),
}
MATH_ENVS = {name + star for star in ("", "*") for name in
             ("equation", "align", "gather", "multline", "eqnarray", "flalign", "alignat")}
SECTION_LEVELS = {"section": 1, "subsection": 2, "subsubsection": 3}
STARRED = set(SECTION_LEVELS) | {"paragraph", "newcommand", "renewcommand", "providecommand",
                                 "DeclareMathOperator", "newtheorem", "vspace", "hspace"}

_EM, _STRONG, _CODE = ("<em>", "</em>"), ("<strong>", "</strong>"), ("<code>", "</code>")
_SC, _SF, _NONE = ('<span class="ltx-sc">', "</span>"), ('<span class="ltx-sf">', "</span>"), ("", "")
STYLES = {  # one-argument text styles -> (opening tag, closing tag)
    "emph": _EM, "textit": _EM, "textsl": _EM, "textbf": _STRONG, "texttt": _CODE,
    "textsc": _SC, "textsf": _SF, "underline": ("<u>", "</u>"),
    "textsuperscript": ("<sup>", "</sup>"), "textsubscript": ("<sub>", "</sub>"),
    "textrm": _NONE, "textnormal": _NONE, "textup": _NONE, "textmd": _NONE,
    "text": _NONE, "mbox": _NONE, "hbox": _NONE, "fbox": _NONE,
}
SWITCHES = {  # declarations such as {\bf ...}: they style the rest of the group
    "bf": _STRONG, "bfseries": _STRONG, "it": _EM, "itshape": _EM, "em": _EM, "sl": _EM,
    "slshape": _EM, "tt": _CODE, "ttfamily": _CODE, "sc": _SC, "scshape": _SC, "sf": _SF,
    "sffamily": _SF,
}
SYMBOLS = {  # control words that print something (values are HTML)
    "ldots": "…", "dots": "…", "textellipsis": "…", "LaTeX": "LaTeX", "TeX": "TeX",
    "S": "§", "P": "¶", "dag": "†", "ddag": "‡", "copyright": "©", "textregistered": "®",
    "texttrademark": "™", "textbackslash": "\\", "textasciitilde": "~", "textasciicircum": "^",
    "textbar": "|", "textless": "&lt;", "textgreater": "&gt;", "textendash": "–",
    "textemdash": "—", "textquoteleft": "‘", "textquoteright": "’", "textquotedblleft": "“",
    "textquotedblright": "”", "textdegree": "°", "textbullet": "•", "quad": "\u2003",
    "qquad": "\u2003\u2003", "enspace": "\u2002", "thinspace": "\u202f", "newline": "<br>",
    "i": "ı", "j": "ȷ", "ss": "ß", "o": "ø", "O": "Ø", "ae": "æ", "AE": "Æ",
    "oe": "œ", "OE": "Œ", "aa": "å", "AA": "Å", "l": "ł", "L": "Ł",
}
CONTROL_SYMBOLS = {  # \% \& ... (values are HTML)
    "%": "%", "&": "&amp;", "_": "_", "#": "#", "$": "$", "{": "{", "}": "}",
    ",": "\u202f", " ": " ", "\n": " ", "\t": " ", ";": " ", ":": " ",
    "!": "", "/": "", "-": "", "@": "",
}
ACCENTS = {  # accent command -> combining character
    "'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303", "=": "\u0304",
    ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b", "c": "\u0327", "k": "\u0328",
    "r": "\u030a", "d": "\u0323", "b": "\u0331",
}
IGNORED = {  # commands dropped silently, with their arguments ("o" optional, "m" mandatory)
    "documentclass": "om", "usepackage": "om", "RequirePackage": "om", "theoremstyle": "m",
    "bibliographystyle": "m", "geometry": "m", "hypersetup": "m", "pagestyle": "m",
    "thispagestyle": "m", "setlength": "mm", "addtolength": "mm", "setcounter": "mm",
    "addtocounter": "mm", "numberwithin": "mm", "vspace": "m", "hspace": "m", "cline": "m",
    "graphicspath": "m", "definecolor": "mmm", "allowdisplaybreaks": "o", "nocite": "m",
    "pagebreak": "o", "nopagebreak": "o", "linebreak": "o", "nolinebreak": "o",
    "toprule": "o", "midrule": "o", "bottomrule": "o", "addlinespace": "o",
    **dict.fromkeys(
        "maketitle noindent indent medskip bigskip smallskip centering raggedright raggedleft "
        "newpage clearpage tableofcontents small footnotesize scriptsize tiny normalsize large "
        "Large LARGE huge Huge normalfont rmfamily upshape mdseries protect relax hline hfill "
        "vfill null leavevmode phantomsection makeatletter makeatother frenchspacing sloppy "
        "selectfont newblock FloatBarrier".split(), ""),
}

_PLAIN = re.compile(r"[^\\{}$~\-`'\n]+")           # text with nothing special in it
_BLANK = re.compile(r"\n[ \t]*\n\s*")               # a paragraph break
_WS = re.compile(r"[ \t]*(?:\n(?![ \t]*\n)[ \t]*)?")  # spaces and at most one line break
_CSNAME = re.compile(r"\\([A-Za-z]+|[\s\S]?)")
_COMMENT = re.compile(r"(?<!\\)((?:\\\\)*)%[^\n]*(?:\n[ \t]*+(?!\n))?")
_BEGIN_END = re.compile(r"\\(begin|end)\s*\{[^{}]*\}")
_ITEM = re.compile(r"\\item(?![A-Za-z])")
_BIBITEM = re.compile(r"\\bibitem(?![A-Za-z])")
_ROW_END = re.compile(r"\\\\\*?(?:[ \t]*\[[^\]\n]*\])?")
_CELL_SEP = re.compile(r"&")
_RULE = re.compile(r"\s*\\(?:(hline|toprule|midrule|bottomrule|addlinespace)(?![A-Za-z])"
                   r"(?:\s*\[[^\]]*\])?|(cline|cmidrule)\s*(?:\[[^\]]*\])?\s*(?:\([^)]*\))?\s*\{[^}]*\})")
_MATH_LABEL = re.compile(r"\\label\s*\{([^{}]*)\}")
_PLACEHOLDER = re.compile("\x00(\\d+)\x00")
_BIB_MARK = "\x00bib\x00"
_SAFE_URL = re.compile(r"\s*(https?:|mailto:)", re.I)


def _esc(s: str) -> str:
    """Escape text for an HTML text node."""
    return html.escape(s, quote=False)


def _attr(s: str) -> str:
    """Escape text for an HTML attribute value."""
    return html.escape(s, quote=True)


def _link(url: str, inner_html: str) -> str:
    """A link for http, https and mailto URLs; other URLs give the text alone."""
    if not _SAFE_URL.match(url):
        return inner_html
    return f'<a class="ltx-link" href="{_attr(url.strip())}" rel="noopener" target="_blank">{inner_html}</a>'


def _accent(mark: str, letter: str) -> str:
    r"""Apply a LaTeX accent (\'e, \c{c}, \^\i, ...) to a letter, as Unicode."""
    base = {"\\i": "i", "\\j": "j"}.get(letter.strip(), letter.strip())
    if not base:
        return ""
    return unicodedata.normalize("NFC", base[0] + ACCENTS[mark]) + base[1:]


def _find(src: str, target: str, i: int) -> int:
    """Index of the first target at or after i that is not escaped by a backslash, or -1."""
    while i < len(src):
        if src.startswith(target, i):
            return i
        i += 2 if src[i] == "\\" else 1
    return -1


def _match_brace(s: str, i: int) -> int:
    """Index of the } that closes the { at s[i], or -1."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _group_at(s: str, i: int) -> tuple[Optional[str], int]:
    """Read a braced group after optional whitespace: (content, index after it), or (None, i)."""
    j = len(s) - len(s[i:].lstrip())
    if j < len(s) and s[j] == "{":
        k = _match_brace(s, j)
        if k >= 0:
            return s[j + 1:k], k + 1
    return None, i


def _split_top(src: str, token: re.Pattern) -> list[str]:
    """Split src at each match of token that is outside braces, math and nested environments.

    The first piece is the text before the first token."""
    pieces, start, depth, i = [], 0, 0, 0
    while i < len(src):
        if depth == 0:
            m = token.match(src, i)
            if m:
                pieces.append(src[start:i])
                start = i = m.end()
                continue
        c = src[i]
        if c == "\\":
            m = _BEGIN_END.match(src, i)
            if m:
                depth = depth + 1 if m.group(1) == "begin" else max(depth - 1, 0)
                i = m.end()
            elif src.startswith(("\\(", "\\["), i):
                end = _find(src, "\\)" if src[i + 1] == "(" else "\\]", i + 2)
                i = len(src) if end < 0 else end + 2
            else:
                i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(depth - 1, 0)
        elif c == "$":
            two = src.startswith("$$", i)
            end = _find(src, "$$" if two else "$", i + (2 if two else 1))
            i = i + 1 if end < 0 else end + (2 if two else 1)
            continue
        i += 1
    pieces.append(src[start:])
    return pieces


def _colspec(spec: str) -> list[str]:
    """Column alignments ("l", "c" or "r") from a tabular column specification."""
    aligns, i = [], 0
    while i < len(spec):
        c = spec[i]
        i += 1
        if c in "lcr":
            aligns.append(c)
        elif c in "pmbX":
            aligns.append("l")
            if c != "X":
                _, i = _group_at(spec, i)
        elif c in "@!<>":
            _, i = _group_at(spec, i)
        elif c == "*":
            count, i = _group_at(spec, i)
            inner, i = _group_at(spec, i)
            if count and count.strip().isdigit():
                aligns += _colspec(inner or "") * min(int(count), 50)
    return aligns


def _letters(n: int) -> str:
    """Appendix numbering: 1 -> A, 26 -> Z, 27 -> AA."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s or "0"


def _text_of(fragment: str) -> str:
    """Plain text of an HTML fragment produced here."""
    return html.unescape(re.sub(r"<[^>]+>", "", _PLACEHOLDER.sub("", fragment))).strip()


def _strip_links(fragment: str) -> str:
    """Remove <a> tags (keeping their content), for titles shown inside a contents link."""
    return re.sub(r"</?a\b[^>]*>", "", fragment)


def _prepend(inner: str, head: str) -> str:
    """Put head at the start of the first paragraph of inner, or in its own paragraph."""
    if inner.startswith("<p>"):
        return "<p>" + head + inner[3:]
    return f"<p>{head.strip()}</p>" + inner


def _unwrap(inner: str) -> str:
    """Drop the <p> around content made of a single paragraph (list items)."""
    if inner.startswith("<p>") and inner.endswith("</p>") and inner.count("<p>") == 1:
        return inner[3:-4]
    return inner


@dataclass
class _Target:
    """What a \\label points to: the anchor, the text \\ref prints, and a longer name."""
    anchor: str
    number: str
    long: str


class _Out:
    """Collects HTML. In block mode, inline pieces are gathered into <p> paragraphs and
    block pieces go between them; in inline mode everything is concatenated."""

    def __init__(self, block: bool):
        self.block, self.blocks, self.inline = block, [], []

    def add(self, piece: str) -> None:
        self.inline.append(piece)

    def par(self) -> None:
        if not self.block:
            self.inline.append(" ")
            return
        text = "".join(self.inline).strip()
        self.inline = []
        if text:
            self.blocks.append(f"<p>{text}</p>")

    def put(self, piece: str) -> None:
        if self.block:
            self.par()
            self.blocks.append(piece)
        else:
            self.inline.append(piece)

    def display(self, math_html: str) -> None:
        tag = "div" if self.block else "span"
        self.put(f'<{tag} class="ltx-eq">{math_html}</{tag}>')

    def html(self) -> str:
        if not self.block:
            return "".join(self.inline)
        self.par()
        return "\n".join(self.blocks)


# ------------------------------------------------------------------------ converter

class _Converter:
    """One conversion: walks the source once, collecting counters, labels, footnotes and
    citations, then resolves the deferred \\ref and \\cite and assembles the result."""

    def __init__(self, bib, card_href, card_note, paper_href):
        self.bib = bib or {}
        self.bib_lower = {k.lower(): k for k in self.bib}
        self.card_href, self.card_note, self.paper_href = card_href, card_note, paper_href
        self.problems: list[str] = []
        self.cards: list[str] = []
        self.toc: list[TocEntry] = []
        self.meta = {"title": "", "author": "", "date": ""}
        self.meta_src: dict[str, str] = {}
        self.abstract = ""
        self.macros: dict[str, tuple[int, Optional[str], str]] = {}
        self.mathjax_defs: list[str] = []
        self.theorems = dict(THEOREMS)
        self.counts: dict[str, int] = {}          # theorem-like environments and tables
        self.sections, self.appendix, self.anchors = [0, 0, 0], False, set()
        self.target: Optional[_Target] = None     # what a \label points to here
        self.labels: dict[str, _Target] = {}
        self.math_labels: set[str] = set()
        self.footnotes: list[str] = []
        self.fn_sink: Optional[list[str]] = None  # collects footnote markers of a heading
        self.cited: list[str] = []
        self.cite_num: dict[str, int] = {}
        self.bibitems: dict[str, str] = {}
        self.bib_toc_index: Optional[int] = None
        self.pending: list[tuple] = []            # deferred \ref and \cite
        self.card_scopes: list[list[str]] = []    # cards named in open theorem-like blocks
        self.captions: list[list[str]] = []       # captions of open table environments
        self.notes_cache: dict[str, Optional[str]] = {}
        self.quiet, self.depth, self.expansions = False, 0, 0
        self.handlers = {
            **dict.fromkeys(SECTION_LEVELS, self._heading),
            **dict.fromkeys(("cite", "citep", "citet", "citealp", "citealt"), self._cite),
            **dict.fromkeys(("ref", "eqref"), self._ref),
            **dict.fromkeys(("footnote", "thanks"), self._footnote),
            **dict.fromkeys(("title", "author", "date"), self._meta),
            **dict.fromkeys(("newcommand", "renewcommand", "providecommand"), self._newcommand),
            "def": self._def, "DeclareMathOperator": self._mathop, "newtheorem": self._newtheorem,
            "paragraph": self._paragraph, "appendix": self._appendix, "begin": self._begin,
            "end": self._end, "label": self._label, "card": self._card, "url": self._url,
            "href": self._href, "bibliography": self._bibliography, "caption": self._caption,
            "item": self._stray_item, "par": self._par, "multicolumn": self._multicolumn,
            "today": self._today,
        }

    # -- small helpers

    def _problem(self, message: str) -> None:
        if message not in self.problems:
            self.problems.append(message)

    def _defer(self, *item) -> str:
        """A placeholder for something resolved after the whole pass (\\ref, \\cite)."""
        self.pending.append(item)
        return f"\x00{len(self.pending) - 1}\x00"

    def _unique_anchor(self, anchor: str) -> str:
        base, k = anchor, 1
        while anchor in self.anchors:
            k += 1
            anchor = f"{base}-{k}"
        self.anchors.add(anchor)
        return anchor

    def _arg(self, src: str, i: int) -> tuple[Optional[str], int]:
        """Read a mandatory argument: a braced group, a control sequence or one character."""
        j = _WS.match(src, i).end()
        if j >= len(src) or src[j] in "}\n":
            return None, i
        if src[j] == "{":
            return self._braced(src, j)
        if src[j] == "\\":
            m = _CSNAME.match(src, j)
            return m.group(0), m.end()
        return src[j], j + 1

    def _braced(self, src: str, j: int) -> tuple[str, int]:
        """The content of the group opened at src[j] and the index after it. A group that
        is never closed ends at the end of its paragraph."""
        k = _match_brace(src, j)
        if k >= 0:
            return src[j + 1:k], k + 1
        self._problem("unbalanced braces: a { is never closed")
        m = _BLANK.search(src, j)
        end = m.start() if m else len(src)
        return src[j + 1:end], end

    def _opt(self, src: str, i: int) -> tuple[Optional[str], int]:
        """Read an optional [argument]; brackets inside braces do not close it."""
        j = _WS.match(src, i).end()
        if not src.startswith("[", j):
            return None, i
        depth, k = 0, j + 1
        while k < len(src):
            c = src[k]
            if c == "\\":
                k += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth < 0:
                    break
            elif c == "]" and depth == 0:
                if _BLANK.search(src, j, k):
                    break
                return src[j + 1:k], k + 1
            k += 1
        return None, i

    def _lead_opt(self, body: str) -> tuple[Optional[str], str]:
        opt, j = self._opt(body, 0)
        return opt, body[j:]

    def _note(self, card_id: str) -> Optional[str]:
        if self.card_note is None:
            return None
        if card_id not in self.notes_cache:
            self.notes_cache[card_id] = self.card_note(card_id)
        return self.notes_cache[card_id]

    # -- the main loop

    def _conv(self, src: str, block: bool, tt: bool = False) -> str:
        """Convert LaTeX to HTML. Block mode makes paragraphs and block elements (document
        body, environments); inline mode makes phrasing content (arguments, headings, table
        cells, footnotes). tt turns off the dash and quote ligatures (typewriter text)."""
        if self.depth > 100:
            self._problem("nesting too deep; part of the source is shown as is")
            return _esc(src)
        self.depth += 1
        try:
            out, i = _Out(block), 0
            while i < len(src):
                m = _PLAIN.match(src, i)
                if m:
                    out.add(_esc(m.group()))
                    i = m.end()
                    continue
                c = src[i]
                if c == "\\":
                    src, i = self._command(src, i, out, tt)
                elif c == "{":
                    group, i = self._braced(src, i)
                    out.add(self._conv(group, False, tt))
                elif c == "}":
                    self._problem("unbalanced braces: unexpected }")
                    i += 1
                elif c == "$":
                    i = self._dollar(src, i, out)
                elif c == "\n":
                    m = _BLANK.match(src, i)
                    if m:
                        out.par()
                        i = m.end()
                    else:
                        out.add("\n")
                        i += 1
                elif c == "~":
                    out.add("&nbsp;")
                    i += 1
                elif tt:
                    out.add(c)
                    i += 1
                else:
                    for lig, char in (("---", "—"), ("--", "–"), ("``", "“"), ("''", "”"),
                                      ("`", "‘"), ("'", "’"), ("-", "-")):
                        if src.startswith(lig, i):
                            out.add(char)
                            i += len(lig)
                            break
            return out.html()
        finally:
            self.depth -= 1

    def _command(self, src: str, i: int, out: _Out, tt: bool) -> tuple[str, int]:
        """Handle the control sequence at src[i]. Returns (src, index after it); src only
        changes when a user macro is expanded in place."""
        m = _CSNAME.match(src, i)
        name, j = m.group(1), m.end()
        star = False
        if not name:
            self._problem("a backslash ends the text")
            return src, j
        if name.isascii() and name.isalpha():  # TeX skips the spaces after a control word
            j = _WS.match(src, j).end()
            if name in STARRED and src.startswith("*", j):
                star, j = True, j + 1
        if name == "\\":
            j = j + 1 if src.startswith("*", j) else j
            _, j = self._opt(src, j)
            out.add("<br>")
            return src, j
        if name in ("(", "["):
            close = "\\)" if name == "(" else "\\]"
            end = _find(src, close, j)
            if end < 0:
                self._problem(f"unclosed \\{name} (math)")
            tex, k = (src[j:], len(src)) if end < 0 else (src[j:end], end + 2)
            if name == "(":
                out.add(self._inline_math(tex))
            else:
                self._display(tex, out)
            return src, k
        if name in ACCENTS:
            arg, j = self._arg(src, j)
            out.add(_esc(_accent(name, arg or "")))
            return src, j
        if name in CONTROL_SYMBOLS:
            out.add(CONTROL_SYMBOLS[name])
            return src, j
        if name in self.handlers:
            return src, self.handlers[name](name, star, src, j, out)
        if name in STYLES:
            arg, j = self._arg(src, j)
            opening, closing = STYLES[name]
            out.add(opening + self._conv(arg or "", False, tt or name == "texttt") + closing)
            return src, j
        if name in SWITCHES:
            if out.block:
                return src, j
            opening, closing = SWITCHES[name]
            out.add(opening + self._conv(src[j:], False, tt or opening == "<code>") + closing)
            return src, len(src)
        if name in SYMBOLS:
            out.add(SYMBOLS[name])
            return src, j
        if name in IGNORED:
            for kind in IGNORED[name]:
                _, j = (self._opt if kind == "o" else self._arg)(src, j)
            return src, j
        if name in self.macros:
            return self._expand(name, src, i, j)
        return src, self._unknown(name, src, j, out, tt)

    def _unknown(self, name: str, src: str, j: int, out: _Out, tt: bool) -> int:
        """An unsupported command: report it once and keep the text of its braced arguments."""
        self._problem(f"unsupported command \\{name}")
        while True:
            opt, k = self._opt(src, j)
            if opt is None:
                k = _WS.match(src, j).end()
                if not src.startswith("{", k):
                    return j
                body, k = self._arg(src, k)
                out.add(self._conv(body or "", False, tt))
            j = k

    def _expand(self, name: str, src: str, i: int, j: int) -> tuple[str, int]:
        """Expand a user macro (from \\newcommand or \\def) in text mode, in place."""
        self.expansions += 1
        if self.expansions > 2000:
            self._problem("too many macro expansions (is a \\newcommand recursive?)")
            return src, j
        n, default, body = self.macros[name]
        args: list[str] = []
        if n and default is not None:
            opt, j = self._opt(src, j)
            args.append(default if opt is None else opt)
        while len(args) < n:
            arg, j = self._arg(src, j)
            args.append(arg or "")

        def substitute(m: re.Match) -> str:
            if m.group(1) == "#":
                return "#"
            k = int(m.group(1))
            return args[k - 1] if k <= n else ""

        return src[:i] + re.sub(r"#([1-9#])", substitute, body) + src[j:], i

    # -- math

    def _scan_labels(self, tex: str) -> None:
        for key in _MATH_LABEL.findall(tex):
            key = key.strip()
            if key in self.math_labels or key in self.labels:
                self._problem(f"label {key} is defined more than once")
            self.math_labels.add(key)

    def _inline_math(self, tex: str) -> str:
        self._scan_labels(tex)
        return "\\(" + _esc(tex) + "\\)"

    def _display(self, tex: str, out: _Out) -> None:
        self._scan_labels(tex)
        out.display("\\[" + _esc(tex) + "\\]")

    def _dollar(self, src: str, i: int, out: _Out) -> int:
        """$...$ and $$...$$. An unclosed $ is kept as a literal dollar."""
        if src.startswith("$$", i):
            end = _find(src, "$$", i + 2)
            if end >= 0:
                self._display(src[i + 2:end], out)
                return end + 2
            self._problem("unclosed $$ (math)")
            out.add("$$")
            return i + 2
        end = _find(src, "$", i + 1)
        if end < 0 or _BLANK.search(src, i, end):
            self._problem("unclosed $ (math)")
            out.add("$")
            return i + 1
        out.add(self._inline_math(src[i + 1:end]))
        return end + 1

    # -- document structure

    def _meta(self, name, star, src, i, out):
        _, i = self._opt(src, i)
        raw, i = self._arg(src, i)
        if self.quiet:   # in the preamble: converted once the macros are known
            self.meta_src[name] = raw or ""
        else:
            self.meta[name] = self._convert_meta(raw or "")
        return i

    def _convert_meta(self, raw: str) -> str:
        """Convert a title, author list or date; \\and separates authors."""
        parts = (self._conv(p, False).strip() for p in re.split(r"\\and(?![A-Za-z])", raw))
        return ", ".join(p for p in parts if p)

    def _heading(self, name, star, src, i, out):
        _, i = self._opt(src, i)
        title_src, i = self._arg(src, i)
        title_src = title_src or ""
        level = SECTION_LEVELS[name]
        if star:
            number, anchor = "", ""   # the anchor comes from the title, below
        else:
            self.sections[level - 1] += 1
            for k in range(level, 3):
                self.sections[k] = 0
            first = _letters(self.sections[0]) if self.appendix else str(self.sections[0])
            number = ".".join([first] + [str(x) for x in self.sections[1:level]])
            anchor = self._unique_anchor("sec-" + number)
        kind = "Appendix" if self.appendix else "Section"
        self.target = target = _Target(anchor, number, f"{kind} {number}")
        saved, self.fn_sink = self.fn_sink, []
        title = self._conv(title_src, False).strip()
        markers, self.fn_sink = "".join(self.fn_sink), saved
        if star:
            target.number = target.long = _text_of(title)
            slug = re.sub(r"[^a-z0-9]+", "-", target.number.lower()).strip("-")[:40]
            anchor = target.anchor = self._unique_anchor("sec-" + (slug or "section"))
        self.toc.append(TocEntry(level, number, title, anchor))
        shown = f"Appendix {number}" if self.appendix and level == 1 and number else number
        num = f'<span class="ltx-num">{shown}</span> ' if shown else ""
        tag = f"h{level + 1}"
        out.put(f'<{tag} class="ltx-{name}" id="{anchor}">{num}{title}{markers}</{tag}>')
        return i

    def _paragraph(self, name, star, src, i, out):
        _, i = self._opt(src, i)
        title, i = self._arg(src, i)
        out.par()
        out.add(f'<strong class="ltx-paragraph">{self._conv(title or "", False).strip()}</strong> ')
        return i

    def _appendix(self, name, star, src, i, out):
        self.appendix, self.sections = True, [0, 0, 0]
        return i

    def _par(self, name, star, src, i, out):
        out.par()
        return i

    def _today(self, name, star, src, i, out):
        d = datetime.date.today()
        out.add(f"{d.day} {d:%B %Y}")
        return i

    # -- macros and definitions

    def _newcommand(self, name, star, src, i, out):
        cs, i = self._arg(src, i)
        nargs, i = self._opt(src, i)
        default, i = self._opt(src, i)
        body, i = self._arg(src, i)
        m = re.fullmatch(r"\s*\\([A-Za-z]+)\s*", cs or "")
        if not m or body is None:
            self._problem(f"malformed \\{name}")
            return i
        macro = m.group(1)
        if macro == "card" or (name == "providecommand" and macro in self.macros):
            return i
        n = min(int(nargs), 9) if nargs and nargs.strip().isdigit() else 0
        self.macros[macro] = (n, default, body)
        spec = (f"[{n}]" if n else "") + (f"[{default}]" if default is not None and n else "")
        self.mathjax_defs.append(f"\\newcommand{{\\{macro}}}{spec}{{{body}}}")
        return i

    def _def(self, name, star, src, i, out):
        m = re.compile(r"\s*\\([A-Za-z]+)((?:#[1-9])*)\s*").match(src, i)
        body, j = _group_at(src, m.end()) if m else (None, i)
        if body is None:
            self._problem("malformed \\def")
            return i
        params = m.group(2)
        if m.group(1) != "card":
            self.macros[m.group(1)] = (len(params) // 2, None, body)
            self.mathjax_defs.append(f"\\def\\{m.group(1)}{params}{{{body}}}")
        return j

    def _mathop(self, name, star, src, i, out):
        cs, i = self._arg(src, i)
        text, i = self._arg(src, i)
        if cs and text is not None:
            self.mathjax_defs.append(f"\\DeclareMathOperator{'*' if star else ''}{{{cs.strip()}}}{{{text}}}")
        return i

    def _newtheorem(self, name, star, src, i, out):
        env, i = self._arg(src, i)
        _, i = self._opt(src, i)
        heading, i = self._arg(src, i)
        _, i = self._opt(src, i)
        env = (env or "").strip()
        if env and heading and env not in self.theorems:
            self.theorems[env] = (re.sub(r"\\[A-Za-z]+|[{}]", "", heading).strip(), True)
        return i

    def _read_preamble(self, src: str) -> None:
        """Collect macro and theorem definitions and the title, author and date."""
        names = "newcommand|renewcommand|providecommand|DeclareMathOperator|def|newtheorem|title|author|date"
        pattern = re.compile(r"\\(" + names + r")(?![A-Za-z])\s*(\*?)")
        self.quiet, i = True, 0
        while m := pattern.search(src, i):
            i = max(self.handlers[m.group(1)](m.group(1), bool(m.group(2)), src, m.end(), _Out(False)),
                    m.end())
        self.quiet = False

    # -- labels, references, citations, footnotes, cards, links

    def _label(self, name, star, src, i, out):
        key, i = self._arg(src, i)
        key = (key or "").strip()
        if not key:
            return i
        if key in self.labels or key in self.math_labels:
            self._problem(f"label {key} is defined more than once")
        if self.target is None:
            self._problem(f"label {key} is not inside a section, theorem-like block or table")
        else:
            self.labels[key] = self.target
        return i

    def _ref(self, name, star, src, i, out):
        key, i = self._arg(src, i)
        out.add(self._defer("ref", name, (key or "").strip()))
        return i

    def _cite(self, name, star, src, i, out):
        first, i = self._opt(src, i)
        second, i = self._opt(src, i)
        keys, i = self._arg(src, i)
        pre, post = (first, second) if second is not None else (None, first)
        keys = [k.strip() for k in (keys or "").split(",") if k.strip()]
        for k in keys:
            if k not in self.cited:
                self.cited.append(k)
        pre = self._conv(pre, False).strip() if pre else ""
        post = self._conv(post, False).strip() if post else ""
        out.add(self._defer("cite", keys, pre, post))
        return i

    def _footnote(self, name, star, src, i, out):
        _, i = self._opt(src, i)
        text, i = self._arg(src, i)
        self.footnotes.append("")
        n = len(self.footnotes)
        note = self._conv(text or "", False).strip()
        self.footnotes[n - 1] = note
        marker = (f'<sup class="ltx-fn" id="fnref-{n}"><a href="#fn-{n}">{n}</a>'
                  f'<span class="ltx-fn-text" hidden>{note}</span></sup>')
        if self.fn_sink is not None:
            self.fn_sink.append(marker)
        else:
            out.add(marker)
        return i

    def _card(self, name, star, src, i, out):
        arg, i = self._arg(src, i)
        tags = []
        for card_id in (x.strip().replace("\\_", "_") for x in (arg or "").split(",")):
            if not card_id:
                continue
            if card_id not in self.cards:
                self.cards.append(card_id)
            for scope in self.card_scopes:
                scope.append(card_id)
            href = self.card_href(card_id) if self.card_href else None
            note = self._note(card_id)
            attrs = ' class="ltx-card ltx-card-flagged"' if note else ' class="ltx-card"'
            attrs += f' title="{_attr(note)}"' if note else ""
            if href:
                tags.append(f'<a{attrs} href="{_attr(href)}">{_esc(card_id)}</a>')
            else:
                tags.append(f"<code{attrs}>{_esc(card_id)}</code>")
        out.add(" ".join(tags))
        return i

    def _url(self, name, star, src, i, out):
        url, i = self._arg(src, i)
        url = re.sub(r"\\([_%#&~])", r"\1", url or "")
        out.add(_link(url, _esc(url)))
        return i

    def _href(self, name, star, src, i, out):
        url, i = self._arg(src, i)
        text, i = self._arg(src, i)
        out.add(_link(re.sub(r"\\([_%#&~])", r"\1", url or ""), self._conv(text or "", False)))
        return i

    def _caption(self, name, star, src, i, out):
        _, i = self._opt(src, i)
        text, i = self._arg(src, i)
        caption = self._conv(text or "", False).strip()
        if self.captions:
            self.captions[-1].append(caption)
        else:
            out.put(f'<div class="ltx-caption">{caption}</div>')
        return i

    def _stray_item(self, name, star, src, i, out):
        self._problem("\\item outside a list")
        _, i = self._opt(src, i)
        return i

    def _multicolumn(self, name, star, src, i, out):
        _, i = self._arg(src, i)
        _, i = self._arg(src, i)
        text, i = self._arg(src, i)
        out.add(self._conv(text or "", False))
        return i

    def _bibliography(self, name, star, src, i, out):
        _, i = self._arg(src, i)
        self._place_references(out)
        return i

    def _place_references(self, out: _Out) -> None:
        if self.bib_toc_index is None:
            self.bib_toc_index = len(self.toc)
            out.put(_BIB_MARK)

    # -- environments

    def _begin(self, name, star, src, i, out):
        env, i = self._arg(src, i)
        env = (env or "").strip()
        if env in MATH_ENVS or env in ("math", "displaymath"):
            m = re.compile(r"\\end\s*\{" + re.escape(env) + r"\}").search(src, i)
            if m is None:
                self._problem(f"missing \\end{{{env}}}")
            body, k = (src[i:], len(src)) if m is None else (src[i:m.start()], m.end())
            if env == "math":
                out.add(self._inline_math(body))
            elif env == "displaymath":
                self._display(body, out)
            else:
                tex = f"\\begin{{{env}}}{body}\\end{{{env}}}"
                self._scan_labels(tex)
                out.display(_esc(tex))
            return k
        pattern = re.compile(r"\\(begin|end)\s*\{" + re.escape(env) + r"\}")
        depth = 1
        for m in pattern.finditer(src, i):
            depth += 1 if m.group(1) == "begin" else -1
            if depth == 0:
                self._environment(env, src[i:m.start()], out)
                return m.end()
        self._problem(f"missing \\end{{{env}}}")
        self._environment(env, src[i:], out)
        return len(src)

    def _end(self, name, star, src, i, out):
        env, i = self._arg(src, i)
        env = (env or "").strip()
        if env == "document":
            return len(src)
        self._problem(f"\\end{{{env}}} without \\begin{{{env}}}")
        return i

    def _environment(self, env: str, body: str, out: _Out) -> None:
        if env in self.theorems:
            self._theorem(env, body, out)
        elif env == "proof":
            self._proof(body, out)
        elif env in ("itemize", "enumerate", "description"):
            self._list(env, body, out)
        elif env in ("table", "table*"):
            self._table(body, out)
        elif env in ("tabular", "tabular*", "tabularx"):
            self._tabular(env, body, out)
        elif env == "abstract":
            self.abstract = self._conv(body, True)
        elif env == "thebibliography":
            self._thebibliography(body, out)
        elif env == "center":
            out.put(f'<div class="ltx-center">{self._conv(body, True)}</div>')
        elif env in ("quote", "quotation"):
            out.put(f'<blockquote class="ltx-quote">{self._conv(body, True)}</blockquote>')
        else:
            if env not in ("flushleft", "flushright", "document"):
                self._problem(f"unsupported environment {env}")
            out.put(self._conv(body, out.block))

    def _theorem(self, env: str, body: str, out: _Out) -> None:
        heading, italic = self.theorems[env]
        opt, body = self._lead_opt(body)
        n = self.counts[env] = self.counts.get(env, 0) + 1
        anchor = self._unique_anchor(f"{env}-{n}")
        saved, self.target = self.target, _Target(anchor, str(n), f"{heading} {n}")
        self.card_scopes.append([])
        note = f" ({self._conv(opt, False).strip()})" if opt is not None else ""
        inner = self._conv(body, True)
        cards = self.card_scopes.pop()
        self.target = saved
        notes = [self._note(c) for c in dict.fromkeys(cards)]
        flags = "".join(f'<div class="ltx-flag">{_esc(t)}</div>' for t in dict.fromkeys(notes) if t)
        head = f'<span class="ltx-thm-head">{_esc(heading)} {n}{note}.</span> '
        cls = f"ltx-thm ltx-thm-{env}" + (" ltx-thm-it" if italic else "")
        out.put(f'<div class="{cls}" id="{anchor}">{flags}{_prepend(inner, head)}</div>')

    def _proof(self, body: str, out: _Out) -> None:
        opt, body = self._lead_opt(body)
        head = (self._conv(opt, False).strip() if opt is not None else "Proof") + "."
        inner = _prepend(self._conv(body, True), f'<span class="ltx-proof-head">{head}</span> ')
        qed = '<span class="ltx-qed">∎</span>'
        inner = inner[:-4] + qed + "</p>" if inner.endswith("</p>") else inner + f'<p class="ltx-qed-line">{qed}</p>'
        out.put(f'<div class="ltx-proof">{inner}</div>')

    def _list(self, env: str, body: str, out: _Out) -> None:
        _, body = self._lead_opt(body)   # enumitem options such as [(a)] are ignored
        pieces = _split_top(body, _ITEM)
        if pieces[0].strip():
            out.put(self._conv(pieces[0], out.block))
        items = []
        for piece in pieces[1:]:
            label, piece = self._lead_opt(piece)
            label = self._conv(label, False).strip() if label is not None else None
            items.append((label, self._conv(piece, True)))
        if env == "description":
            inner = "".join(f"<dt>{label or ''}</dt><dd>{_unwrap(content)}</dd>" for label, content in items)
            out.put(f'<dl class="ltx-list ltx-description">{inner}</dl>')
            return
        lis = []
        for label, content in items:
            if label is None:
                lis.append(f"<li>{_unwrap(content)}</li>")
            else:
                head = f'<span class="ltx-item-label">{label}</span> '
                lis.append(f'<li class="ltx-item-labelled">{_unwrap(_prepend(content, head))}</li>')
        tag = "ul" if env == "itemize" else "ol"
        out.put(f'<{tag} class="ltx-list">' + "".join(lis) + f"</{tag}>")

    def _table(self, body: str, out: _Out) -> None:
        _, body = self._lead_opt(body)   # placement such as [htbp]
        anchor, saved = "", self.target
        if re.search(r"\\caption(?![A-Za-z])", body):
            n = self.counts["table"] = self.counts.get("table", 0) + 1
            anchor = self._unique_anchor(f"table-{n}")
            self.target = _Target(anchor, str(n), f"Table {n}")
        self.captions.append([])
        inner = self._conv(body, True)
        captions = self.captions.pop()
        self.target = saved
        caption = ""
        if captions and anchor:
            caption = (f'<figcaption><span class="ltx-caption-head">Table {self.counts["table"]}.</span> '
                       f"{captions[0]}</figcaption>")
        ident = f' id="{anchor}"' if anchor else ""
        out.put(f'<figure class="ltx-table"{ident}>{caption}{inner}</figure>')

    def _tabular(self, env: str, body: str, out: _Out) -> None:
        _, body = self._lead_opt(body)
        if env != "tabular":
            _, j = _group_at(body, 0)   # the width of tabular* and tabularx
            body = body[j:]
        spec, j = _group_at(body, 0)
        aligns, body = _colspec(spec or ""), body[j:]
        rows, rules = [], []   # rows: (rule names before the row, raw cells)
        for chunk in _split_top(body, _ROW_END):
            while m := _RULE.match(chunk):
                rules.append(m.group(1) or m.group(2))
                chunk = chunk[m.end():]
            if chunk.strip():
                rows.append((rules, _split_top(chunk, _CELL_SEP)))
                rules = []
        header = len(rows) > 1 and any(r in ("midrule", "hline") for r in rows[1][0])
        thead = ""
        if header:
            thead = "<thead><tr>" + self._cells(rows[0][1], aligns, "th") + "</tr></thead>"
            rows = rows[1:]
        trs = []
        for k, (before, cells) in enumerate(rows):
            cls = ' class="ltx-rule"' if before and k > 0 else ""
            trs.append(f"<tr{cls}>" + self._cells(cells, aligns, "td") + "</tr>")
        out.put('<div class="ltx-tabular-wrap"><table class="ltx-tabular">'
                + thead + "<tbody>" + "".join(trs) + "</tbody></table></div>")

    def _cells(self, cells: list[str], aligns: list[str], tag: str) -> str:
        parts, col = [], 0
        for raw in cells:
            raw, span = raw.strip(), 1
            align = aligns[col] if col < len(aligns) else "l"
            m = re.match(r"\\multicolumn\s*\{\s*(\d+)\s*\}", raw)
            if m:
                spec, j = _group_at(raw, m.end())
                text, j = _group_at(raw, j)
                if text is not None:
                    span, raw = max(int(m.group(1)), 1), text + raw[j:]
                    align = (_colspec(spec or "") or ["c"])[0]
            colspan = f' colspan="{span}"' if span > 1 else ""
            parts.append(f'<{tag} class="ltx-al-{align}"{colspan}>{self._conv(raw, False).strip()}</{tag}>')
            col += span
        return "".join(parts)

    def _thebibliography(self, body: str, out: _Out) -> None:
        _, j = _group_at(body, 0)   # the widest label
        for piece in _split_top(body[j:], _BIBITEM)[1:]:
            _, piece = self._lead_opt(piece)
            key, j = _group_at(piece, 0)
            if key and key.strip():
                self.bibitems[key.strip()] = self._conv(piece[j:], False).strip()
        self._place_references(out)

    # -- assembling the result

    def _canonical(self, key: str) -> Optional[str]:
        """The bibliography key a citation key refers to, or None if it is unknown."""
        if self.bibitems:
            return key if key in self.bibitems else None
        return key if key in self.bib else self.bib_lower.get(key.lower())

    def _resolve(self, fragment: str) -> str:
        """Replace the placeholders of \\ref and \\cite now that every label is known."""
        fragment = fragment.replace(_BIB_MARK, "")   # a \bibliography in an odd place
        return _PLACEHOLDER.sub(lambda m: self._resolve_one(self.pending[int(m.group(1))]), fragment)

    def _resolve_one(self, item: tuple) -> str:
        if item[0] == "ref":
            _, cmd, key = item
            if key in self.math_labels:   # an equation: MathJax resolves it
                return _esc(f"\\{cmd}{{{key}}}")
            target = self.labels.get(key)
            if target is None:
                self._problem(f"undefined reference \\{cmd}{{{key}}}")
                return "??"
            link = (f'<a class="ltx-ref" href="#{_attr(target.anchor)}" title="{_attr(target.long)}">'
                    f"{_esc(target.number)}</a>")
            return f"({link})" if cmd == "eqref" else link
        _, keys, pre, post = item
        numbers = []
        for key in keys:
            n = self.cite_num.get(self._canonical(key) or "")
            if n is None:
                self._problem(f"unknown citation key {key}")
                numbers.append('<span class="ltx-cite-missing">?</span>')
            else:
                numbers.append(f'<a class="ltx-cite" href="#bib-{n}">{n}</a>')
        inner = ", ".join(numbers)
        inner = f"{pre} {inner}" if pre else inner
        inner = f"{inner}, {post}" if post else inner
        return f"[{inner}]"

    def _format_names(self, raw: str) -> str:
        """BibTeX authors ("Last, First and ...") as "First Last, ..., and First Last"."""
        names = [n.strip() for n in _split_top(raw, re.compile(r"\s+and\s+")) if n.strip()]
        others = bool(names) and names[-1].lower() == "others"
        shown = []
        for name in names[:-1] if others else names:
            parts = [p.strip() for p in _split_top(name, re.compile(","))]
            if len(parts) == 2:
                name = f"{parts[1]} {parts[0]}"
            elif len(parts) >= 3:
                name = f"{parts[2]} {parts[0]} {parts[1]}"
            shown.append(self._conv(name, False).strip())
        if not shown:
            return ""
        if len(shown) > 4:
            return shown[0] + " et al."
        if others:
            return ", ".join(shown) + " et al."
        if len(shown) <= 2:
            return " and ".join(shown)
        return ", ".join(shown[:-1]) + ", and " + shown[-1]

    def _format_entry(self, e: dict[str, str]) -> str:
        """One bibliography entry: authors, title, venue volume, pages (year). Links."""
        def field_html(name: str) -> str:
            return self._conv(e.get(name, ""), False).strip()

        title = field_html("title")
        if title and e.get("paperid") and self.paper_href:
            url = self.paper_href(e["paperid"].strip())
            if url:
                title = f'<a href="{_attr(url)}">{title}</a>'
        venue = next((field_html(k) for k in ("journal", "booktitle", "publisher", "school",
                                              "institution", "howpublished") if e.get(k)), "")
        volume = field_html("volume")
        pieces = [self._format_names(e.get("author") or e.get("editor") or ""),
                  f'<span class="ltx-bib-title">{title}</span>' if title else "",
                  (f"<em>{venue}</em>" + (f" <strong>{volume}</strong>" if volume else "")) if venue else "",
                  field_html("pages")]
        text = ", ".join(p for p in pieces if p)
        year = field_html("year")
        text += f" ({year})." if year else "."
        if e.get("note"):
            text += " " + field_html("note").rstrip(".") + "."
        links = []
        eprint = re.sub(r"^arxiv:", "", (e.get("eprint") or e.get("arxiv") or "").strip(), flags=re.I)
        prefix = (e.get("archiveprefix") or e.get("eprinttype") or "arxiv").strip().lower()
        if eprint and (prefix == "arxiv" or e.get("arxiv")):
            links.append(_link(f"https://arxiv.org/abs/{eprint}", _esc(f"arXiv:{eprint}")))
        doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", e.get("doi", "").strip(), flags=re.I)
        doi = doi.replace("\\_", "_")
        if doi:
            links.append(_link(f"https://doi.org/{doi}", _esc(f"doi:{doi}")))
        if e.get("url") and not links:
            url = e["url"].strip().replace("\\_", "_")
            links.append(_link(url, _esc(url)))
        return text + (" " + ", ".join(links) + "." if links else "")

    def _references(self) -> str:
        if not self.cite_num:
            return ""
        items = []
        for key, n in self.cite_num.items():
            text = self.bibitems[key] if self.bibitems else self._format_entry(self.bib[key])
            items.append(f'<li id="bib-{n}"><span class="ltx-bib-label">[{n}]</span> {text}</li>')
        return ('<section class="ltx-bibliography" id="references">\n'
                '<h2 class="ltx-section">References</h2>\n<ol class="ltx-bib">\n'
                + "\n".join(items) + "\n</ol>\n</section>")

    def _footnotes_section(self) -> str:
        if not self.footnotes:
            return ""
        items = "\n".join(f'<li id="fn-{n}">{text} <a class="ltx-fn-back" href="#fnref-{n}" '
                          f'aria-label="Back to the text">↩\ufe0e</a></li>'
                          for n, text in enumerate(self.footnotes, 1))
        return f'<section class="ltx-footnotes">\n<ol>\n{items}\n</ol>\n</section>'

    def run(self, tex: str) -> Rendered:
        tex = _COMMENT.sub(r"\1", tex.replace("\x00", "").replace("\r\n", "\n"))
        m = re.search(r"\\begin\s*\{document\}", tex)
        preamble, body = (tex[:m.start()], tex[m.end():]) if m else ("", tex)
        m = re.search(r"\\end\s*\{document\}", body)
        body = body[:m.start()] if m else body
        self._read_preamble(preamble)
        for name, raw in self.meta_src.items():
            self.meta[name] = self._convert_meta(raw)
        page = self._conv(body, True)

        order = (list(self.bibitems) if self.bibitems
                 else list(dict.fromkeys(k for k in map(self._canonical, self.cited) if k)))
        self.cite_num = {key: n for n, key in enumerate(order, 1)}
        references = self._references()
        tail = "\n".join(x for x in (self._footnotes_section(), references) if x)
        if references:
            entry = TocEntry(1, "", "References", "references")
            self.toc.insert(len(self.toc) if self.bib_toc_index is None else self.bib_toc_index, entry)
        if _BIB_MARK in page:
            page = page.replace(_BIB_MARK, tail, 1).replace(_BIB_MARK, "")
        elif tail:
            page += "\n" + tail
        if self.mathjax_defs:
            defs = "".join("\\(" + _esc(d.replace("\n", " ")) + "\\)" for d in self.mathjax_defs)
            page = f'<div class="ltx-macros" hidden>{defs}</div>\n' + page

        return Rendered(
            title=self._resolve(self.meta["title"]),
            authors=self._resolve(self.meta["author"]),
            date=self._resolve(self.meta["date"]),
            abstract=self._resolve(self.abstract),
            body=self._resolve(page).strip(),
            toc=[TocEntry(t.level, t.number, _strip_links(self._resolve(t.title)), t.anchor) for t in self.toc],
            cards=list(self.cards),
            problems=self.problems,
        )


def render(tex: str, *, bib: Optional[dict[str, dict[str, str]]] = None,
           card_href: Optional[Callable[[str], Optional[str]]] = None,
           card_note: Optional[Callable[[str], Optional[str]]] = None,
           paper_href: Optional[Callable[[str], Optional[str]]] = None) -> Rendered:
    r"""Convert a note or draft to HTML.

    bib: entries from parse_bib, for \cite. card_href(id) gives the URL of a card page,
    or None for no link. card_note(id) gives a plain-text warning about a card (shown at
    the top of a theorem-like block that names it), or None. paper_href(id) gives the
    URL of a paper card named by a bib entry's paperid field, or None.
    """
    converter = _Converter(bib, card_href, card_note, paper_href)
    try:
        return converter.run(tex or "")
    except Exception as exc:   # a bug in the converter or a callback: show the source
        return Rendered(body=f'<pre class="ltx-source">{_esc(tex or "")}</pre>',
                        problems=converter.problems + [f"converter error: {exc!r}"])


def document_html(r: Rendered) -> str:
    """Assemble a Rendered into one <article class="ltx-document">: the MathJax macros,
    title, authors, date, abstract and body, in that order."""
    body, macros = r.body, ""
    if body.startswith('<div class="ltx-macros"'):
        macros, _, body = body.partition("\n")
    parts = ['<article class="ltx-document">', macros]
    if r.title:
        parts.append(f'<h1 class="ltx-title">{r.title}</h1>')
    if r.authors:
        parts.append(f'<div class="ltx-authors">{r.authors}</div>')
    if r.date:
        parts.append(f'<div class="ltx-date">{r.date}</div>')
    if r.abstract:
        parts.append(f'<div class="ltx-abstract"><h6>Abstract</h6>\n{r.abstract}\n</div>')
    parts += [body, "</article>"]
    return "\n".join(p for p in parts if p)


# --------------------------------------------------------------------------- BibTeX

_ENTRY = re.compile(r"@\s*([A-Za-z]+)\s*([{(])")
_FIELD = re.compile(r"[\s,]*([A-Za-z][\w\-:.]*)\s*=\s*")
_BIB_ACCENT = re.compile(r"(\{)?\\(?:([`'^\"~=.])|([cvuHkrdb])(?![A-Za-z]))\s*"
                         r"(?:\{(\\[ij]|[A-Za-z])\}|(\\[ij](?![A-Za-z])|[A-Za-z]))(?(1)\})")
_BIB_LETTER = re.compile(r"\{\\(ss|o|O|ae|AE|oe|OE|aa|AA|l|L|i|j)\}|\\(ss|o|O|ae|AE|oe|OE|aa|AA|l|L)\{\}")
_PROTECT = re.compile(r"\{([^{}\\$]*)\}")
_ARGUMENT_BEFORE = re.compile(r"(\\[A-Za-z]+\s*|[\^_])$")   # text before a command's argument


def _entry_end(text: str, i: int, opener: str) -> int:
    """Index of the character that closes a BibTeX entry opened by { or ( before i."""
    closer, depth, quoted = ("}" if opener == "{" else ")"), 0, False
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == closer and depth == 0 and not quoted:
            return i
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(depth - 1, 0)
        elif c == '"' and depth == 0:
            quoted = not quoted
        i += 1
    return len(text)


def _bib_value(s: str, i: int) -> tuple[str, int]:
    """Read a field value: {braced}, "quoted" or a bare word, joined by #."""
    parts = []
    while i < len(s):
        if s[i] == "{":
            k = _match_brace(s, i)
            k = len(s) if k < 0 else k
            parts.append(s[i + 1:k])
            i = k + 1
        elif s[i] == '"':
            k, depth = i + 1, 0
            while k < len(s) and not (s[k] == '"' and depth == 0):
                if s[k] == "\\":
                    k += 1
                elif s[k] == "{":
                    depth += 1
                elif s[k] == "}":
                    depth -= 1
                k += 1
            parts.append(s[i + 1:k])
            i = k + 1
        else:
            m = re.compile(r"[^\s,#{}\"]+").match(s, i)
            if not m:
                break
            parts.append(m.group())
            i = m.end()
        m = re.compile(r"\s*#\s*").match(s, i)
        if not m:
            break
        i = m.end()
    return "".join(parts), i


def _clean_bib_value(value: str) -> str:
    r"""Collapse whitespace, turn accents ({\"o}, \'e, \c{c}) into Unicode and drop the
    braces that only protect capitals ({Monte Carlo}); command arguments keep theirs."""
    def accent(m: re.Match) -> str:
        char = _accent(m.group(2) or m.group(3), m.group(4) or m.group(5))
        is_argument = m.group(1) and _ARGUMENT_BEFORE.search(m.string, 0, m.start())
        return "{" + char + "}" if is_argument else char

    def unprotect(m: re.Match) -> str:
        return m.group(0) if _ARGUMENT_BEFORE.search(m.string, 0, m.start()) else m.group(1)

    value = re.sub(r"\s+", " ", value).strip()
    value = _BIB_LETTER.sub(lambda m: SYMBOLS[m.group(1) or m.group(2)], value)
    value = _BIB_ACCENT.sub(accent, value)
    previous = None
    while previous != value:
        previous, value = value, _PROTECT.sub(unprotect, value)
    return value


def parse_bib(text: str) -> dict[str, dict[str, str]]:
    r"""Parse a BibTeX file into {key: {field: value}}.

    Field names are lowercase; "entrytype" holds the entry type ("article", ...).
    @comment, @string and @preamble blocks are skipped (string macros are not expanded).
    Values have their outer braces or quotes removed and LaTeX accents turned into Unicode.
    Malformed entries are skipped or cut short; this function does not raise.
    """
    entries: dict[str, dict[str, str]] = {}
    pos = 0
    while m := _ENTRY.search(text or "", pos):
        kind, start = m.group(1).lower(), m.end()
        end = _entry_end(text, start, m.group(2))
        pos = end + 1
        if kind in ("comment", "string", "preamble"):
            continue
        key, _, rest = text[start:end].partition(",")
        if not key.strip():
            continue
        fields, i = {}, 0
        while f := _FIELD.match(rest, i):
            value, i = _bib_value(rest, f.end())
            fields[f.group(1).lower()] = _clean_bib_value(value)
        fields["entrytype"] = kind
        entries[key.strip()] = fields
    return entries
