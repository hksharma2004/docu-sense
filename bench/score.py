"""score cached benchmark runs.

    uv run python -m bench.score --model google/gemma-4-31b-it:free

metrics per config (same for all, so it's fair):
  correct       every answer_keywords group matched (case-insensitive, groups list alternatives)
  cite_hit      at least one gold (version, section) cited
  cite_recall   share of gold citations cited
  quotes_ok     share of quotes ("...", >= 15 chars) found verbatim (whitespace-insensitive) in a source
  tool calls, prompt+completion tokens, latency (means)
citations come from ds:// ids in the answer and from verbatim quotes, located in the canonical
texts and mapped to their section. a quote found in several versions cites all of them.
"""

import argparse
import bisect
import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path

BENCH = Path(__file__).resolve().parent
WORK, CACHE = BENCH / "work", BENCH / "results" / "cache"
DS_CITATION = re.compile(r"ds://([\w.\-]+@[\w.\-]+)#§([^:\s\]\)]+):b(\d+)-(\d+)")
QUOTE = re.compile(r"[\"“]([^\"”]{15,600})[\"”]")


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("’", "'").replace("‘", "'").split())


@lru_cache
def corpus() -> dict:
    """version -> (normalized text, normalized-char -> byte offset, section starts, section rows)"""
    sections = json.loads((WORK / "sections.json").read_text())
    out = {}
    for path in sorted((WORK / "texts").glob("*.txt")):
        vid, raw = path.stem, path.read_bytes().decode("utf-8")
        norm_chars, offsets, byte, prev_space = [], [], 0, True
        for ch in raw:
            if ch.isspace():
                if not prev_space:
                    norm_chars.append(" ")
                    offsets.append(byte)
                prev_space = True
            else:
                norm_chars.append(ch.lower().replace("’", "'").replace("‘", "'"))
                offsets.append(byte)
                prev_space = False
            byte += len(ch.encode("utf-8"))
        rows = sorted(sections.get(vid, []), key=lambda r: (r[0], -r[1]))
        out[vid] = ("".join(norm_chars), offsets, rows)
    return out


def section_at(vid: str, byte: int) -> tuple[str | None, str]:
    """innermost section containing a byte offset -> (number, title)"""
    best = None
    for start, end, number, title in corpus()[vid][2]:
        if start <= byte < max(end, start + 1) and (best is None or start >= best[0]):
            best = (start, number, title)
    return (best[1], best[2]) if best else (None, "")


def cited_locations(answer: str) -> tuple[set, int, int]:
    """(set of (version, section number or title), quotes found, quotes total)"""
    cited: set[tuple[str, str]] = set()
    for vid, section, _, _ in DS_CITATION.findall(answer):
        cited.add((vid, section))
    found = total = 0
    for quote in QUOTE.findall(answer):
        q = _norm(quote.strip(" .…"))
        if len(q) < 15:
            continue
        total += 1
        hit = False
        for vid, (text, offsets, _) in corpus().items():
            i = text.find(q)
            while i != -1:
                hit = True
                number, title = section_at(vid, offsets[i])
                cited.add((vid, number or title))
                i = text.find(q, i + 1)
        found += hit
    return cited, found, total


def _section_matches(gold: str, cited: str) -> bool:
    return cited == gold or cited.startswith(gold + ".")


def score_one(q: dict, r: dict) -> dict:
    answer = r.get("answer") or ""
    low = _norm(answer)
    correct = all(any(_norm(alt) in low for alt in group) for group in q["answer_keywords"])
    cited, quotes_found, quotes_total = cited_locations(answer)
    gold = [(g["version"], g["section"]) for g in q["gold_citations"]]
    matched = [g for g in gold if any(c[0] == g[0] and _section_matches(g[1], c[1]) for c in cited)]
    usage = r.get("usage") or {}
    return {"correct": correct, "cite_hit": bool(matched), "cite_recall": len(matched) / len(gold),
            "quotes_found": quotes_found, "quotes_total": quotes_total, "tool_calls": r.get("tool_calls", 0),
            "tokens": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            "latency_s": r.get("latency_s", 0), "budget_stop": r.get("stop") == "budget"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    args = p.parse_args()
    questions = {json.loads(l)["id"]: json.loads(l) for l in (BENCH / "questions.jsonl").read_text().splitlines() if l.strip()}
    model_dir = CACHE / re.sub(r"[^\w.-]", "_", args.model)
    report: dict = {"model": args.model, "date": dt.date.today().isoformat(), "configs": {}}
    rows = []
    for cfg_dir in sorted(p for p in model_dir.iterdir() if p.is_dir()):
        results = [json.loads(f.read_text()) for f in sorted(cfg_dir.glob("*.json"))]
        scored = {r["id"]: score_one(questions[r["id"]], r) for r in results if r["id"] in questions}
        if not scored:
            continue
        n = len(scored)
        mean = lambda k: sum(float(s[k]) for s in scored.values()) / n
        qf, qt = sum(s["quotes_found"] for s in scored.values()), sum(s["quotes_total"] for s in scored.values())
        by_type: dict[str, list[bool]] = {}
        for qid, s in scored.items():
            by_type.setdefault(questions[qid]["type"], []).append(s["correct"])
        summary = {"n": n, "correct": mean("correct"), "cite_hit": mean("cite_hit"), "cite_recall": mean("cite_recall"),
                   "quotes_ok": qf / qt if qt else None, "tool_calls": mean("tool_calls"), "tokens": mean("tokens"),
                   "latency_s": mean("latency_s"), "budget_stops": sum(s["budget_stop"] for s in scored.values()),
                   "correct_by_type": {t: sum(v) / len(v) for t, v in sorted(by_type.items())}, "per_question": scored}
        report["configs"][cfg_dir.name] = summary
        rows.append((cfg_dir.name, summary))

    lines = [f"Model: `{args.model}` · {report['date']}", "",
             "| config | n | correct | cite hit | cite recall | quotes verified | tool calls | tokens | latency s |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, s in rows:
        qok = f"{s['quotes_ok']:.0%}" if s["quotes_ok"] is not None else "–"
        lines.append(f"| {name} | {s['n']} | {s['correct']:.0%} | {s['cite_hit']:.0%} | {s['cite_recall']:.0%} | {qok} | "
                     f"{s['tool_calls']:.1f} | {s['tokens']:,.0f} | {s['latency_s']:.0f} |")
    types = sorted({t for _, s in rows for t in s["correct_by_type"]})
    if types:
        lines += ["", "| config | " + " | ".join(types) + " |", "|---|" + "---|" * len(types)]
        for name, s in rows:
            lines.append(f"| {name} | " + " | ".join(f"{s['correct_by_type'].get(t, 0):.0%}" for t in types) + " |")
    table = "\n".join(lines)
    out = BENCH / "results" / f"{report['date']}_{re.sub(r'[^\w.-]', '_', args.model)}"
    out.with_suffix(".json").write_text(json.dumps(report, indent=1))
    out.with_suffix(".md").write_text(table + "\n")
    print(table)


if __name__ == "__main__":
    main()
