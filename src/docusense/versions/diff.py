"""version diffs at section, claim and reference level"""

from difflib import SequenceMatcher

from docusense.db.conn import Database

from docusense.extract.sentences import flatten, split_sentences

TITLE_MATCH = 0.8        # title similarity needed to align sections with different numbers
TITLE_MATCH_SAME_NUM = 0.5
CLAIM_MATCH = 0.5        # topic-term Jaccard needed to pair two claims as "changed"


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower(), autojunk=False).ratio()


def _label(s: dict) -> str:
    return " ".join(x for x in (s["number"], s["title"]) if x)


def _sections(conn: Database, version_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT id, number, title, level, ordinal FROM sections
           WHERE version_id = %s ORDER BY ordinal""",
        (version_id,),
    ).fetchall()
    bodies: dict[int, list[str]] = {}
    for p in conn.execute(
        """SELECT section_id, text FROM spans WHERE version_id = %s AND kind <> 'sentence'
           AND section_id IS NOT NULL ORDER BY ordinal""",
        (version_id,),
    ):
        bodies.setdefault(p["section_id"], []).append(p["text"])
    for r in rows:
        r["body"] = "\n\n".join(bodies.get(r["id"], []))
        r["flat"] = flatten(r["body"])
    return rows


def _align(old: list[dict], new: list[dict]) -> list[tuple[dict | None, dict | None]]:
    """greedy best-first alignment on title similarity, boosted when numbers match"""
    candidates = []
    for o in old:
        for n in new:
            t = _ratio(o["title"], n["title"])
            same_num = o["number"] is not None and o["number"] == n["number"]
            if t >= TITLE_MATCH or (same_num and t >= TITLE_MATCH_SAME_NUM):
                candidates.append((t + (0.25 if same_num else 0.0), o["id"], n["id"]))
    candidates.sort(reverse=True)
    old_by_id, new_by_id = {o["id"]: o for o in old}, {n["id"]: n for n in new}
    used_old, used_new, pairs = set(), set(), {}
    for score, oid, nid in candidates:
        if oid not in used_old and nid not in used_new:
            used_old.add(oid)
            used_new.add(nid)
            pairs[nid] = oid

    out: list[tuple[dict | None, dict | None]] = []
    removed = [o for o in old if o["id"] not in used_old]
    for n in new:
        oid = pairs.get(n["id"])
        if oid is not None:
            o = old_by_id[oid]
            # emit removed sections that came before this one in the old order
            while removed and removed[0]["ordinal"] < o["ordinal"]:
                out.append((removed.pop(0), None))
            out.append((o, n))
        else:
            out.append((None, n))
    out.extend((o, None) for o in removed)
    return out


def _sentence_changes(old_text: str, new_text: str, limit: int) -> dict:
    old_s = [flatten(s.text) for s in split_sentences(old_text)]
    new_s = [flatten(s.text) for s in split_sentences(new_text)]
    old_set, new_set = set(old_s), set(new_s)
    return {
        "removed": [s for s in old_s if s not in new_set][:limit],
        "added": [s for s in new_s if s not in old_set][:limit],
    }


def diff_sections(conn: Database, old_vid: str, new_vid: str, sentence_limit: int = 6) -> dict:
    old, new = _sections(conn, old_vid), _sections(conn, new_vid)
    rows, counts = [], {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    for o, n in _align(old, new):
        if o and n:
            if o["flat"] == n["flat"]:
                status, similarity, changes = "unchanged", 1.0, None
            else:
                status = "modified"
                similarity = round(_ratio(o["flat"][:4000], n["flat"][:4000]), 3)
                changes = _sentence_changes(o["body"], n["body"], sentence_limit)
            row = {"status": status, "old": _label(o), "new": _label(n),
                   "old_section_id": o["id"], "new_section_id": n["id"],
                   "renumbered": o["number"] != n["number"], "similarity": similarity}
            if changes:
                row["changes"] = changes
        elif n:
            status = "added"
            row = {"status": status, "old": None, "new": _label(n), "new_section_id": n["id"]}
        else:
            status = "removed"
            row = {"status": status, "old": _label(o), "new": None, "old_section_id": o["id"]}
        counts[status] += 1
        rows.append(row)
    return {"from": old_vid, "to": new_vid, "level": "section", "summary": counts, "sections": rows}


def _claims(conn: Database, version_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT c.id, c.claim_type, c.modality, c.subject, c.value_num, c.unit, c.topic_terms,
                  p.id AS span_id, p.text, p.start_byte, p.end_byte, s.number, s.title
           FROM claims c JOIN spans p ON p.id = c.span_id LEFT JOIN sections s ON s.id = p.section_id
           WHERE c.version_id = %s ORDER BY p.start_byte""",
        (version_id,),
    ).fetchall()
    for r in rows:
        r["flat"] = flatten(r["text"])
        r["terms"] = set(r["topic_terms"] or [])
    return rows


