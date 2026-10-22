"""Parser output shared by the PDF and Markdown paths.

All offsets are byte offsets into the UTF-8 encoded canonical text. Pages are 1-indexed.
"""

from bisect import bisect_right
from dataclasses import dataclass, field


@dataclass
class Heading:
    number: str | None
    title: str
    level: int
    start: int
    end: int


@dataclass
class Block:
    start: int
    end: int
    kind: str  # paragraph | table | code


@dataclass
class ParsedDoc:
    text: str
    page_starts: list[int]
    headings: list[Heading] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    layout: str = ""  # mono | styled | markdown
    title: str | None = None

    @property
    def data(self) -> bytes:
        return self.text.encode("utf-8")

    def page_of(self, offset: int) -> int:
        return max(1, bisect_right(self.page_starts, offset))


class TextBuilder:
    """Builds canonical text line by line, tracking byte offsets as it goes."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.pos = 0

    def add(self, line: str) -> tuple[int, int]:
        start = self.pos
        end = start + len(line.encode("utf-8"))
        self.lines.append(line)
        self.pos = end + 1  # the joining "\n"
        return start, end

    def blank(self) -> None:
        if self.lines and self.lines[-1] != "":
            self.add("")

    def build(self) -> str:
        lines = self.lines
        while lines and lines[-1] == "":
            lines = lines[:-1]
        return "\n".join(lines) + "\n"
