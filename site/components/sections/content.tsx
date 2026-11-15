import Link from "next/link";
import type { ReactNode } from "react";
import { BenchRow, CopyButton, CountUp, FeatureTabs, HeroPrompt, PixelScene, Reveal, type FeatureItem } from "@/components/client";
import { ArrowUpRight, FileIcons, I } from "@/components/icons";
import * as M from "@/components/sections/mocks";
import type { SceneName } from "@/lib/pixel";

/* ---------------- hero ---------------- */

export function Hero() {
  return (
    <>
      <section className="hero wrap">
        <h1>Agents that <em>quote</em> your documents,<br className="br-lg" /> at a fraction of the <em>tokens</em></h1>
        <p className="sub">A local MCP server that reads your PDFs, Word files and specs by section and by claim. Every answer cites the exact passage.</p>
        <div className="ctas">
          <Link className="btn" href="/docs">Read the docs</Link>
          <Link className="btn primary" href="/docs/installation#install">Install in 30s</Link>
        </div>
        <div className="hero-cmd">
          <span className="p">$</span> uv tool install <span className="c">docusense-mcp</span>
          <CopyButton text="uv tool install docusense-mcp" />
        </div>
      </section>

      <Reveal className="wrap" as="div">
        <PixelScene scene="alpine" seed={17} className="stage">
          <HeroPrompt />
        </PixelScene>
        <div className="box cells c3 surfaces">
          {[
            { h: "MCP Server", p: <>17 tools your agent calls to browse, search, cite and compare documents. Runs on stdio or HTTP.</>, f: "Tools", href: "/docs/reference/tools" },
            { h: "CLI", p: <>Add files or whole folders, search from the terminal, and run <code>docusense savings</code> to see what you saved.</>, f: "Commands", href: "/docs/reference/cli" },
            { h: "Ledger", p: <>An append-only store. Every passage has a byte range and a SHA-256, and old versions are never overwritten.</>, f: "Versions", href: "/docs/tracking-changes" },
          ].map((c) => (
            <div className="cell" key={c.h}>
              <div className="in"><h3>{c.h}</h3><p>{c.p}</p></div>
              <Link className="foot" href={c.href}>{c.f} <span>→</span></Link>
            </div>
          ))}
        </div>
      </Reveal>
    </>
  );
}

/* ---------------- stats + formats ---------------- */

export function Stats() {
  return (
    <Reveal className="wrap">
      <div className="box">
        <div className="cells c4 stats">
          <div className="cell"><CountUp to={23} suffix="x" /><div className="l">Less context than pasting</div></div>
          <div className="cell"><CountUp to={478} /><div className="l">Tokens for a cited fact</div></div>
          <div className="cell"><CountUp to={100} suffix="%" /><div className="l">Passages hash-verified</div></div>
          <div className="cell"><div className="n">0</div><div className="l">API keys or accounts</div></div>
        </div>
        <div className="band">Reads the files you already have</div>
        <div className="cells c5 formats">
          <div className="cell">{FileIcons.pdf}PDF</div>
          <div className="cell">{FileIcons.word}Word</div>
          <div className="cell">{FileIcons.html}HTML</div>
          <div className="cell">{FileIcons.md}Markdown</div>
          <div className="cell">{FileIcons.txt}Text</div>
        </div>
      </div>
    </Reveal>
  );
}

/* ---------------- feature sections ---------------- */

function Feature({ id, eyebrow, color, title, items, scene, seed, foot, footHref }: {
  id: string; eyebrow: string; color: "rose" | "indigo" | "lime"; title: ReactNode;
  items: FeatureItem[]; scene: SceneName; seed: number; foot: string; footHref: string;
}) {
  return (
    <Reveal className="wrap" id={id}>
      <div className="feat">
        <div className="feat-head">
          <div className={`eyebrow ${color}`}>{eyebrow}</div>
          <h2>{title}</h2>
        </div>
        <FeatureTabs items={items} scene={scene} seed={seed} />
        <Link className="feat-foot" href={footHref}>{foot} →</Link>
      </div>
    </Reveal>
  );
}

export function ReadFeature() {
  return (
    <Feature
      id="read" eyebrow="#01 - Read like a person" color="rose" scene="lake" seed={118}
      title="Table of contents, then the one paragraph that answers."
      foot="All the reading tools" footHref="/docs/reference/tools"
      items={[
        { k: "toc", icon: I.list, title: "Section map", desc: "Your agent sees the outline first, with a token count per section, before it reads a word.", mock: M.tocMock },
        { k: "read", icon: I.book, title: "Read a section", desc: "Open just §3.1, not the 40 pages around it. Subsections load only when asked.", mock: M.readMock },
        { k: "search", icon: I.search, title: "Hybrid search", desc: "Keyword and meaning search fused into one ranking, so exact terms and paraphrases both hit.", mock: M.searchMock },
        { k: "def", icon: I.link, title: "Definitions & references", desc: "Look up a defined term and follow “Section 4.5.3 of RFC 5321” straight to its text.", mock: M.defMock },
      ]}
    />
  );
}

