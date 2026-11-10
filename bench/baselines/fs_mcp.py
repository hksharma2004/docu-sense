"""Baseline 1 — raw filesystem MCP: list_files, grep, read_file over the canonical .txt files."""

import re
from pathlib import Path

from mcp.server import MCPServer

TEXTS = Path(__file__).resolve().parents[1] / "work" / "texts"
server = MCPServer("fs-baseline", instructions="Plain text files, one per document version (e.g. smtp@rfc5321.txt).")


def _path(name: str) -> Path:
    p = (TEXTS / name).resolve()
    if p.parent != TEXTS.resolve() or not p.exists():
        raise ValueError(f"no such file {name!r}; call list_files")
    return p


@server.tool()
def list_files() -> list[dict]:
    """List the available text files with their size in lines."""
    return [{"file": p.name, "lines": p.read_text().count("\n")} for p in sorted(TEXTS.glob("*.txt"))]


@server.tool()
def grep(pattern: str, file: str | None = None, max_matches: int = 30) -> list[dict]:
    """Case-insensitive regex search. Returns file, line number and the matching line."""
    rx = re.compile(pattern, re.I)
    out = []
    for p in [_path(file)] if file else sorted(TEXTS.glob("*.txt")):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if rx.search(line):
                out.append({"file": p.name, "line": n, "text": line.strip()})
                if len(out) >= max_matches:
                    return out
    return out


@server.tool()
def read_file(file: str, offset: int = 1, limit: int = 80) -> dict:
    """Read `limit` lines (max 200) of a file starting at line `offset` (1-based)."""
    lines = _path(file).read_text().splitlines()
    limit = max(1, min(limit, 200))
    return {"file": file, "offset": offset, "lines": lines[offset - 1: offset - 1 + limit], "total_lines": len(lines)}


if __name__ == "__main__":
    server.run()
