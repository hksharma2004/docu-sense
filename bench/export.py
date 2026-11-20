"""export each version's canonical text and section map for the baselines and scorer.

    uv run python -m bench.export   -> bench/work/texts/<version_id>.txt, bench/work/sections.json
"""

import json
from pathlib import Path

from docusense.db.conn import connect
from docusense.store.blobs import BlobStore

WORK = Path(__file__).resolve().parent / "work"
TEXTS = WORK / "texts"


def export() -> int:
    TEXTS.mkdir(parents=True, exist_ok=True)
    store, sections = BlobStore(), {}
    with connect() as conn:
        versions = conn.execute("SELECT id, text_sha256 FROM versions ORDER BY id").fetchall()
        for v in versions:
            (TEXTS / f"{v['id']}.txt").write_bytes(store.get(v["text_sha256"]))
            sections[v["id"]] = [
                [s["start_byte"], s["end_byte"], s["number"], s["title"]]
                for s in conn.execute("SELECT start_byte, end_byte, number, title FROM sections "
                                      "WHERE version_id = %s ORDER BY ordinal", (v["id"],))
            ]
    (WORK / "sections.json").write_text(json.dumps(sections))
    return len(versions)


if __name__ == "__main__":
    print(f"exported {export()} versions to {TEXTS}")