export function CiteFeature() {
  return (
    <Feature
      id="cite" eyebrow="#02 - Citations you can check" color="indigo" scene="hills" seed={219}
      title="Every quote is fingerprinted, so a made-up one can't pass."
      foot="How citations work" footHref="/docs/citations"
      items={[
        { k: "ev", icon: I.shield, title: "Verified evidence", desc: "Each passage carries its byte range and a SHA-256. get_evidence re-hashes before it returns.", mock: M.evidenceMock },
        { k: "pack", icon: I.box, title: "Evidence packing", desc: "Hand over span ids and a token budget. Get back the best evidence that fits, cited.", mock: M.packMock },
        { k: "tamper", icon: I.warn, title: "Tamper check", desc: "If the stored bytes changed, or the quote never existed, the result says verified: false.", mock: M.tamperMock },
      ]}
    />
  );
}

export function VersionsFeature() {
  return (
    <Feature
      id="versions" eyebrow="#03 - Versions & conflicts" color="lime" scene="dusk" seed={320}
      title="Ask what changed. Ask what contradicts. RAG can't."
      foot="Track document changes" footHref="/docs/tracking-changes"
      items={[
        { k: "diff", icon: I.diff, title: "Diff versions", desc: "Add a changed file again and both versions are kept. See only what moved, without loading either.", mock: M.diffMock },
        { k: "blame", icon: I.clock, title: "Blame", desc: "Find the version a rule first appeared in, and what it said before.", mock: M.blameMock },
        { k: "conf", icon: I.swap, title: "Contradictions", desc: "Your policy says one thing, the standard says another. Both sides come back, cited.", mock: M.conflictMock },
        { k: "aff", icon: I.tree, title: "Affected documents", desc: "A standard changed. See every document that cites it, before anything breaks.", mock: M.affectedMock },
      ]}
    />
  );
}

/* ---------------- how it works ---------------- */

const STEPS = [
  { n: "01", h: "Install", p: "One Python package. No server, no account, no API key.", cmd: "uv tool install", arg: "docusense-mcp", rest: "" },
  { n: "02", h: "Connect", p: "Registers the MCP server with Claude Code. Cursor and Claude Desktop work too.", cmd: "docusense", arg: "setup", rest: "" },
  { n: "03", h: "Add", p: "Files or whole folders. Re-add a changed file and you get a new version.", cmd: "docusense", arg: "add", rest: " ~/docs" },
  { n: "04", h: "Ask", p: "Ask your agent about your documents. Then check what it saved you.", cmd: "docusense", arg: "savings", rest: "" },
];

const PIPELINE = [
  { icon: I.file, h: "Parse", tag: "pdf · docx · html · md", body: <>Clean text, page map, and a section tree</> },
  { icon: I.lines, h: "Spans", tag: "byte range + sha256", body: <>Paragraphs, tables and sentences, each fingerprinted</> },
  { icon: I.plus, h: "Extract", tag: "rules first", body: <>Claims like <code>MUST</code> <code>MUST NOT</code>, definitions, references</> },
  { icon: I.searchBold, h: "Index", tag: "bm25 + embeddings", body: <>Fused ranking, served to your agent over MCP</> },
];

export function HowItWorks() {
  return (
    <Reveal className="wrap" id="how">
      <div className="feat">
        <div className="feat-head">
          <div className="eyebrow amber">#04 - How it works</div>
          <h2>Four commands from a folder of files to cited answers.</h2>
        </div>
        <div className="box cells c4 steps">
          {STEPS.map((s) => {
            const full = `${s.cmd} ${s.arg}${s.rest}`;
            return (
              <div className="cell" key={s.n}>
                <div className="num">{s.n}</div>
                <h3>{s.h}</h3>
                <p>{s.p}</p>
                <div className="term"><span className="p">$</span> {s.cmd} <span className="c">{s.arg}</span>{s.rest}<CopyButton text={full} /></div>
              </div>
            );
          })}
        </div>
        <div className="pipe-row">
          <div className="pipe-text">
            <div className="eyebrow muted">Under the hood</div>
            <h3>Parsed once, by rules. Indexed locally. Never overwritten.</h3>
            <p>Parsing and extraction are deterministic. The search model (~130 MB) downloads once and runs on your machine. Nothing leaves it.</p>
            <Link className="btn" href="/docs/quickstart" style={{ alignSelf: "flex-start" }}>Quickstart →</Link>
          </div>
          <PixelScene scene="lake2" seed={421}>
            <div className="flow">
              {PIPELINE.map((n, i) => (
                <div key={n.h} style={{ display: "contents" }}>
                  {i > 0 && <div className="link"><i /><b /><i /></div>}
                  <div className="node">
                    <div className="nh">{n.icon}{n.h}<span>{n.tag}</span></div>
                    <div className="nb">{n.body}</div>
                  </div>
                </div>
              ))}
            </div>
          </PixelScene>
        </div>
      </div>
    </Reveal>
  );
}

