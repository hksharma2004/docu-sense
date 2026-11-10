"""Contradiction surfacing across documents. Both claims are always kept; nothing is auto-resolved.

Stage 1 (deterministic, recall-oriented): a candidate pair comes from two different documents,
shares rare topic terms (IDF-weighted overlap), and either
  - has the same unit but a different number   -> value_mismatch
  - has opposing BCP 14 modalities             -> modality_mismatch
Stage 2 (optional, bounded LLM judge, precision-oriented): Groq labels each candidate. The verdict
is stored next to the candidate; rejected candidates stay in the table, marked, never deleted.
"""

import json
import math
from itertools import combinations

import psycopg
from psycopg.types.json import Jsonb

from docusense.extract.sentences import flatten

TIME_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
MIN_SHARED_TERMS = 2
MIN_SCORE = 0.35          # IDF-weighted |A∩B| / min(|A|, |B|)
MAX_POSTING = 400         # skip terms shared by too many claims to be discriminative
POSITIVE = {"MUST", "SHOULD"}
NEGATIVE = {"MUST NOT", "SHOULD NOT"}
RULE_METHOD = "rule/0.2"


def _normalized(value: float | None, unit: str | None) -> tuple[float | None, str | None]:
    if value is None or unit is None:
        return value, unit
    if unit in TIME_SECONDS:
        return value * TIME_SECONDS[unit], "second"
    if unit == "byte":
        return value, "octet"
    return value, unit


def _opposed(a: str | None, b: str | None) -> bool:
    if not a or not b or a == b:
        return False
    pair = {a, b}
    return bool(pair & POSITIVE and pair & NEGATIVE) or pair in ({"MUST", "MAY"}, {"MAY", "MUST NOT"}, {"MAY", "SHOULD NOT"})


def _load(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT c.id, c.version_id, v.document_id, c.modality, c.value_num, c.unit, c.topic_terms, p.text
           FROM claims c JOIN versions v ON v.id = c.version_id JOIN spans p ON p.id = c.span_id"""
    ).fetchall()
    for r in rows:
        r["terms"] = set(r["topic_terms"] or [])
        r["norm_value"], r["norm_unit"] = _normalized(r["value_num"], r["unit"])
    return rows


def find_candidates(conn: psycopg.Connection, min_score: float = MIN_SCORE) -> list[dict]:
    claims = _load(conn)
    df: dict[str, int] = {}
    for c in claims:
        for t in c["terms"]:
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(len(claims) / n) for t, n in df.items()}
    for c in claims:
        c["weight"] = sum(idf[t] for t in c["terms"]) or 1.0

    by_term: dict[str, list[int]] = {}
    for i, c in enumerate(claims):
        for t in c["terms"]:
            by_term.setdefault(t, []).append(i)

    seen, out = set(), []
    for postings in by_term.values():
        if len(postings) > MAX_POSTING:
            continue
        for i, j in combinations(postings, 2):
            if (i, j) in seen:
                continue
            seen.add((i, j))
            a, b = claims[i], claims[j]
            if a["document_id"] == b["document_id"]:
                continue
            if a["norm_unit"] and a["norm_unit"] == b["norm_unit"] and a["norm_value"] != b["norm_value"]:
                reason = "value_mismatch"
            elif _opposed(a["modality"], b["modality"]):
                reason = "modality_mismatch"
            else:
                continue
            shared = a["terms"] & b["terms"]
            if len(shared) < MIN_SHARED_TERMS:
                continue
            score = sum(idf[t] for t in shared) / min(a["weight"], b["weight"])
            if score >= min_score:
                out.append({"claim_a": a["id"], "claim_b": b["id"], "reason": reason,
                            "score": round(score, 3), "shared_terms": sorted(shared), "a": a, "b": b})
    out.sort(key=lambda c: -c["score"])
    return out


_JUDGE_PROMPT = """Two statements come from different technical documents.

A: <<<{a}>>>
B: <<<{b}>>>

Do they contradict each other? They contradict if someone cannot follow both at once, or if they
state different values for the same limit or requirement. Statements about different things do not
contradict. Answer with JSON only:
{{"contradiction": true|false, "confidence": <0.0-1.0>, "explanation": "<one sentence>"}}"""


def detect(conn: psycopg.Connection, llm_judge: bool = False, max_judge_calls: int = 300) -> dict:
    """Recompute the conflicts table. Returns counts."""
    candidates = find_candidates(conn)
    latest = {r["id"] for r in conn.execute(
        "SELECT DISTINCT ON (document_id) id FROM versions ORDER BY document_id, seq DESC")}
    # Judge budget order: contradictions between current versions first, then by score.
    candidates.sort(key=lambda c: (not (c["a"]["version_id"] in latest and c["b"]["version_id"] in latest),
                                   -c["score"]))
    judge = None
    if llm_judge:
        from docusense.extract.llm_fallback import SubjectFallback
        judge = SubjectFallback(max_calls=max_judge_calls)

    confirmed = rejected = 0
    with conn.transaction():
        conn.execute("DELETE FROM conflicts")
        for c in candidates:
            details = {"shared_terms": c["shared_terms"], "status": "candidate"}
            method = RULE_METHOD
            if judge and judge.available:
                verdict = _judge(judge, flatten(c["a"]["text"]), flatten(c["b"]["text"]))
                if verdict is not None:
                    details["judge"] = verdict
                    details["status"] = "confirmed" if verdict["contradiction"] else "rejected"
                    method = RULE_METHOD + "+llm"
                    confirmed += verdict["contradiction"]
                    rejected += not verdict["contradiction"]
            conn.execute(
                """INSERT INTO conflicts (claim_a, claim_b, reason, method, confidence, details)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (c["claim_a"], c["claim_b"], c["reason"], method, c["score"], Jsonb(details)),
            )
    conn.commit()
    return {"candidates": len(candidates), "confirmed": confirmed, "rejected": rejected,
            "unjudged": len(candidates) - confirmed - rejected, "judge_calls": judge.calls if judge else 0}


def _judge(judge, a: str, b: str) -> dict | None:
    import time

    import httpx

    from docusense.extract.llm_fallback import GROQ_URL
    from docusense.store.blobs import sha256_hex

    prompt = _JUDGE_PROMPT.format(a=a[:1500], b=b[:1500])
    judge.calls += 1
    try:
        for attempt in range(5):
            resp = judge._client.post(
                GROQ_URL, headers={"Authorization": f"Bearer {judge.api_key}"},
                json={"model": judge.model, "temperature": 0, "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": prompt}]},
            )
            if resp.status_code != 429:
                break
            time.sleep(float(resp.headers.get("retry-after", 2 ** attempt)))
        resp.raise_for_status()
        data = json.loads(resp.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    return {"contradiction": bool(data.get("contradiction")), "confidence": data.get("confidence"),
            "explanation": data.get("explanation"), "model_id": judge.model,
            "prompt_hash": sha256_hex(prompt.encode())}
