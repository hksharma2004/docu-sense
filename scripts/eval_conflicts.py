"""Score stored conflicts against corpus/synthetic/planted_conflicts.yaml (recall + judged precision)."""

from pathlib import Path

import yaml

from docusense.db.conn import connect

GOLD = Path(__file__).resolve().parents[1] / "corpus" / "synthetic" / "planted_conflicts.yaml"

SQL = """
SELECT f.id, f.reason, f.confidence, f.details->>'status' AS status,
       ca.version_id AS va, sa.number AS na, cb.version_id AS vb, sb.number AS nb
FROM conflicts f
JOIN claims ca ON ca.id = f.claim_a JOIN claims cb ON cb.id = f.claim_b
JOIN spans pa ON pa.id = ca.span_id JOIN spans pb ON pb.id = cb.span_id
LEFT JOIN sections sa ON sa.id = pa.section_id LEFT JOIN sections sb ON sb.id = pb.section_id
"""


def main() -> None:
    gold = yaml.safe_load(GOLD.read_text())["conflicts"]
    with connect() as conn:
        rows = conn.execute(SQL).fetchall()
    index: dict[tuple, list[dict]] = {}
    for r in rows:
        index.setdefault((r["va"], r["na"], r["vb"], r["nb"]), []).append(r)
        index.setdefault((r["vb"], r["nb"], r["va"], r["na"]), []).append(r)

    hits = {"candidate": 0, "confirmed": 0}
    for g in gold:
        key = (g["synthetic"]["version"], g["synthetic"]["section"], g["source"]["version"], g["source"]["section"])
        found = index.get(key, [])
        statuses = {r["status"] for r in found}
        is_hit = bool(found) and statuses != {"rejected"}
        hits["candidate"] += bool(found)
        hits["confirmed"] += is_hit
        print(f"{'HIT ' if is_hit else 'MISS'} {g['id']:4} {statuses or '-'}  {key}")

    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"\nrecall (candidates): {hits['candidate']}/{len(gold)}")
    print(f"recall (not rejected by judge): {hits['confirmed']}/{len(gold)}")
    print(f"stored conflicts by status: {by_status}")


if __name__ == "__main__":
    main()
