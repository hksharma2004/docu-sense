"""PDF → canonical text, using PyMuPDF layout information.

Two layouts are handled:
  mono   – fixed-width pages (RFC .txt rendered to PDF): headings are numbered lines at column 0.
  styled – xml2rfc v3 PDFs: headings are bold lines, inline bold/links arrive as separate spans.
"""

import re
from collections import Counter
from dataclasses import dataclass

import pymupdf

from docusense.ingest.model import Block, Heading, ParsedDoc, TextBuilder
from docusense.ingest.normalize import normalize_line
from docusense.ingest.sections import HeadingMatch, match_heading_text

BASELINE_TOLERANCE = 2.0  # points; spans closer than this share a visual line
EDGE_LINES = 2            # lines at top/bottom of a page checked for running headers/footers
MONO_CHAR_WIDTH = 0.6     # em width of a fixed-width glyph


@dataclass
class RawLine:
    text: str
    page: int
    x0: float
    y: float  # baseline
    size: float
    bold: bool
    mono: bool
    indent: int = 0
    chars: int = 0


def _is_mono(font: str) -> bool:
    f = font.lower()
    return "mono" in f or "cour" in f


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def _page_lines(page: pymupdf.Page, pno: int) -> list[RawLine]:
    spans = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            if tuple(round(d) for d in line["dir"]) != (1, 0):
                continue
            spans.extend(s for s in line["spans"] if s["text"].strip())
    spans.sort(key=lambda s: (s["origin"][1], s["origin"][0]))

    clusters: list[list[dict]] = []
    for s in spans:
        if clusters and abs(s["origin"][1] - clusters[-1][0]["origin"][1]) <= BASELINE_TOLERANCE:
            clusters[-1].append(s)
        else:
            clusters.append([s])

    lines = []
    for cluster in clusters:
        cluster.sort(key=lambda s: s["bbox"][0])
        text, prev = "", None
        for s in cluster:
            if prev is not None:
                gap = s["bbox"][0] - prev["bbox"][2]
                if gap > 0.15 * s["size"] and not text.endswith(" ") and not s["text"].startswith(" "):
                    text += " "
            text += s["text"]
            prev = s
        dominant = max(cluster, key=lambda s: len(s["text"].strip()))
        lines.append(RawLine(
            text=text,
            page=pno,
            x0=cluster[0]["bbox"][0],
            y=cluster[0]["origin"][1],
            size=round(dominant["size"], 1),
            bold=all(_is_bold(s) for s in cluster),
            mono=_is_mono(dominant["font"]),
            chars=sum(len(s["text"].strip()) for s in cluster),
        ))
    return lines


