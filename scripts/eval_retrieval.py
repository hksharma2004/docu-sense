"""retrieval eval on real non-rfc documents (no llm, no api cost).

paraphrased questions -> does search return the passage that answers them?
reports hit@1, hit@5 and mrr for lexical, semantic and hybrid.

    uv run python scripts/eval_retrieval.py          # throwaway DOCUSENSE_HOME
    uv run python scripts/eval_retrieval.py --keep   # keep the eval store

docs are downloaded once to ~/.cache/docusense-eval. they can change upstream (irs revises
pub 463 yearly), so the sha-256 seen is printed with the results.
"""

import argparse
import hashlib
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

DOCS = {
    "irs-p463.pdf": "https://www.irs.gov/pub/irs-pdf/p463.pdf",                 # 3-column government publication
    "attention.pdf": "https://arxiv.org/pdf/1706.03762v7",                     # 2-column-ish research paper
}

# (document, question, substring of the answering passage)
QUESTIONS = [
    ("irs-p463", "Where is my tax home if my family lives in a different city from where I work?",
     "your tax home is your regular place of business"),
    ("irs-p463", "What share of meal costs on a business trip can I write off?",
     "deduct only 50% of the unreimbursed cost of your meals"),
    ("irs-p463", "Do tips to hotel porters count as incidental expenses?", "fees and tips given to porters"),
    ("irs-p463", "Can I deduct what I pay to park at my office every day?",
     "fees you pay to park your car at your place of business are nondeductible"),
    ("irs-p463", "Where can I look up the federal per diem rates?", "gsa.gov/travel/plan-book/per-diem-rates"),
    ("irs-p463", "Does a short-term assignment in another city change my tax home?",
     "if your assignment or job away from your main place of work is temporary"),
    ("irs-p463", "If I relocate for a job with a probation period, is it temporary or indefinite?",
     "during a probationary period, the job is indefinite"),
    ("irs-p463", "What is the maximum I can deduct for a gift to one client?", "you can deduct no more than $25"),
    ("irs-p463", "How many cents per mile can I claim for driving my car for work in 2025?",
     "standard mileage rate for the cost of operating your car"),
    ("irs-p463", "Can I deduct my wife's travel costs when she comes along on a business trip?",
     "if a spouse, dependent, or other individual goes with you"),
    ("irs-p463", "When can a convention held outside North America be deducted?",
     "outside the north american area as within the north american area"),
    ("attention", "How many identical layers are stacked in the encoder?", "stack of n = 6 identical layers"),
    ("attention", "Why are attention logits divided by the square root of the key dimension?",
     "we scale the dot products by"),
    ("attention", "How does the model represent token positions without recurrence?",
     "sine and cosine functions of different frequencies"),
    ("attention", "What BLEU score did the model reach on English to German?", "28.4 bleu"),
    ("attention", "What dropout probability was used for the base model?", "pdrop = 0.1"),
    ("attention", "Did they smooth the training labels and by how much?", "label smoothing of value"),
    ("attention", "What hardware was used to train the models?", "8 nvidia p100 gpus"),
    ("attention", "How many attention heads are used?", "h = 8 parallel attention layers"),
    ("attention", "How was the learning rate varied during training?", "increasing the learning rate linearly"),
]


def _norm(text: str) -> str:
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)          # PDF line-break hyphenation
    text = re.sub(r"(\w)- (\w)", r"\1\2", " ".join(text.split()))
    return text.lower().replace("’", "'")


def fetch(cache: Path) -> dict[str, Path]:
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, url in DOCS.items():
        path = cache / name
        if not path.exists():
            print(f"downloading {url}", file=sys.stderr)
            req = urllib.request.Request(url, headers={"User-Agent": "docusense-eval"})
            with urllib.request.urlopen(req, timeout=60) as r:
                path.write_bytes(r.read())
        out[name] = path
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    files = fetch(Path.home() / ".cache" / "docusense-eval")
    home = Path(tempfile.mkdtemp(prefix="docusense-eval-"))
    os.environ.update(DOCUSENSE_HOME=str(home), DOCUSENSE_DATABASE_URL="", DOCUSENSE_STORE_DIR="")

    from docusense.config import get_settings
    get_settings.cache_clear()
    from docusense.db.conn import connect, init_schema
    from docusense.ingest.add import add_file, refresh_derived
    from docusense.services import DocuSense

    with connect() as conn:
        init_schema(conn)
        for name, path in files.items():
            r = add_file(conn, path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
            print(f"{r.version_id:24} {r.status:9} pages={r.pages} spans={r.spans} sha256={digest}…")
        refresh_derived(conn, index=True)

        ds = DocuSense(conn)
        print(f"\n{'mode':9} hit@1  hit@{args.k}  MRR   (n={len(QUESTIONS)})")
        misses: dict[str, list[str]] = {}
        for mode in ("lexical", "semantic", "hybrid"):
            hit1 = hitk = rr = 0.0
            for doc, question, gold in QUESTIONS:
                results = ds.search(question, mode=mode, doc=doc, k=args.k, max_tokens=100_000)["results"]
                rank = next((i for i, r in enumerate(results) if gold in _norm(r["text"])), None)
                if rank is None:
                    misses.setdefault(mode, []).append(question)
                    continue
                hit1 += rank == 0
                hitk += 1
                rr += 1 / (rank + 1)
            n = len(QUESTIONS)
            print(f"{mode:9} {hit1 / n:5.2f}  {hitk / n:5.2f}  {rr / n:5.2f}")
        for mode, qs in misses.items():
            print(f"\nmissed by {mode}:", *[f"  - {q}" for q in qs], sep="\n")
    if args.keep:
        print(f"\neval store kept at {home}")


if __name__ == "__main__":
    main()
