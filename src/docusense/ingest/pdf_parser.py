"""PDF → canonical text, using PyMuPDF layout information.

Two layouts are handled:
  mono   – fixed-width pages (RFC .txt rendered to PDF): headings are numbered lines at column 0.
  styled – proportional fonts (xml2rfc v3, papers, reports): headings are bold or larger lines, inline
           bold/links arrive as separate spans.

Multi-column pages (newsletters, government publications, papers) are read column by column: text
blocks are grouped into vertical bands, and full-width blocks (titles, wide tables) split the page into
horizontal segments. Single-column pages take exactly the original whole-page path, so canonical text
for previously ingested single-column documents is unchanged.
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
MARGIN = 0.07             # top/bottom fraction of the page where fuzzy running lines may sit


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
    region_start: bool = False  # first line of a new column / segment (reading order jumps)
    rel_y: float = 0.5          # baseline as a fraction of page height


def _is_mono(font: str) -> bool:
    f = font.lower()
    return "mono" in f or "cour" in f


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def _block_spans(block: dict) -> list[dict]:
    out = []
    for line in block["lines"]:
        if tuple(round(d) for d in line["dir"]) != (1, 0):
            continue
        out.extend(s for s in line["spans"] if s["text"].strip())
    return out


def _regions(page: pymupdf.Page) -> list[list[dict]]:
    """Spans grouped into reading-order regions: one region for single-column pages, else one per
    column band within each horizontal segment (segments are separated by full-width blocks)."""
    blocks = [b for b in page.get_text("dict")["blocks"] if b.get("type") == 0]
    blocks = [(b, sp) for b in blocks if (sp := _block_spans(b))]
    everything = [s for _, sp in blocks for s in sp]
    width = page.rect.width
    if not blocks or width <= 0:
        return [everything]

    # Column bands: narrow blocks clustered by left edge (column paragraphs share x0; stray table cells
    # rarely reach 200 characters). Bands that overlap horizontally are merged (indented lists, quotes).
    narrow = [(b, sp) for b, sp in blocks if b["bbox"][2] - b["bbox"][0] < 0.48 * width]
    clusters: list[dict] = []
    for b, sp in sorted(narrow, key=lambda item: item[0]["bbox"][0]):
        x0, x1 = b["bbox"][0], b["bbox"][2]
        n = sum(len(s["text"].strip()) for s in sp)
        if clusters and x0 - clusters[-1]["x0"] <= 10:
            clusters[-1]["edges"].append((x1, n))
            clusters[-1]["chars"] += n
        else:
            clusters.append({"x0": x0, "edges": [(x1, n)], "chars": n})

    def right_edge(edges: list[tuple[float, int]]) -> float:
        """Character-weighted median right edge: table rows sharing the column's left edge can't stretch it."""
        total, acc = sum(n for _, n in edges), 0
        for x1, n in sorted(edges):
            acc += n
            if acc * 2 >= total:
                return x1
        return edges[-1][0]

    real: list[list[float]] = []
    for c in clusters:
        if c["chars"] < 200:
            continue
        x1 = right_edge(c["edges"])
        if real and c["x0"] <= real[-1][1]:
            real[-1][1] = max(real[-1][1], x1)
        else:
            real.append([c["x0"], x1])
    if len(real) < 2:
        return [everything]  # single column: original behaviour

    def band_of(b: dict) -> int | None:
        hits = [i for i, band in enumerate(real) if b["bbox"][0] < band[1] and b["bbox"][2] > band[0]]
        return hits[0] if len(hits) == 1 else None  # spans several bands → full width

    wide = sorted((b for b, _ in blocks if band_of(b) is None), key=lambda b: b["bbox"][1])
    cuts = [b["bbox"][1] for b in wide] + [float("inf")]
    regions: list[list[dict]] = []
    top = float("-inf")
    for cut, wide_block in zip(cuts, wide + [None]):
        for i in range(len(real)):
            col = [s for b, sp in blocks if band_of(b) == i and top <= b["bbox"][1] < cut for s in sp]
            if col:
                regions.append(col)
        if wide_block is not None:
            regions.append(_block_spans(wide_block))
            top = wide_block["bbox"][1]
    return regions


def _page_lines(page: pymupdf.Page, pno: int) -> list[RawLine]:
    lines: list[RawLine] = []
    height = page.rect.height or 1.0
    for n, spans in enumerate(_regions(page)):
        region = _region_lines(spans, pno)
        if region and n:
            region[0].region_start = True
        for l in region:
            l.rel_y = l.y / height
        lines.extend(region)
    return lines


def _region_lines(spans: list[dict], pno: int) -> list[RawLine]:
    spans = sorted(spans, key=lambda s: (s["origin"][1], s["origin"][0]))

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
    """Drop headers/footers: short edge lines that recur (digit-masked, fuzzily) on many pages.

    Exact repeats on half the pages catch RFC-style headers. Fuzzy repeats (≥ 75% of the shorter line's tokens shared) on
    80% of the pages of one parity catch book layouts whose footers alternate sides or embed the
    chapter name ("4 Chapter 1 Travel Publication 463 (2025)").
    """

    def key(line: RawLine) -> str:
        return re.sub(r"\d+", "#", " ".join(line.text.split()))

    def edge_lines(lines: list[RawLine]) -> list[RawLine]:
        # Geometric edges (top/bottom baselines): in column layouts a footer may sit inside a column.
        by_y = sorted(lines, key=lambda l: l.y)
        return by_y[:EDGE_LINES] + by_y[-EDGE_LINES:]

    edges_by_page = [edge_lines(lines) for lines in pages]
    counts: Counter[str] = Counter()
    for edges in edges_by_page:
        counts.update({key(l) for l in edges})
    threshold = max(2, len(pages) // 2)
    running = {k for k, c in counts.items() if c >= threshold}

    if len(pages) >= 6:
        # Only lines with ≥ 3 tokens: short ones ("#", "1 Introduction") match too easily.
        # Fuzzy matching is limited to the page margins, so templated body lines are never dropped.
        margin = {key(l) for edges in edges_by_page for l in edges if l.rel_y < MARGIN or l.rel_y > 1 - MARGIN}
        tokens = {k: t for k in counts if k in margin and len(k) <= 100 and len(t := frozenset(k.lower().split())) >= 3}
        for parity in (0, 1):
            page_keys = [{key(l) for l in edges} & tokens.keys() for edges in edges_by_page[parity::2]]
            need = max(3, int(0.8 * len(page_keys)))
            for k in {k for keys in page_keys for k in keys} - running:
                t = tokens[k]
                support = sum(
                    any(len(t & tokens[o]) / min(len(t), len(tokens[o])) >= 0.75 for o in keys) for keys in page_keys
                )
                if support >= need:
                    running.add(k)

    out = []
    for lines, page_edges in zip(pages, edges_by_page):
        edges = {id(l) for l in page_edges}
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
                elif first_on_page or l.region_start:
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