def _strip_running_lines(pages: list[list[RawLine]]) -> list[list[RawLine]]:
    """Drop headers/footers: edge lines whose digit-masked text repeats on most pages."""

    def key(line: RawLine) -> str:
        return re.sub(r"\d+", "#", " ".join(line.text.split()))

    counts: Counter[str] = Counter()
    for lines in pages:
        counts.update({key(l) for l in lines[:EDGE_LINES] + lines[-EDGE_LINES:]})
    threshold = max(2, len(pages) // 2)
    running = {k for k, c in counts.items() if c >= threshold}

    out = []
    for lines in pages:
        edges = {id(l) for l in lines[:EDGE_LINES] + lines[-EDGE_LINES:]}
        out.append([l for l in lines if not (id(l) in edges and key(l) in running)])
    return out


def parse_pdf(data: bytes) -> ParsedDoc:
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        pages = [_page_lines(page, i + 1) for i, page in enumerate(pdf)]
    pages = _strip_running_lines(pages)
    all_lines = [l for lines in pages for l in lines]
    if not all_lines:
        return ParsedDoc(text="", page_starts=[0] * len(pages), layout="empty")

    mono_chars = sum(l.chars for l in all_lines if l.mono)
    layout = "mono" if mono_chars >= 0.8 * sum(l.chars for l in all_lines) else "styled"

    size_chars: Counter[float] = Counter()
    for l in all_lines:
        size_chars[l.size] += l.chars
    body_size = size_chars.most_common(1)[0][0]

    # Indentation (in characters) is kept only for fixed-width lines: it carries table/ABNF layout.
    def first_glyph_x(l: RawLine) -> float:
        return l.x0 + (len(l.text) - len(l.text.lstrip())) * l.size * MONO_CHAR_WIDTH

    body = [l for l in all_lines if (l.mono if layout == "mono" else not l.mono)] or all_lines
    left = min(first_glyph_x(l) if l.mono else l.x0 for l in body)
    for l in all_lines:
        if l.mono:
            l.indent = max(0, round((first_glyph_x(l) - left) / (l.size * MONO_CHAR_WIDTH)))
        l.text = normalize_line(l.text.strip())

    deltas = [
        b.y - a.y
        for lines in pages
        for a, b in zip(lines, lines[1:])
        if 0.5 * body_size < b.y - a.y < 3 * body_size
    ]
    # Line pitch = a low percentile of baseline gaps: robust even when blank lines are frequent.
    pitch = sorted(deltas)[len(deltas) // 5] if deltas else body_size * 1.2

    title = None
    builder = TextBuilder()
    page_starts: list[int] = []
    headings: list[Heading] = []
    blocks: list[Block] = []
    block_lines: list[tuple[int, int, str]] = []

    def flush_block() -> None:
        if block_lines:
            texts = [t for _, _, t in block_lines]
            blocks.append(Block(block_lines[0][0], block_lines[-1][1], _block_kind(texts)))
            block_lines.clear()

    prev: RawLine | None = None
    prev_heading = False
    for lines in pages:
        page_starts.append(builder.pos if builder.lines else 0)
        first_on_page = True
        for l in lines:
            if not l.text:
                continue
            if layout == "styled" and l.size >= 16 and l.bold:
                title = title or l.text  # document title block on page 1
            hm = _detect_heading(l, layout, body_size)

            continuation = (
                prev_heading and hm is None and layout == "styled" and l.bold
                and prev is not None and l.size == prev.size and 0 < l.y - prev.y <= 1.6 * pitch
            )
            if continuation:
                start, end = builder.add(l.text)
                headings[-1].end = end
                headings[-1].title += " " + l.text
                prev = l
                continue

            if prev is not None:
                if hm or prev_heading:
                    breaks = True
                elif first_on_page:
                    breaks = bool(re.search(r"[.:]$", prev.text)) and bool(re.match(r"[A-Z0-9\[(]", l.text))
                else:
                    breaks = l.y - prev.y > 1.45 * pitch
                if breaks:
                    flush_block()
                    builder.blank()
            if first_on_page:
                page_starts[-1] = builder.pos
                first_on_page = False

            line_text = " " * l.indent + l.text if l.mono else l.text
            start, end = builder.add(line_text)
            if hm:
                headings.append(Heading(hm.number, hm.title, hm.level, start, end))
            if not hm or hm.inline_body:
                block_lines.append((start, end, line_text))
            prev, prev_heading = l, hm is not None and not hm.inline_body
    flush_block()

    text = builder.build()
    return ParsedDoc(text, page_starts, headings, blocks, layout, title)


def _detect_heading(l: RawLine, layout: str, body_size: float) -> HeadingMatch | None:
    if layout == "mono":
        if l.indent != 0:
            return None
        return match_heading_text(l.text)
    if l.mono or not l.bold or l.size >= 16:
        return None
    hm = match_heading_text(l.text)
    if hm:
        return hm
    if l.size >= body_size + 1 and len(l.text) < 80:
        return HeadingMatch(None, l.text, 1)
    return None


_TABLE_RULE = re.compile(r"^\s*[+|][-=+|\s]*[+|]?\s*$")


def _block_kind(lines: list[str]) -> str:
    if len(lines) < 2:
        return "paragraph"
    ruled = sum(1 for t in lines if "|" in t or _TABLE_RULE.match(t))
    columns = sum(1 for t in lines if len(re.findall(r"\S\s{3,}\S", t.strip())) >= 2)
    if ruled >= len(lines) / 2 or columns >= max(2, 0.6 * len(lines)):
        return "table"
    return "paragraph"
