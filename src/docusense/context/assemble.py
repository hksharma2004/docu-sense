"""budget-aware context assembly.

per requested span:
  1. verify    sha-256 mismatch rejects the span (goes to `rejected`)
  2. version   if obsolete, attach the closest span from the latest version + its similarity
  3. conflict  append claims from other docs that conflict with this one
  4. pack      requested > newer version > conflict, greedy within the token budget,
               cut at sentence boundaries when a block doesn't fit
"""

from docusense.extract.sentences import flatten, split_sentences
from docusense.services import DocuSense, tokens
from docusense.versions.blame import _best_match

PRIORITY = {"requested": 0, "newer_version": 1, "conflict": 2}
MIN_BLOCK_TOKENS = 40


def _truncate(text: str, budget_tokens: int) -> str:
    out = ""
    for s in split_sentences(text):
        candidate = (out + " " + flatten(s.text)).strip()
        if len(candidate) // 4 > budget_tokens:
            break
        out = candidate
    return out


def _conflicts_for(ds: DocuSense, span: dict) -> list[dict]:
    rows = ds.conn.execute(
        """SELECT f.id, f.reason, f.details, CASE WHEN ca.span_id = mine.id THEN cb.span_id ELSE ca.span_id END AS other_span
           FROM spans mine
           JOIN claims c ON c.span_id = mine.id
           JOIN conflicts f ON f.claim_a = c.id OR f.claim_b = c.id
           JOIN claims ca ON ca.id = f.claim_a JOIN claims cb ON cb.id = f.claim_b
           WHERE mine.version_id = %s AND mine.start_byte >= %s AND mine.end_byte <= %s
             AND coalesce(f.details->>'status', '') <> 'rejected'
           ORDER BY f.confidence DESC, f.id LIMIT 5""",
        (span["version_id"], span["start_byte"], span["end_byte"]),
    ).fetchall()
    return rows


def assemble_context(ds: DocuSense, span_ids: list[int], token_budget: int = 4000) -> dict:
    blocks, rejected, seen = [], [], set()

    def add(span_id: int, role: str, note: str | None = None) -> dict | None:
        if span_id in seen:
            return None
        seen.add(span_id)
        rows = ds._spans("p.id = %s", (span_id,))
        if not rows:
            rejected.append({"span_id": span_id, "reason": "span not found"})
            return None
        check = ds.verifier.verify_span(span_id)
        if not check["verified"]:
            rejected.append({"span_id": span_id, "reason": "provenance check failed (SHA-256 mismatch)",
                             "action": "re-fetch the span or cite a different source"})
            return None
        block = ds._span_view(rows[0], 20000) | {"role": role, "verified": True, "_row": rows[0]}
        if note:
            block["note"] = note
        blocks.append(block)
        return block

    for sid in span_ids:
        block = add(sid, "requested")
        if block is None:
            continue
        row = block["_row"]
        newer = block.get("newer_version")
        if newer:
            match, score = _best_match(ds.conn, newer, flatten(row["text"]), row["kind"])
            if match is not None and score >= 0.4:
                nb = add(match["id"], "newer_version",
                         f"{row['version_id']} is obsolete; closest text in {newer} (similarity {score:.2f})")
                if nb is None and match["id"] in seen:
                    block["note"] = f"also present in {newer}"
            else:
                block["note"] = f"{row['version_id']} is obsolete and this text has no close match in {newer}"
        for c in _conflicts_for(ds, row):
            status = (c["details"] or {}).get("status", "candidate")
            add(c["other_span"], "conflict", f"{c['reason']} with span {sid} ({status})")

    blocks.sort(key=lambda b: PRIORITY[b["role"]])
    packed, omitted, used = [], [], 0
    for b in blocks:
        b.pop("_row", None)
        cost = tokens(b)
        if used + cost <= token_budget:
            packed.append(b)
            used += cost
            continue
        room = token_budget - used - (cost - len(b["text"]) // 4)
        if room >= MIN_BLOCK_TOKENS:
            b["text"] = _truncate(b["text"], room) + " …"
            b["truncated"] = True
            packed.append(b)
            used += tokens(b)
        else:
            omitted.append({"span_id": b["span_id"], "role": b["role"], "citation": b["citation"]})

    return {"token_budget": token_budget, "tokens_used": used, "blocks": packed,
            "omitted": omitted, "rejected": rejected}
