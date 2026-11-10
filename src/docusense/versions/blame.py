"""Span blame: which version first introduced a piece of text, and how it evolved."""

from difflib import SequenceMatcher

import psycopg

from docusense.extract.sentences import flatten

FUZZY_MATCH = 0.9


def _best_match(conn: psycopg.Connection, version_id: str, target: str, kind: str) -> tuple[dict | None, float]:
    kinds = ["sentence"] if kind == "sentence" else ["paragraph", "table", "code"]
    rows = conn.execute(
        """SELECT p.id, p.text, p.start_byte, p.end_byte, s.number, s.title FROM spans p
           LEFT JOIN sections s ON s.id = p.section_id WHERE p.version_id = %s AND p.kind = ANY(%s)""",
        (version_id, kinds),
    ).fetchall()
    best, best_score = None, 0.0
    for r in rows:
        flat = flatten(r["text"])
        if flat == target:
            return r, 1.0
        m = SequenceMatcher(None, target, flat, autojunk=False)
        if m.real_quick_ratio() <= best_score or m.quick_ratio() <= best_score:
            continue
        score = m.ratio()
        if score > best_score:
            best, best_score = r, score
    return best, best_score


def blame(conn: psycopg.Connection, span_id: int) -> dict:
    span = conn.execute(
        """SELECT p.id, p.kind, p.text, p.version_id, v.document_id, v.seq
           FROM spans p JOIN versions v ON v.id = p.version_id WHERE p.id = %s""",
        (span_id,),
    ).fetchone()
    if span is None:
        raise ValueError(f"no span {span_id}")
    target = flatten(span["text"])
    versions = conn.execute(
        "SELECT id, label, seq FROM versions WHERE document_id = %s ORDER BY seq", (span["document_id"],)
    ).fetchall()

    history = []
    for v in versions:
        if v["id"] == span["version_id"]:
            match, score = span, 1.0
        else:
            match, score = _best_match(conn, v["id"], target, span["kind"])
        status = "identical" if score == 1.0 else "similar" if score >= FUZZY_MATCH else "absent"
        entry = {"version": v["id"], "status": status, "similarity": round(score, 3)}
        if match is not None and status != "absent":
            entry["span_id"] = match["id"]
            entry["text"] = flatten(match["text"])[:400]
        history.append(entry)
    # introduced_in = start of the most recent unbroken run of presence up to this span's version
    run_start = None
    for entry in history:
        if entry["status"] == "absent":
            run_start = None
        elif run_start is None:
            run_start = entry["version"]
        if entry["version"] == span["version_id"]:
            break
    return {"span_id": span_id, "version": span["version_id"], "text": target[:400],
            "introduced_in": run_start, "history": history}