/* ---------------- benchmarks ---------------- */

export function Benchmarks() {
  return (
    <Reveal className="wrap" id="bench">
      <div className="box bench">
        <div className="bench-head">
          <div>
            <div className="eyebrow indigo">Benchmarks</div>
            <h2>Same questions. A fraction of the tokens.</h2>
          </div>
          <div className="big"><div className="l">less context than pasting the docs</div><div className="n">23<em>x</em></div></div>
        </div>
        <BenchRow title="A precise fact" sub="with a citation" rows={[
          { who: "Paste", tokens: 9090 }, { who: "Vector RAG", tokens: 5362 }, { who: "DocuSense", tokens: 478, us: true },
        ]} />
        <BenchRow title="What changed" sub="between two versions" rows={[
          { who: "Paste", tokens: 97895 }, { who: "Vector RAG", tokens: 5292, label: "can't diff" }, { who: "DocuSense", tokens: 2776, us: true },
        ]} />
        <BenchRow title="Does A conflict with B?" sub="both sides cited" rows={[
          { who: "Paste", tokens: 53194 }, { who: "Vector RAG", tokens: 5111, label: "hit or miss" }, { who: "DocuSense", tokens: 3615, us: true },
        ]} />
        <div className="bench-foot">Tokens of context the agent loaded per question, measured with scripts/token_demo.py. Totals: 160,179 pasted · 15,765 vector RAG · 6,869 DocuSense. <Link href="/docs/guides/savings" style={{ color: "var(--primary)" }}>Measure your own →</Link></div>
      </div>
    </Reveal>
  );
}

/* ---------------- agents ---------------- */

const AGENTS = [
  { icon: I.terminal, nm: "Claude Code", cmd: "docusense setup", href: "/docs/connect#claude-code" },
  { icon: I.monitor, nm: "Claude Desktop", cmd: "setup claude-desktop", href: "/docs/connect#claude-desktop" },
  { icon: I.cursor, nm: "Cursor", cmd: "docusense setup cursor", href: "/docs/connect#cursor" },
  { icon: I.globe, nm: "Shared over HTTP", cmd: "serve-mcp --http", href: "/docs/guides/team" },
  { icon: I.plug, nm: "Any MCP client", cmd: "docusense setup print", href: "/docs/connect#any-mcp-client" },
  { icon: I.sliders, nm: "Tight context?", cmd: "DOCUSENSE_TOOLS=core", href: "/docs/reference/settings#lighter-tool-set" },
];

export function Agents() {
  return (
    <Reveal className="wrap" id="agents">
      <div className="integ">
        <div className="left">
          <div className="eyebrow indigo">Agentic integrations</div>
          <h2>Works with your favorite agent.</h2>
        </div>
        <div className="grid">
          {AGENTS.map((a) => (
            <Link key={a.nm} href={a.href}>
              <div className="top">{a.icon}<ArrowUpRight className="arr" /></div>
              <div><div className="nm">{a.nm}</div><div className="cmd">{a.cmd}</div></div>
            </Link>
          ))}
        </div>
      </div>
    </Reveal>
  );
}

/* ---------------- principles ---------------- */

const PRINCIPLES = [
  { txt: "Parsing and extraction are rules, not guesses. An LLM fallback exists, but it's off by default and every call it makes is recorded.", b: "Deterministic first", s: "LLM optional", color: "#3F40FA", icon: <><path d="M12 2 3 7v10l9 5 9-5V7z" /><path d="M12 22V12M3 7l9 5 9-5" /></> },
  { txt: "Old evidence is never overwritten. The database itself rejects edits and deletes to versions, sections and spans.", b: "Append-only", s: "Every version kept", color: "#4D7C0F", icon: <><rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></> },
  { txt: "Embedded SQLite and a local search model. No API key, no account, nothing uploaded. If your files already fit in context, you don't need it.", b: "Local & private", s: "No account needed", color: "#E11D74", icon: <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /> },
];

export function Principles() {
  return (
    <Reveal className="wrap">
      <div className="box cells c3 principles">
        {PRINCIPLES.map((p) => (
          <div className="cell" key={p.b}>
            <div className="txt">{p.txt}</div>
            <div className="who">
              <div><b>{p.b}</b><small>{p.s}</small></div>
              <div className="ic">
                <svg viewBox="0 0 24 24" fill="none" stroke={p.color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{p.icon}</svg>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Reveal>
  );
}
