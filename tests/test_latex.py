"""Tests of space/latex.py, the converter from the LaTeX subset of notes and drafts to HTML.

The fixtures under tests/fixtures/latex are a real session note (S1 of a project on
walk-on-spheres methods for the Laplacian spectrum), a draft built from it, and a
bibliography with the keys they cite.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "space"))

import latex  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "latex"
REFUTED = "CL-S2-1 was refuted by DE-S5-1"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def text_of(fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", fragment)


@pytest.fixture(scope="module")
def bib():
    return latex.parse_bib(read("references.bib"))


@pytest.fixture(scope="module")
def note(bib):
    return latex.render(read("note-S1.tex"), bib=bib)


@pytest.fixture(scope="module")
def draft(bib):
    return latex.render(read("draft.tex"), bib=bib,
                        card_href=lambda c: f"/cards/{c}",
                        card_note=lambda c: REFUTED if c == "CL-S2-1" else None,
                        paper_href=lambda p: f"/papers/{p}")


# --------------------------------------------------------------------- the S1 note

def test_note_renders_without_problems(note):
    assert note.problems == []


def test_note_title_authors_abstract(note):
    assert note.title == "Walk methods for the Laplacian spectrum: what the literature allows"
    assert note.authors == "Note on session S1, 22 October 2026"
    assert note.abstract.startswith("<p>Walk-on-spheres estimators of the Helmholtz equation \\(\\Delta u+k^2u=0\\)")
    assert "Abstract" not in note.body and "Walk-on-spheres estimators" not in note.body


def test_note_sections_are_numbered_after_the_starred_setting(note):
    assert [(t.level, t.number) for t in note.toc] == [(1, "")] + [(1, str(n)) for n in range(1, 7)] + [(1, "")]
    assert note.toc[0].title == "Setting" and note.toc[0].anchor == "sec-setting"
    assert note.toc[1].title == "Helmholtz by walks stops at the first eigenvalue"
    assert note.toc[-1].title == "References" and note.toc[-1].anchor == "references"
    assert '<h2 class="ltx-section" id="sec-setting">Setting</h2>' in note.body
    assert '<h2 class="ltx-section" id="sec-3"><span class="ltx-num">3</span> Several eigenvalues' in note.body


def test_note_equations_pass_through_with_their_labels(note):
    blocks = re.findall(r'<div class="ltx-eq">(.*?)</div>', note.body, re.S)
    assert len(blocks) == 5
    assert blocks[0] == ("\\begin{equation}\nu(x)=\\mathbb E_x\\!\\left[e^{k^2\\tau}\\,g(X_\\tau)\\right].\n"
                         "\\label{eq:fk}\n\\end{equation}")
    assert "\\(\\mathbb P_x(\\tau&gt;t)\\sim c\\,e^{-\\lambda_1 t}\\)" in note.body


def test_note_eqref_is_left_for_mathjax_and_ref_is_resolved(note):
    assert "Walk on spheres applies \\eqref{eq:fk} with one weight" in note.body
    assert "the weights&nbsp;\\eqref{eq:weights} by sampling" in note.body
    assert ('the barrier of Section&nbsp;<a class="ltx-ref" href="#sec-1" title="Section 1">1</a>'
            in note.body)
    assert 'extraction of Section&nbsp;<a class="ltx-ref" href="#sec-3" title="Section 3">3</a>' in note.body


def test_note_citations_are_numbered_by_first_use(note):
    assert 'Dirichlet route works&nbsp;[<a class="ltx-cite" href="#bib-1">1</a>]' in note.body
    assert ('used in&nbsp;[<a class="ltx-cite" href="#bib-2">2</a>, <a class="ltx-cite" href="#bib-3">3</a>]'
            in note.body)
    entries = re.findall(r'<li id="bib-(\d+)"><span class="ltx-bib-label">\[\d+\]</span> (.*?)</li>', note.body)
    assert [int(n) for n, _ in entries] == list(range(1, 17))
    assert entries[0][1].startswith("Rohan Sawhney, Bailey Miller, Ioannis Gkioulekas, and Keenan Crane, ")
    assert text_of(entries[11][1]).startswith("T. E. Booth and J. E. Gubernatis, Monte Carlo Determination")
    assert "<strong>80</strong>, 046704 (2009)." in entries[11][1]
    assert '<a class="ltx-link" href="https://arxiv.org/abs/0812.4854"' in entries[11][1]
    assert '<a class="ltx-link" href="https://doi.org/10.1103/PhysRevE.80.046704"' in entries[11][1]
    assert note.body.index("<h2 class=\"ltx-section\">References</h2>") > note.body.index("Open question")


def test_note_footnote(note):
    marker = re.search(r'<sup class="ltx-fn" id="fnref-1"><a href="#fn-1">1</a>'
                       r'<span class="ltx-fn-text" hidden>(.*?)</span></sup>', note.body)
    assert marker and marker.group(1).startswith("The 3D form is the continuation of \\(\\sqrt{s}")
    assert '[<a class="ltx-cite" href="#bib-2">2</a>]' in marker.group(1)
    footnotes = re.search(r'<section class="ltx-footnotes">(.*?)</section>', note.body, re.S).group(1)
    assert '<li id="fn-1">The 3D form' in footnotes and 'href="#fnref-1"' in footnotes
    assert note.body.index('class="ltx-footnotes"') < note.body.index('class="ltx-bibliography"')


def test_note_text_details(note):
    assert "“the response at \\(x_0\\)” has to mean" in note.body
    assert "to about 0.4% with" in note.body and "Feynman–Kac" in note.body
    assert note.body.count("<li>") == 5 and '<ul class="ltx-list">' in note.body


# ------------------------------------------------------------------------ the draft

def test_draft_renders_without_problems(draft):
    assert draft.problems == []


def test_draft_result_is_numbered_with_its_title(draft):
    assert ('<div class="ltx-thm ltx-thm-result ltx-thm-it ltx-has-card" id="result-1">' in draft.body)
    assert '<span class="ltx-thm-head">Result 1 (Per-ball weights).</span> Started at' in draft.body


def test_draft_cards_link_through_the_callback(draft):
    assert draft.cards == ["CL-S2-1", "D-S2-1", "C-S2-1"]
    assert (f'<a class="ltx-card ltx-card-flagged" title="{REFUTED}" href="/cards/CL-S2-1">CL-S2-1</a>'
            in draft.body)
    assert 'derivation&nbsp;<a class="ltx-card" href="/cards/D-S2-1">D-S2-1</a>' in draft.body


def test_draft_card_note_flags_the_result(draft):
    result = re.search(r'id="result-1">(.*?)</div>', draft.body, re.S).group(1)
    assert result == f'<div class="ltx-flag">{REFUTED}'
    assert draft.body.count("ltx-flag") == 1


def test_blocks_list_the_cards_they_name_and_take_a_footer_per_card():
    tex = (r"\begin{result}A.\card{CL-S1-1}\footnote{See \card{CL-S1-2}.}\end{result}"
           r"\begin{remark}No card.\end{remark}\begin{conjecture}B.\card{CL-S1-1}\end{conjecture}")
    r = latex.render(tex, card_footer=lambda c: f"<i>{c}</i>" if c == "CL-S1-1" else None)
    assert [(b.kind, b.number, b.anchor, b.cards) for b in r.blocks] == [
        ("result", "1", "result-1", ["CL-S1-1", "CL-S1-2"]), ("remark", "1", "remark-1", []),
        ("conjecture", "1", "conjecture-1", ["CL-S1-1"])]
    assert r.body.count('<div class="ltx-thm-foot"><i>CL-S1-1</i></div></div>') == 2
    assert '<div class="ltx-thm ltx-thm-remark" id="remark-1">' in r.body
    assert "ltx-thm-foot" not in latex.render(tex).body


def test_draft_subsections_and_appendix(draft):
    numbers = [t.number for t in draft.toc]
    assert numbers == ["1", "2", "2.1", "2.2", "3", "4", "A", "B", ""]
    assert [t.level for t in draft.toc][:4] == [1, 1, 2, 2]
    assert '<h2 class="ltx-section" id="sec-A"><span class="ltx-num">Appendix A</span> Proof of Result 1</h2>' in draft.body
    assert '(Appendix&nbsp;<a class="ltx-ref" href="#sec-A" title="Appendix A">A</a>)' in draft.body
    assert 'Section&nbsp;<a class="ltx-ref" href="#sec-2.1" title="Section 2.1">2.1</a>' in draft.body


def test_draft_table_has_a_numbered_caption_and_a_header_row(draft):
    table = re.search(r'<figure class="ltx-table" id="table-1">(.*?)</figure>', draft.body, re.S).group(1)
    assert table.startswith('<figcaption><span class="ltx-caption-head">Table 1.</span> First six Dirichlet')
    assert "\\([0,\\sqrt2]\\times[0,1]\\)" in table
    assert re.findall(r"<th\b[^>]*>(.*?)</th>", table) == ["\\(n\\)", "rectangle", "disk"]
    assert table.count("<tr>") == 7 and '<td class="ltx-al-c">83.892</td>' in table
    assert 'lowest levels of Table&nbsp;<a class="ltx-ref" href="#table-1" title="Table 1">1</a>' in draft.body


def test_draft_bibliography_links_paper_cards(draft):
    assert '<span class="ltx-bib-title"><a href="/papers/P-1512.07725">Walk on Spheres' in draft.body
    assert "Benoit Blossier et al.," in draft.body


# ---------------------------------------------------------------------- the subset

def test_escaping_in_text_math_and_attributes():
    r = latex.render("\\title{<b>T</b>}\nText <script>alert(1)</script> & co, $a<b & c>d$, "
                     "\\href{javascript:alert(1)}{click} \\card{X\" onclick=\"y}\\footnote{<i>n</i>}"
                     "\\label{a\"b} \\ref{a\"b}",
                     card_href=lambda c: '"><script>x</script>')
    html = r.title + r.body
    assert "<script" not in html and "<b>" not in html and "<i>" not in html
    assert "Text &lt;script&gt;alert(1)&lt;/script&gt; &amp; co, \\(a&lt;b &amp; c&gt;d\\)" in r.body
    assert "javascript" not in r.body and "click" in r.body
    assert 'href="&quot;&gt;&lt;script&gt;x&lt;/script&gt;"' in r.body
    assert '>X" onclick="y</a>' in r.body


def test_comments_are_removed_but_percent_is_kept():
    r = latex.render("Done at 50\\% % a comment\nsame paragraph\n% a comment line\nstill the same\n%\n\nnew one\\\\%c\nend")
    assert r.body == "<p>Done at 50% same paragraph\nstill the same</p>\n<p>new one<br>end</p>"


def test_typography_and_accents():
    r = latex.render("``Quoted'' it's -- and --- \\'ecole {\\\"o} \\c{c}a \\v{s} \\^o \\~n \\`a \\$5 a~b \\LaTeX{} \\ldots")
    assert r.body == "<p>“Quoted” it’s – and — école ö ça š ô ñ à $5 a&nbsp;b LaTeX …</p>"


def test_styles_and_links():
    r = latex.render("\\emph{e} \\textbf{b} \\texttt{a--b} \\textsc{s} {\\bf w} \\url{https://x.org/a\\_b} "
                     "\\href{mailto:a@b.c}{mail} \\href{ftp://x}{ftp}")
    assert ("<em>e</em> <strong>b</strong> <code>a--b</code> <span class=\"ltx-sc\">s</span> <strong>w</strong> "
            '<a class="ltx-link" href="https://x.org/a_b" rel="noopener" target="_blank">https://x.org/a_b</a> '
            '<a class="ltx-link" href="mailto:a@b.c" rel="noopener" target="_blank">mail</a> ftp') in r.body


def test_unknown_commands_and_environments_are_reported_once():
    r = latex.render("\\includegraphics[width=3cm]{fig.png} \\foo{bar} \\foo \\begin{weird}inside\\end{weird}")
    assert r.problems == ["unsupported command \\includegraphics", "unsupported command \\foo",
                          "unsupported environment weird"]
    assert "fig.png" in r.body and "bar" in r.body and "inside" in r.body


@pytest.mark.parametrize("tex", [
    "Unbalanced {brace and \\emph{unclosed\n\nnext",
    "\\begin{itemize}\n\\item one\n\\item two",
    "stray } and \\end{foo} and $x and $$y",
    "\\begin{equation} x = 1",
    "\\begin{tabular}{cc} a & b \\\\ c",
    "\\section{\\footnote{",
    "\\cite{",
    "trailing backslash \\",
    "{" * 3000,
    "\\newcommand{\\a}{\\a\\a}\\a",
    "\\begin{table}\\caption{x}\\label{t}\\begin{tabular}{c}\\multicolumn{2}{",
])
def test_malformed_input_does_not_raise(tex):
    r = latex.render(tex)
    assert r.problems and not any(p.startswith("converter error") for p in r.problems)


def test_missing_end_itemize_renders_the_items():
    r = latex.render("\\begin{itemize}\n\\item one\n\\item two\n")
    assert r.body == '<ul class="ltx-list"><li>one</li><li>two</li></ul>'
    assert r.problems == ["missing \\end{itemize}"]


def test_lists():
    r = latex.render("\\begin{enumerate}\\item A \\begin{itemize}\\item[$\\star$] B\\end{itemize}\\item C\\end{enumerate}"
                     "\\begin{description}\\item[Term] Meaning.\\end{description}")
    assert ('<ol class="ltx-list"><li><p>A</p>\n<ul class="ltx-list"><li class="ltx-item-labelled">'
            '<span class="ltx-item-label">\\(\\star\\)</span> B</li></ul></li><li>C</li></ol>') in r.body
    assert '<dl class="ltx-list ltx-description"><dt>Term</dt><dd>Meaning.</dd></dl>' in r.body


def test_booktabs_table_with_multicolumn():
    r = latex.render("\\begin{tabular}{l|r@{.}l}\\toprule\nName & \\multicolumn{2}{c}{Value} \\\\\n\\midrule\n"
                     "x & 1 & 5 \\\\\ny & $\\begin{pmatrix}a&b\\end{pmatrix}$ & {c & d} \\\\ \\hline\nz & 3 & 0\\\\\n"
                     "\\bottomrule\\end{tabular}")
    assert ('<thead><tr><th class="ltx-al-l">Name</th><th class="ltx-al-c" colspan="2">Value</th></tr></thead>'
            in r.body)
    assert '<td class="ltx-al-r">\\(\\begin{pmatrix}a&amp;b\\end{pmatrix}\\)</td><td class="ltx-al-l">c &amp; d</td>' in r.body
    assert '<tr class="ltx-rule"><td class="ltx-al-l">z</td>' in r.body
    assert r.problems == []


def test_theorem_kinds_proof_and_references():
    r = latex.render("\\section{S}\\begin{theorem}[Main]\\label{thm:a}T.\\end{theorem}\n"
                     "\\begin{lemma}L.\\end{lemma}\\begin{definition}D.\\end{definition}\\begin{remark}R.\\end{remark}"
                     "\\begin{theorem}U.\\end{theorem}\\begin{proof}Easy.\\end{proof}"
                     "\\begin{proof}[Proof of Theorem~\\ref{thm:a}]\\[x\\]\\end{proof}"
                     "By \\ref{thm:a}, \\ref{eq:z} and \\eqref{eq:z}, see \\ref{later}."
                     "\\begin{align}a&=b\\label{eq:z}\\end{align}\\subsection{T}\\label{later}")
    assert '<div class="ltx-thm ltx-thm-theorem ltx-thm-it" id="theorem-1"><p><span class="ltx-thm-head">Theorem 1 (Main).</span> T.</p></div>' in r.body
    assert 'id="theorem-2"><p><span class="ltx-thm-head">Theorem 2.</span>' in r.body
    assert '<div class="ltx-thm ltx-thm-lemma ltx-thm-it" id="lemma-1">' in r.body
    assert '<div class="ltx-thm ltx-thm-definition" id="definition-1">' in r.body
    assert '<div class="ltx-thm ltx-thm-remark" id="remark-1">' in r.body
    assert '<p><span class="ltx-proof-head">Proof.</span> Easy.<span class="ltx-qed">∎</span></p>' in r.body
    assert '<span class="ltx-proof-head">Proof of Theorem&nbsp;<a class="ltx-ref" href="#theorem-1"' in r.body
    assert '<p class="ltx-qed-line"><span class="ltx-qed">∎</span></p>' in r.body
    assert 'By <a class="ltx-ref" href="#theorem-1" title="Theorem 1">1</a>, \\ref{eq:z} and \\eqref{eq:z}' in r.body
    assert 'see <a class="ltx-ref" href="#sec-1.1" title="Section 1.1">1.1</a>.' in r.body
    assert '<div class="ltx-eq">\\begin{align}a&amp;=b\\label{eq:z}\\end{align}</div>' in r.body
    assert r.problems == []


def test_unknown_reference_and_citation_key():
    r = latex.render("See \\ref{nope} and \\cite{a,missing}.", bib={"a": {"title": "A"}})
    assert 'See ?? and [<a class="ltx-cite" href="#bib-1">1</a>, <span class="ltx-cite-missing">?</span>].' in r.body
    assert r.problems == ["undefined reference \\ref{nope}", "unknown citation key missing"]


def test_citation_forms_and_thebibliography():
    r = latex.render("See~\\cite[p.~3]{b} and \\citep[see][Ch.~2]{a,b}.\n"
                     "\\begin{thebibliography}{9}\n\\bibitem{a} A. Author, \\emph{Book}, 2001.\n"
                     "\\bibitem[B]{b} B. Author, Paper.\n\\end{thebibliography}")
    assert 'See&nbsp;[<a class="ltx-cite" href="#bib-2">2</a>, p.&nbsp;3]' in r.body
    assert '[see <a class="ltx-cite" href="#bib-1">1</a>, <a class="ltx-cite" href="#bib-2">2</a>, Ch.&nbsp;2]' in r.body
    assert '<li id="bib-1"><span class="ltx-bib-label">[1]</span> A. Author, <em>Book</em>, 2001.</li>' in r.body
    assert r.toc[-1].title == "References" and r.problems == []


def test_references_go_at_the_end_without_bibliography_command():
    r = latex.render("Text~\\cite{k}.\n\\section{Last}", bib={"k": {"author": "Doe, Jane", "title": "T", "year": "2020"}})
    assert r.body.endswith('<li id="bib-1"><span class="ltx-bib-label">[1]</span> Jane Doe, '
                           '<span class="ltx-bib-title">T</span> (2020).</li>\n</ol>\n</section>')
    assert [t.title for t in r.toc] == ["Last", "References"]


def test_macros_go_to_mathjax_and_expand_in_text():
    r = latex.render("\\newcommand{\\R}{\\mathbb{R}}\n\\newcommand{\\todo}[1]{\\textbf{TODO: #1}}\n"
                     "\\newcommand{\\pair}[2][x]{(#1, #2)}\\DeclareMathOperator{\\Tr}{Tr}\n"
                     "\\providecommand{\\card}[1]{#1}\n\\title{On $\\R^n$}\\begin{document}\n"
                     "$\\Tr \\R$, \\todo{fix \\emph{it}}, \\pair{y}, \\pair[z]{w}, \\card{CL-S1-1}.\n\\end{document}")
    assert r.body.startswith('<div class="ltx-macros" hidden>\\(\\newcommand{\\R}{\\mathbb{R}}\\)'
                             '\\(\\newcommand{\\todo}[1]{\\textbf{TODO: #1}}\\)'
                             '\\(\\newcommand{\\pair}[2][x]{(#1, #2)}\\)\\(\\DeclareMathOperator{\\Tr}{Tr}\\)</div>')
    assert ('<p>\\(\\Tr \\R\\), <strong>TODO: fix <em>it</em></strong>, (x, y), (z, w), '
            '<code class="ltx-card">CL-S1-1</code>.</p>') in r.body
    page = latex.document_html(r)
    assert page.index("ltx-macros") < page.index('<h1 class="ltx-title">On \\(\\R^n\\)</h1>')
    assert r.problems == []


def test_card_note_outside_a_theorem_marks_only_the_tag():
    r = latex.render("Claim\\card{A,B}.\\begin{conjecture}Maybe\\card{B}.\\end{conjecture}",
                     card_note=lambda c: f"{c} is stale" if c == "B" else None)
    assert r.cards == ["A", "B"]
    assert '<code class="ltx-card">A</code> <code class="ltx-card ltx-card-flagged" title="B is stale">B</code>' in r.body
    assert '<div class="ltx-thm ltx-thm-conjecture ltx-thm-it ltx-has-card" id="conjecture-1"><div class="ltx-flag">B is stale</div>' in r.body
    assert r.body.count("ltx-flag\"") == 1


def test_heading_footnote_and_label_stay_out_of_the_toc():
    r = latex.render("\\section{Intro\\footnote{Note \\cite{k}.}\\label{s}}See \\ref{s}.", bib={"k": {"title": "K"}})
    assert r.toc[0].title == "Intro"
    assert re.search(r'<h2 class="ltx-section" id="sec-1"><span class="ltx-num">1</span> Intro<sup class="ltx-fn"', r.body)
    assert 'See <a class="ltx-ref" href="#sec-1"' in r.body


def test_no_document_environment_means_the_whole_input_is_the_body():
    r = latex.render("\\title{T}\\author{A \\and B}\\date{2026}Hello.")
    assert (r.title, r.authors, r.date, r.body) == ("T", "A, B", "2026", "<p>Hello.</p>")


# ------------------------------------------------------------------------- parse_bib

def test_parse_bib_fixture(bib):
    assert len(bib) == 18 and "fake" not in bib and "pre" not in bib
    booth = bib["booth2008"]
    assert booth["entrytype"] == "article" and booth["title"] == "Monte Carlo Determination of Multiple Extremal Eigenpairs"
    assert booth["author"] == "Booth, T. E. and Gubernatis, J. E." and booth["paperid"] == "P-0812.4854"
    assert bib["blossier2009"]["year"] == "2009"
    assert bib["bernal2023"]["title"].startswith("An iterative method for Helmholtz boundary")
    assert bib["bernal2023"]["author"].endswith("dos Reis, Gonçalo")
    assert bib["cimpean2026"]["author"].startswith("Cîmpean, Iulian")
    assert "Hołyst" in bib["burdzy1996"]["author"]
    assert "Schrödinger's equation" in bib["donsker1950"]["title"]
    assert bib["ceperley1988"]["url"] == "https://pubs.aip.org/aip/jcp/article/89/10/6316/"


def test_parse_bib_edge_cases():
    bib = latex.parse_bib('@Article{K1, Title = "A {B} \\emph{c} $x^{12}$" # " end", Note = {\\\'e and {\\\'E}}}\n'
                          "@misc{K2, title = {unclosed")
    assert bib["K1"]["title"] == "A B \\emph{c} $x^{12}$ end"
    assert bib["K1"]["note"] == "é and É"
    assert bib["K2"]["title"] == "unclosed"
    assert latex.parse_bib("") == {} and latex.parse_bib("@") == {}
