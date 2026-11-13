"""Build dist/docusense.mcpb — a one-click Claude Desktop extension (MCP Bundle, server type "uv").

    uv run python scripts/build_mcpb.py            # stage, validate and pack with the official mcpb CLI

The bundle carries only tracked source (src/, pyproject.toml, uv.lock, README, LICENSE) — never .env, the
store, the corpus or the viewer. On first launch the host runs `uv run`, which installs dependencies from
uv.lock into the bundle folder (a minute or two: PyMuPDF, ONNX runtime); later launches are instant.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "dist" / "mcpb"
OUT = ROOT / "dist" / "docusense.mcpb"
MCPB_CLI = "@anthropic-ai/mcpb@2.1.2"
INCLUDE = ["pyproject.toml", "uv.lock", "README.md", "LICENSE", "src"]


def version() -> str:
    return re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", *INCLUDE], cwd=ROOT, check=True, capture_output=True, text=True)
    return [f for f in out.stdout.splitlines() if f]


MANIFEST = {
    "manifest_version": "0.4",
    "name": "docusense",
    "display_name": "DocuSense",
    "version": None,  # filled from pyproject.toml
    "description": "Verifiable, versioned document memory for Claude: every answer cites byte ranges with a SHA-256.",
    "long_description": (
        "Add PDFs, Word, HTML and Markdown files. DocuSense splits them into sections and passages, hashes "
        "every passage, keeps every version of a file, and gives Claude tools to search, read, verify citations, "
        "diff versions and surface contradictions. Everything stays on your machine (~/.docusense)."
    ),
    "author": {"name": "Harsh Kumar Sharma"},
    "license": "MIT",
    "icon": "icon.png",
    "keywords": ["documents", "citations", "rag", "pdf", "versioning", "provenance"],
    "server": {
        "type": "uv",
        "entry_point": "src/docusense/mcp_server.py",
        "mcp_config": {
            "command": "uv",
            "args": ["run", "--directory", "${__dirname}", "--no-dev", "--frozen", "--quiet",
                     "docusense", "serve-mcp"],
            "env": {
                "DOCUSENSE_ADD_ROOTS": "${user_config.documents_folder}",
                "DOCUSENSE_TOOLS": "${user_config.tool_set}",
            },
        },
    },
    "user_config": {
        "documents_folder": {
            "type": "directory",
            "title": "Documents folder",
            "description": "Folder Claude may add documents from (add_document). Leave empty to allow your home folder.",
            "required": False,
            "default": "${HOME}",
        },
        "tool_set": {
            "type": "string",
            "title": "Tool set",
            "description": "'all' (17 tools) or 'core' (11 tools, smaller context).",
            "required": False,
            "default": "all",
        },
    },
    "compatibility": {"platforms": ["darwin", "linux", "win32"], "runtimes": {"python": ">=3.12"}},
}


def make_icon(path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=256, height=256)
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(0, 0, 256, 256), radius=0.18)
    shape.finish(color=None, fill=(0.11, 0.16, 0.27))
    shape.draw_rect(pymupdf.Rect(60, 44, 196, 212), radius=0.08)  # page
    shape.finish(color=None, fill=(0.96, 0.97, 0.99))
    for i, w in enumerate((96, 80, 96, 60)):  # text lines
        y = 78 + i * 22
        shape.draw_line((80, y), (80 + w, y))
    shape.finish(color=(0.55, 0.6, 0.7), width=7, lineCap=1)
    shape.draw_circle((180, 182), 38)  # verified badge
    shape.finish(color=None, fill=(0.13, 0.65, 0.42))
    shape.draw_polyline([(162, 182), (176, 196), (200, 168)])
    shape.finish(color=(1, 1, 1), width=10, lineCap=1, lineJoin=1, closePath=False)
    shape.commit()
    page.get_pixmap(dpi=144).save(str(path))  # 512×512


def main() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    files = tracked_files()
    for rel in files:
        dest = STAGE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    assert not any(Path(f).name == ".env" for f in files)

    manifest = dict(MANIFEST, version=version())
    (STAGE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (STAGE / ".mcpbignore").write_text(".venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n")
    make_icon(STAGE / "icon.png")

    npx = ["npx", "-y", MCPB_CLI]
    subprocess.run([*npx, "validate", str(STAGE / "manifest.json")], check=True)
    OUT.unlink(missing_ok=True)
    subprocess.run([*npx, "pack", str(STAGE), str(OUT)], check=True)
    print(f"\nbuilt {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB, {len(files)} source files)", file=sys.stderr)


if __name__ == "__main__":
    main()
