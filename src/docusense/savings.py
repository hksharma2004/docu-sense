"""token savings ledger: what the agent read via docusense vs. pasting the docs.

each mcp tool call appends a line to $DOCUSENSE_HOME/savings.jsonl:
    {"ts", "session", "tool", "returned", "versions"}
`returned` is the token estimate of the response, `versions` the versions it drew from.
the counterfactual is pasting each touched version once (full canonical text), so a doc read
by ten calls counts once on the paste side. both sides use chars/4. nothing leaves the machine.
"""

import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

from docusense.config import docusense_home

_CITATION = re.compile(r"ds://([^#\s\"]+)#")
_lock = threading.Lock()
SESSION = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def ledger_path() -> Path:
    return docusense_home() / "savings.jsonl"


def enabled() -> bool:
    return os.environ.get("DOCUSENSE_SAVINGS_LOG", "1").strip().lower() not in ("0", "false", "no", "off")


def versions_in(payload: str) -> list[str]:
    """version ids a response cites (every span view carries a ds:// citation)"""
    return sorted(set(_CITATION.findall(payload)))


def record(tool: str, payload: str) -> None:
    if not enabled():
        return
    line = json.dumps({"ts": round(time.time(), 3), "session": SESSION, "tool": tool,
                       "returned": len(payload) // 4, "versions": versions_in(payload)})
    try:
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # the meter must never break a tool call


def summarize(version_tokens: dict[str, int], since: float | None = None) -> dict:
    """aggregate the ledger. `version_tokens` maps version id -> tokens of its full text"""
    sessions: dict[str, dict] = defaultdict(lambda: {"calls": 0, "returned": 0, "versions": set(), "tools": defaultdict(int)})
    path = ledger_path()
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if since and row.get("ts", 0) < since:
                continue
            s = sessions[row["session"]]
            s["calls"] += 1
            s["returned"] += row["returned"]
            s["versions"].update(row.get("versions", []))
            s["tools"][row["tool"]] += 1

    total = {"sessions": 0, "calls": 0, "returned": 0, "paste": 0, "tools": defaultdict(int)}
    for s in sessions.values():
        paste = sum(version_tokens.get(v, 0) for v in s["versions"])
        if not paste:  # sessions that never touched document text (only list_documents etc)
            continue
        total["sessions"] += 1
        total["calls"] += s["calls"]
        total["returned"] += s["returned"]
        total["paste"] += paste
        for t, n in s["tools"].items():
            total["tools"][t] += n
    total["saved"] = max(total["paste"] - total["returned"], 0)
    total["ratio"] = round(total["paste"] / total["returned"], 1) if total["returned"] else None
    total["tools"] = dict(sorted(total["tools"].items(), key=lambda kv: -kv[1]))
    return total
