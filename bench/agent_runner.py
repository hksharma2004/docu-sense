"""Run the benchmark: every question × every config, same model, same budget (PLAN.md §8).

    uv run python -m bench.agent_runner --model google/gemma-4-31b-it:free --configs docusense,fs,vector --limit 3

Each config is an MCP server spoken to over stdio; its tools are offered to an OpenAI-compatible chat model
(OpenRouter or Groq). Results are cached per (model, config, question) in bench/results/cache/, so rate
limits never force a full re-run: run again and it continues where it stopped.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from docusense.config import get_settings

BENCH = Path(__file__).resolve().parent
CACHE = BENCH / "results" / "cache"
PY = sys.executable
CONFIGS = {
    "docusense": {"args": ["-c", "from docusense.mcp_server import main; main()"],
                  "exclude": {"add_document", "ingest_status"}},
    "fs": {"args": [str(BENCH / "baselines" / "fs_mcp.py")], "exclude": set()},
    "vector": {"args": [str(BENCH / "baselines" / "vector_rag_mcp.py")], "exclude": set()},
}
ENDPOINTS = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter_api_key"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "groq_api_key"),
}
SYSTEM = """You answer questions about a collection of technical documents (IETF RFCs and an example
organisation's internal policies) using only the tools provided. Do not answer from memory.

When you are done, give a concise answer. Support every factual statement with a short verbatim quote from
the source in double quotes, followed by where it comes from (document/version and section, file name, or
any citation identifier the tools returned, copied exactly). If the documents disagree, say so and quote both."""
MAX_RESULT_CHARS = 16_000


class DailyLimit(RuntimeError):
    pass


class Chat:
    def __init__(self, provider: str, model: str):
        url, key_field = ENDPOINTS[provider]
        self.url, self.model = url, model
        self.key = getattr(get_settings(), key_field)
        if not self.key:
            raise SystemExit(f"{key_field.upper()} is not set")
        self.http = httpx.Client(timeout=180)

    def __call__(self, messages: list, tools: list | None) -> dict:
        body = {"model": self.model, "messages": messages, "temperature": 0}
        if tools:
            body["tools"] = tools
        for attempt in range(8):
            try:
                r = self.http.post(self.url, headers={"Authorization": f"Bearer {self.key}"}, json=body)
            except httpx.TransportError:  # network blip / DNS / laptop sleep: back off and retry
                time.sleep(min(2 ** attempt * 5, 120))
                continue
            if r.status_code == 429:
                text = r.text.lower()
                if "per-day" in text or "per day" in text or "daily" in text or "free-models-per-day" in text:
                    raise DailyLimit(r.text[:300])
                time.sleep(min(float(r.headers.get("retry-after", 0) or 2 ** attempt * 5), 90))
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(str(data["error"])[:300])
            return data
        raise RuntimeError("chat endpoint kept failing (rate limited or 5xx)")


def _tool_schema(t) -> dict:
    return {"type": "function", "function": {"name": t.name, "description": (t.description or "")[:1000],
                                             "parameters": t.input_schema or {"type": "object", "properties": {}}}}


async def run_question(session: ClientSession, tools: list, chat: Chat, q: dict, budget: dict) -> dict:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": q["question"]}]
    log, usage, calls = [], {"prompt_tokens": 0, "completion_tokens": 0}, 0
    started = time.time()
    answer, stop = "", "answered"
    while True:
        over = calls >= budget["tool_calls"] or usage["prompt_tokens"] + usage["completion_tokens"] >= budget["tokens"]
        if over:
            messages.append({"role": "user", "content": "Tool/token budget exhausted. Answer now from what you have."})
            stop = "budget"
        resp = await asyncio.to_thread(chat, messages, None if over else tools)
        for k in usage:
            usage[k] += (resp.get("usage") or {}).get(k, 0) or 0
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls or over:
            answer = msg.get("content") or ""
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            calls += 1
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
                result = await session.call_tool(name, args)
                text = "\n".join(getattr(c, "text", "") for c in result.content)
                if result.is_error:
                    text = "ERROR: " + text
            except Exception as e:  # malformed arguments or server error: the agent sees it and can adapt
                args, text = {}, f"ERROR: {type(e).__name__}: {e}"
            log.append({"tool": name, "args": args, "result_chars": len(text)})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text[:MAX_RESULT_CHARS]})
    return {"id": q["id"], "type": q["type"], "answer": answer, "tool_calls": calls, "calls": log,
            "usage": usage, "latency_s": round(time.time() - started, 1), "stop": stop}


async def run_config(config: str, questions: list[dict], chat: Chat, budget: dict) -> list[dict]:
    spec = CONFIGS[config]
    out_dir = CACHE / re.sub(r"[^\w.-]", "_", chat.model) / config
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [q for q in questions if not (out_dir / f"{q['id']}.json").exists()]
    if todo:
        params = StdioServerParameters(command=PY, args=spec["args"], env={**os.environ}, cwd=str(BENCH.parent))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = [_tool_schema(t) for t in (await session.list_tools()).tools if t.name not in spec["exclude"]]
                for q in todo:
                    print(f"[{config}] {q['id']} …", file=sys.stderr, flush=True)
                    result = await run_question(session, tools, chat, q, budget)
                    result.update(model=chat.model, config=config, tools_offered=len(tools))
                    (out_dir / f"{q['id']}.json").write_text(json.dumps(result, indent=1))
    return [json.loads((out_dir / f"{q['id']}.json").read_text()) for q in questions]


def main() -> None:
    s = get_settings()
    p = argparse.ArgumentParser()
    p.add_argument("--provider", default=s.agent_provider, choices=sorted(ENDPOINTS))
    p.add_argument("--model", default=s.agent_model)
    p.add_argument("--configs", default="docusense,fs,vector")
    p.add_argument("--ids", default="", help="comma-separated question ids")
    p.add_argument("--limit", type=int, default=0, help="first N questions only")
    args = p.parse_args()

    questions = [json.loads(line) for line in (BENCH / "questions.jsonl").read_text().splitlines() if line.strip()]
    if args.ids:
        wanted = set(args.ids.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]
    chat = Chat(args.provider, args.model)
    budget = {"tool_calls": s.agent_max_tool_calls, "tokens": s.agent_max_tokens}
    stop = False
    for config in args.configs.split(","):
        try:
            asyncio.run(run_config(config, questions, chat, budget))
        except* DailyLimit as group:  # raised inside the MCP client's task group, hence except*
            print(f"daily request limit reached; cached results are kept, re-run later to continue.\n"
                  f"{group.exceptions[0]}", file=sys.stderr)
            stop = True
        if stop:
            break
    print(f"results cached under {CACHE}; score with: uv run python -m bench.score --model {args.model}", file=sys.stderr)


if __name__ == "__main__":
    main()
