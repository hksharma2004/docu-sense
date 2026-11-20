"""docx and html -> markdown, deterministic, stdlib only.

the markdown becomes the canonical text (span offsets point into it) and `verify --deep`
re-runs this on the stored original, so output must depend only on input bytes.
"""

import re
import zipfile
from collections import Counter
from html.parser import HTMLParser
from io import BytesIO
from xml.etree import ElementTree as ET

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_HEADING_STYLE = re.compile(r"^heading\s*(\d)$", re.I)


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def _table_md(rows: list[list[str]]) -> list[str]:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(_cell(c) for c in rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows[1:]]
    return out


# ── docx ─────────────────────────────────────────────────────────────────────

def _docx_text(el: ET.Element) -> str:
    parts = []
    for node in el.iter():
        if node.tag == _W + "t" and node.text:
            parts.append(node.text)
        elif node.tag in (_W + "tab",):
            parts.append(" ")
        elif node.tag in (_W + "br", _W + "cr"):
            parts.append(" ")
    return " ".join("".join(parts).split())


def docx_to_markdown(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            document = ET.fromstring(z.read("word/document.xml"))
            styles = ET.fromstring(z.read("word/styles.xml")) if "word/styles.xml" in z.namelist() else None
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError(f"not a valid .docx file: {e}") from e

    style_names: dict[str, str] = {}
    if styles is not None:
        for st in styles.iter(_W + "style"):
            sid, name = st.get(_W + "styleId"), st.find(_W + "name")
            if sid and name is not None:
                style_names[sid] = (name.get(_W + "val") or sid).lower()

    body = document.find(_W + "body")
    if body is None:
        return ""

    # pass 1: collect paragraphs/tables plus the formatting hints used to spot headings
    items: list[dict] = []
    size_chars: Counter = Counter()
    for child in body:
        if child.tag == _W + "p":
            text = _docx_text(child)
            if not text:
                continue
            ppr = child.find(_W + "pPr")
            style = ""
            if ppr is not None and (ps := ppr.find(_W + "pStyle")) is not None:
                sid = ps.get(_W + "val") or ""
                style = style_names.get(sid, sid.lower())
            bold, sizes = _run_format(child)
            for sz, n in sizes.items():
                size_chars[sz] += n
            bullet = _BULLET.match(text)
            items.append({"kind": "p", "text": _BULLET.sub("", text) if bullet else text, "style": style,
                          "list": (ppr is not None and ppr.find(_W + "numPr") is not None)
                                  or style.startswith("list") or bool(bullet),
                          "bold": bold, "size": max(sizes, key=sizes.get) if sizes else None})
        elif child.tag == _W + "tbl":
            rows = [[_docx_text(tc) for tc in tr.iter(_W + "tc")] for tr in child.iter(_W + "tr")]
            items.append({"kind": "table", "rows": rows})

    body_size = size_chars.most_common(1)[0][0] if size_chars else None

    def formatted_heading(it: dict) -> bool:
        """direct-formatting heading: short, no sentence end, bold or clearly bigger than body"""
        t = it["text"]
        if it["list"] or it["style"] or len(t) > 120 or t.endswith((".", ";", ",")) or len(t.split()) > 14:
            return False
        bigger = body_size is not None and it["size"] is not None and it["size"] >= body_size * 1.15
        return bigger or it["bold"]

    styled = any(_HEADING_STYLE.match(_norm_style(it.get("style", ""))) for it in items if it["kind"] == "p")
    candidates = [it for it in items if it["kind"] == "p" and not styled and formatted_heading(it)]
    heading_sizes = sorted({it["size"] or 0 for it in candidates}, reverse=True)

    # title: an explicit title style, or a leading heading in the single largest size
    first_p = next((it for it in items if it["kind"] == "p"), None)
    title_item = next((it for it in items if it["kind"] == "p" and it["style"] == "title"), None)
    if title_item is None and first_p in candidates and heading_sizes and (first_p["size"] or 0) == heading_sizes[0] \
            and sum((c["size"] or 0) == heading_sizes[0] for c in candidates) == 1:
        title_item = first_p
        heading_sizes = heading_sizes[1:]
    shift = 1 if title_item is not None else 0

    # pass 2: emit markdown
    blocks: list[str] = []
    for it in items:
        if it["kind"] == "table":
            table = _table_md(it["rows"])
            if table:
                blocks.append("\n".join(table))
            continue
        text = it["text"]
        if it is title_item:
            blocks.append("# " + text)
        elif m := _HEADING_STYLE.match(_norm_style(it["style"])):
            blocks.append("#" * min(int(m.group(1)) + shift, 6) + " " + text)
        elif it in candidates:
            rank = heading_sizes.index(it["size"] or 0) + 1 if (it["size"] or 0) in heading_sizes else len(heading_sizes) + 1
            blocks.append("#" * min(rank + shift, 6) + " " + text)
        elif it["list"]:
            if blocks and blocks[-1].startswith("- "):
                blocks[-1] += "\n- " + text  # keep consecutive items in one list block
            else:
                blocks.append("- " + text)
        else:
            blocks.append(text)
    return "\n\n".join(blocks) + "\n"


def _norm_style(style: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"heading\s*", "heading ", style or "")).strip()