def _claim_view(c: dict) -> dict:
    return {"span_id": c["span_id"], "section": _label(c) if c["title"] else None, "modality": c["modality"],
            "subject": c["subject"], "value": c["value_num"], "unit": c["unit"], "text": c["flat"]}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def diff_claims(conn: Database, old_vid: str, new_vid: str, limit: int = 200) -> dict:
    old, new = _claims(conn, old_vid), _claims(conn, new_vid)
    old_text = {c["flat"]: c for c in old}
    unmatched_new, matched_old = [], set()
    for n in new:
        o = old_text.get(n["flat"])
        if o is not None:
            matched_old.add(o["id"])
        else:
            unmatched_new.append(n)

    remaining_old = [o for o in old if o["id"] not in matched_old]
    changed, added = [], []
    for n in unmatched_new:
        best, best_score = None, CLAIM_MATCH
        for o in remaining_old:
            score = _jaccard(n["terms"], o["terms"])
            if score > best_score:
                best, best_score = o, score
        if best is None:
            added.append(_claim_view(n))
            continue
        remaining_old.remove(best)
        kinds = []
        if best["modality"] != n["modality"]:
            kinds.append("modality_changed")
        if best["value_num"] != n["value_num"]:
            kinds.append("value_changed")
        changed.append({"change": kinds or ["reworded"], "similarity": round(best_score, 3),
                        "old": _claim_view(best), "new": _claim_view(n)})

    removed = [_claim_view(o) for o in remaining_old]
    changed.sort(key=lambda c: (c["change"] == ["reworded"], -c["similarity"]))
    return {
        "from": old_vid, "to": new_vid, "level": "claim",
        "summary": {"unchanged": len(matched_old), "changed": len(changed), "added": len(added), "removed": len(removed),
                    "modality_changed": sum("modality_changed" in c["change"] for c in changed),
                    "value_changed": sum("value_changed" in c["change"] for c in changed)},
        "changed": changed[:limit], "added": added[:limit], "removed": removed[:limit],
    }


def diff_references(conn: Database, old_vid: str, new_vid: str) -> dict:
    def targets(vid: str) -> dict[tuple, str]:
        rows = conn.execute(
            """SELECT DISTINCT relation, coalesce(target_doc, 'RFC ' || target_rfc) AS target, raw
               FROM refs WHERE version_id = %s AND (target_version IS NULL OR target_version <> version_id)
                 AND (target_doc IS NOT NULL OR target_rfc IS NOT NULL)""",
            (vid,),
        ).fetchall()
        out = {}
        for r in rows:
            out.setdefault((r["relation"] if r["relation"] in ("obsoletes", "updates") else "cites", r["target"]), r["raw"])
        return out

    old, new = targets(old_vid), targets(new_vid)
    fmt = lambda keys: [{"relation": k[0], "target": k[1]} for k in sorted(keys)]
    return {"from": old_vid, "to": new_vid, "level": "reference",
            "added": fmt(new.keys() - old.keys()), "removed": fmt(old.keys() - new.keys()),
            "kept": len(new.keys() & old.keys())}
