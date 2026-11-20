"""end-to-end check over the real mcp stdio protocol.

launches `docusense serve-mcp` and replays the tool path an agent would take for:
  "What does RFC 6750 say about the URI syntax it references?"
"""

import asyncio
import json
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters


def _payload(result) -> dict:
    if result.is_error:
        raise RuntimeError(result.content[0].text)
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def main() -> None:
    params = StdioServerParameters(command="uv", args=["run", "--quiet", "docusense", "serve-mcp"])
    async with Client(params) as client:
        tools = await client.list_tools()
        print(f"tools ({len(tools.tools)}):", ", ".join(t.name for t in tools.tools))

        async def call(name: str, **args) -> dict:
            print(f"\n→ {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
            return _payload(await client.call_tool(name, args))

        hits = await call("search", query="access token in URI query parameter", doc="RFC 6750", mode="hybrid", k=5)
        for h in hits["results"]:
            print("   ", h["citation"])

        source = None
        for h in hits["results"]:
            refs = await call("resolve_reference", span_id=h["span_id"])
            uri_refs = [r for r in refs["references"] if r.get("target_version", "") and r["target_version"].startswith("uri@")]
            if uri_refs:
                source, target = h, uri_refs[0]
                break
        if source is None:
            sys.exit("FAIL: no RFC 6750 span referencing RFC 3986 found")
        print(f"    {source['citation']} cites {target['raw']} → {target['target_version']} ({target['status']})")

        section_map = await call("get_section_map", doc=target["target_version"], max_depth=1)
        print("    target sections:", ", ".join(f"{s['number']} {s['title']}" for s in section_map["sections"] if s["number"])[:200])

        syntax = await call("read_section", doc=target["target_version"], section="3")
        first = syntax["spans"][0]
        print(f"    {syntax['section']}: {' '.join(first['text'].split())[:160]}")

        evidence = await call("get_evidence", span_id=first["span_id"])
        print(f"    verified={evidence['verified']} sha256={evidence['provenance']['sha256'][:16]}… latest={evidence['is_latest']}")

        check = await call("verify_span", span_id=source["span_id"], deep=True)
        print(f"    source span deep-verified={check['verified']}")

        if not (evidence["verified"] and check["verified"]):
            sys.exit("FAIL: verification failed")
        print("\nPASS: followed RFC 6750 → RFC 3986 via resolve_reference with verified citations")


if __name__ == "__main__":
    asyncio.run(main())
