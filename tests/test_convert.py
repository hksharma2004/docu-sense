"""docx / html -> markdown, plus end-to-end ingest + verify for both"""

import zipfile
from io import BytesIO

from docusense.ingest.convert import docx_to_markdown, html_to_markdown
from docusense.ingest.pipeline import ingest_version, parse_source
from docusense.provenance import Verifier

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _p(text, style=None, numbered=False):
    ppr = ""
    if style or numbered:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + \
              ("<w:numPr><w:ilvl w:val=\"0\"/><w:numId w:val=\"1\"/></w:numPr>" if numbered else "") + "</w:pPr>"
    return f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"


def make_docx(body: str) -> bytes:
    styles = (f'<w:styles {W}>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>'
              '</w:styles>')
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {W}><w:body>{body}</w:body></w:document>")
        z.writestr("word/styles.xml", styles)
    return buf.getvalue()


DOCX = make_docx(
    _p("Travel Policy", "Title")
    + _p("1. Hotels", "Heading1")
    + _p("Employees must not book hotels above $150 per night.")
    + _p("Receipts are required.", numbered=True) + _p("Use the corporate card.", numbered=True)
    + _p("Exceptions", "Heading2")
    + _p("The CFO may approve exceptions in writing.")
    + "<w:tbl><w:tr><w:tc>" + _p("City") + "</w:tc><w:tc>" + _p("Cap") + "</w:tc></w:tr>"
    + "<w:tr><w:tc>" + _p("London") + "</w:tc><w:tc>" + _p("£200") + "</w:tc></w:tr></w:tbl>"
)

HTML = b"""<!doctype html><html><head><title>Leave Policy</title><style>p{}</style></head>
<body><nav>Home | About</nav><main>
<h1>Leave Policy</h1>
<h2>1. Annual leave</h2>
<p>Employees are entitled to <b>24 days</b> of paid leave.</p>
<ul><li>Carry over is capped at 5 days.</li><li>Requests need manager approval.</li></ul>
<table><tr><th>Tenure</th><th>Days</th></tr><tr><td>5+ years</td><td>28</td></tr></table>
<pre>code   block</pre>
<script>alert(1)</script>
</main><footer>(c) 2026</footer></body></html>"""


def test_docx_to_markdown():
    md = docx_to_markdown(DOCX)
    assert md.startswith("# Travel Policy\n\n## 1. Hotels\n\nEmployees must not book hotels above $150 per night.")
    assert "- Receipts are required.\n- Use the corporate card." in md
    assert "### Exceptions" in md
    assert "| City | Cap |\n|---|---|\n| London | £200 |" in md


def test_html_to_markdown():
    md = html_to_markdown(HTML)
    assert md.startswith("# Leave Policy\n\n## 1. Annual leave\n\nEmployees are entitled to 24 days of paid leave.")
    assert "- Carry over is capped at 5 days.\n- Requests need manager approval." in md
    assert "| Tenure | Days |" in md and "```\ncode   block\n```" in md
    assert "alert" not in md and "Home | About" not in md and "(c) 2026" not in md


def test_conversion_is_deterministic():
    assert parse_source("docx", DOCX).data == parse_source("docx", DOCX).data
    assert parse_source("html", HTML).data == parse_source("html", HTML).data


def test_ingest_and_deep_verify(conn, store, tmp_path):
    (tmp_path / "travel.docx").write_bytes(DOCX)
    (tmp_path / "leave.html").write_bytes(HTML)
    r1 = ingest_version(conn, document_id="travel", title="Travel", family="user", label="v1", seq=1,
                        path=tmp_path / "travel.docx", store=store)
    r2 = ingest_version(conn, document_id="leave", title="Leave", family="user", label="v1", seq=1,
                        path=tmp_path / "leave.html", store=store)
    assert r1.status == r2.status == "ingested" and r1.layout == "docx" and r2.layout == "html"
    sections = [r["title"] for r in conn.execute("SELECT title FROM sections WHERE version_id = 'travel@v1' ORDER BY ordinal")]
    assert "Hotels" in sections and "Exceptions" in sections
    report = Verifier(conn, store).verify_all(deep=True)
    assert report["total"] > 0 and report["verified"] == report["total"]


def _run(text, size=24, bold=False):
    rpr = f'<w:rPr>{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/></w:rPr>'
    return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def test_docx_headings_from_direct_formatting():
    """real docs often fake headings with bold / bigger fonts instead of heading styles"""
    md = docx_to_markdown(make_docx(
        _run("Expense Policy", 48, True) + _run("1. Meals", 36, True)
        + _run("Employees must not claim more than $60 per day.")
        + _run("Approval", 24, True) + _run("Managers approve claims within 5 business days.")
        + _run("2. Travel", 36, True) + _run("This bold sentence ends with a period.", 24, True)
    ))
    assert md.split("\n\n")[:5] == ["# Expense Policy", "## 1. Meals", "Employees must not claim more than $60 per day.",
                                    "### Approval", "Managers approve claims within 5 business days."]
    assert "## 2. Travel" in md and "\n\nThis bold sentence ends with a period.\n" in md