_BULLET = re.compile(r"^\s*[•◦▪‣·\-–]\s+")


def _on(el: ET.Element | None) -> bool:
    return el is not None and (el.get(_W + "val") or "true").lower() not in ("0", "false", "off", "none")


def _run_format(p: ET.Element) -> tuple[bool, Counter]:
    """(all runs bold, Counter of half-point size -> chars)"""
    all_bold, any_text, sizes = True, False, Counter()
    for r in p.iter(_W + "r"):
        text = "".join(t.text or "" for t in r.iter(_W + "t")).strip()
        if not text or _BULLET.fullmatch(text + " "):
            continue
        any_text = True
        rpr = r.find(_W + "rPr")
        if not (rpr is not None and _on(rpr.find(_W + "b"))):
            all_bold = False
        sz = rpr.find(_W + "sz") if rpr is not None else None
        if sz is not None and (v := sz.get(_W + "val", "")).isdigit():
            sizes[int(v)] += len(text)
    return any_text and all_bold, sizes


# ── html ─────────────────────────────────────────────────────────────────────

_SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "head", "form", "button", "iframe"}
_BLOCK = {"p", "div", "section", "article", "main", "aside", "header", "blockquote", "figure", "figcaption",
          "dd", "dt", "address", "details", "summary", "body", "html"}


class _HtmlToMd(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.buf: list[str] = []
        self.skip = 0
        self.heading: int | None = None
        self.list_items: list[str] | None = None
        self.in_li = False
        self.pre = 0
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.title: str | None = None
        self.in_title = False

    def _flush(self) -> None:
        text = "".join(self.buf)
        self.buf = []
        if self.pre:
            return
        text = " ".join(text.split())
        if not text:
            return
        if self.heading is not None:
            self.blocks.append("#" * self.heading + " " + text)
        else:
            self.blocks.append(text)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag == "table":
            self._flush()
            self.table = []
        elif self.table is not None:
            return
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading = int(tag[1])
        elif tag in ("ul", "ol"):
            self._flush()
            if self.list_items is None:
                self.list_items = []
        elif tag == "li":
            self._flush_li()
            self.in_li = True
        elif tag == "pre":
            self._flush()
            self.pre += 1
        elif tag == "br":
            self.buf.append(" ")
        elif tag in _BLOCK:
            if not self.in_li:
                self._flush()

    def _flush_li(self) -> None:
        if self.in_li and self.list_items is not None:
            text = " ".join("".join(self.buf).split())
            self.buf = []
            if text:
                self.list_items.append("- " + text)
        self.in_li = False

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            md = _table_md(self.table)
            if md:
                self.blocks.append("\n".join(md))
            self.table = None
        elif self.table is not None:
            return
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.heading = None
        elif tag == "li":
            self._flush_li()
        elif tag in ("ul", "ol"):
            self._flush_li()
            if self.list_items:
                self.blocks.append("\n".join(self.list_items))
            self.list_items = None
        elif tag == "pre":
            code = "".join(self.buf).strip("\n")
            self.buf = []
            self.pre = max(0, self.pre - 1)
            if code.strip():
                self.blocks.append("```\n" + code + "\n```")
        elif tag in _BLOCK and not self.in_li:
            self._flush()

    def handle_data(self, data):
        if self.in_title:
            self.title = (self.title or "") + data
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.table is None:
            self.buf.append(data)


def html_to_markdown(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    parser = _HtmlToMd()
    parser.feed(text)
    parser.close()
    parser._flush_li()
    parser._flush()
    blocks = parser.blocks
    if not any(b.startswith("# ") for b in blocks) and parser.title and parser.title.strip():
        blocks = ["# " + " ".join(parser.title.split())] + blocks
    return "\n\n".join(blocks) + "\n"
