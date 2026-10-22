"""Markdown → canonical text. The canonical text is the normalised file itself, so offsets map 1:1."""

from markdown_it import MarkdownIt

from docusense.ingest.model import Block, Heading, ParsedDoc
from docusense.ingest.normalize import normalize_text
from docusense.ingest.sections import match_heading_text

_BLOCK_KINDS = {
    "paragraph_open": "paragraph",
    "bullet_list_open": "paragraph",
    "ordered_list_open": "paragraph",
    "blockquote_open": "paragraph",
    "table_open": "table",
    "fence": "code",
    "code_block": "code",
}


def parse_markdown(data: bytes) -> ParsedDoc:
    text = normalize_text(data.decode("utf-8")).rstrip("\n") + "\n"
    lines = text.split("\n")
    line_starts, pos = [], 0
    for line in lines:
        line_starts.append(pos)
        pos += len(line.encode("utf-8")) + 1

    def span(first: int, last_exclusive: int) -> tuple[int, int]:
        last = last_exclusive - 1
        return line_starts[first], line_starts[last] + len(lines[last].encode("utf-8"))

    tokens = MarkdownIt("commonmark").enable("table").parse(text)
    h1_count = sum(1 for t in tokens if t.type == "heading_open" and t.tag == "h1")

    title, headings, blocks = None, [], []
    for i, tok in enumerate(tokens):
        if tok.map is None or tok.level != 0:
            continue
        if tok.type == "heading_open":
            depth = int(tok.tag[1])
            content = tokens[i + 1].content.strip()
            if depth == 1 and h1_count == 1:
                title = content  # single H1 = document title, part of front matter
                continue
            start, end = span(*tok.map)
            hm = match_heading_text(content)
            number = hm.number if hm and hm.number else None
            heading_title = hm.title if number else content
            level = depth - 1 if h1_count == 1 else depth
            headings.append(Heading(number, heading_title, level, start, end))
        elif tok.type in _BLOCK_KINDS:
            start, end = span(*tok.map)
            if end > start:
                blocks.append(Block(start, end, _BLOCK_KINDS[tok.type]))

    return ParsedDoc(text, [0], headings, blocks, "markdown", title)
