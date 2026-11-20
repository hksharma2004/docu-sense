"""render a paginated rfc .txt into a fixed-width pdf, one rfc page per pdf page.

older rfcs only ship as .txt; this matches the layout datatracker serves as pdf.
output is byte-for-byte deterministic (fixed metadata, no random file id).
"""

import pymupdf

FONT_SIZE = 10
LINE_HEIGHT = 12
MARGIN_X = 54
MARGIN_Y = 40
FIXED_DATE = "D:20000101000000Z"


def render_txt_pdf(txt: str, title: str) -> bytes:
    pages = txt.replace("\r\n", "\n").split("\f")
    pdf = pymupdf.open()
    for page_text in pages:
        lines = page_text.strip("\n").split("\n")
        if not any(line.strip() for line in lines):
            continue
        height = max(792, 2 * MARGIN_Y + len(lines) * LINE_HEIGHT)
        page = pdf.new_page(width=612, height=height)
        for i, line in enumerate(lines):
            if line.strip():
                page.insert_text(
                    (MARGIN_X, MARGIN_Y + (i + 1) * LINE_HEIGHT),
                    line.expandtabs(8),
                    fontname="cour",
                    fontsize=FONT_SIZE,
                )
    pdf.set_metadata({
        "title": title,
        "producer": "docusense-render/0.1",
        "creator": "docusense-render/0.1",
        "creationDate": FIXED_DATE,
        "modDate": FIXED_DATE,
    })
    data = pdf.tobytes(garbage=4, deflate=True, no_new_id=True)
    pdf.close()
    return data
