from docusense.ingest.md_parser import parse_markdown
from docusense.ingest.pdf_parser import parse_pdf
from docusense.ingest.render import render_txt_pdf
from docusense.ingest.sections import build_sections

PAGE_1 = """\
Network Working Group                                          A. Author
Request for Comments: 9999                                     Example
Category: Informational                                     January 2026


                         A Small Test Protocol

Abstract

   This memo describes a small protocol used only for testing.

1.  Introduction

   The client MUST send a greeting.  The greeting is 5 octets long and
   ends with CRLF.

   A second paragraph follows here.




Author                        Informational                     [Page 1]
"""

PAGE_2 = """\
RFC 9999                  A Small Test Protocol             January 2026


1.1.  Terminology

   Greeting: the first line sent by a client.

   +--------+-------+
   | Field  | Size  |
   +--------+-------+
   | hello  | 5     |
   +--------+-------+

   The greeting is sent once per
   connection.




Author                        Informational                     [Page 2]
"""

PAGE_3 = """\
RFC 9999                  A Small Test Protocol             January 2026


Appendix A.  Examples

   An example exchange is shown in Section 1.




Author                        Informational                     [Page 3]
"""

RFC_TXT = PAGE_1 + "\f\n" + PAGE_2 + "\f\n" + PAGE_3


def _slices_match(doc):
    data = doc.data
    for b in doc.blocks:
        chunk = data[b.start:b.end].decode()
        assert chunk == chunk.strip("\n") and chunk.strip()


def test_render_is_deterministic():
    assert render_txt_pdf(RFC_TXT, "t") == render_txt_pdf(RFC_TXT, "t")


def test_pdf_mono_parse():
    doc = parse_pdf(render_txt_pdf(RFC_TXT, "RFC 9999"))
    assert doc.layout == "mono"
    assert len(doc.page_starts) == 3
    assert "[Page" not in doc.text and "RFC 9999                  A Small" not in doc.text

    numbers = [s["number"] for s in build_sections(doc)]
    assert numbers == [None, None, "1", "1.1", "A"]  # front matter, Abstract, 1, 1.1, Appendix A

    kinds = [b.kind for b in doc.blocks]
    assert "table" in kinds
    _slices_match(doc)

    greeting = next(b for b in doc.blocks if b"MUST send" in doc.data[b.start:b.end])
    assert doc.page_of(greeting.start) == 1
    terminology = next(b for b in doc.blocks if b"Greeting:" in doc.data[b.start:b.end])
    assert doc.page_of(terminology.start) == 2


def test_pdf_preserves_indentation_for_tables():
    doc = parse_pdf(render_txt_pdf(RFC_TXT, "RFC 9999"))
    table = next(b for b in doc.blocks if b.kind == "table")
    assert doc.data[table.start:table.end].decode().startswith("   +--------+")


MD = """# Policy Title

> intro note

## 1. Scope

Applies to **everything**.

## 2. Limits

### 2.1 Size

Lines MUST NOT exceed 1000 octets.

| a | b |
|---|---|
| 1 | 2 |
"""


def test_markdown_parse():
    doc = parse_markdown(MD.encode())
    assert doc.title == "Policy Title"
    sections = build_sections(doc)
    assert [(s["number"], s["title"], s["level"]) for s in sections] == [
        (None, "Front Matter", 0), ("1", "Scope", 1), ("2", "Limits", 1), ("2.1", "Size", 2),
    ]
    assert sections[3]["parent_ordinal"] == 2
    _slices_match(doc)
    texts = [doc.data[b.start:b.end].decode() for b in doc.blocks]
    assert "Lines MUST NOT exceed 1000 octets." in texts
    assert any(b.kind == "table" for b in doc.blocks)
