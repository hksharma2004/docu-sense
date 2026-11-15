import Image from "next/image";
import Link from "next/link";
import wordmark from "@/assets/brand/wordmark.png";
import { ArrowRight, ArrowUpRight, Brand } from "@/components/icons";
import { Reveal } from "@/components/client";
import { ASK_PROMPT, PYPI } from "@/lib/site";

const ext = { target: "_blank", rel: "noopener" } as const;

export function Nav({ active }: { active?: "docs" } = {}) {
  return (
    <header className="nav">
      <div className="wrap">
        <Link href="/" className="logo" aria-label="DocuSense home"><Image src={wordmark} alt="DocuSense" priority /></Link>
        <nav className="nav-links">
          <Link href="/#how">How it works</Link>
          <Link href="/#read">Features</Link>
          <Link href="/#bench">Benchmarks</Link>
          <Link href="/#agents">Agents</Link>
          <Link href="/docs" className={active === "docs" ? "on" : ""}>Docs</Link>
        </nav>
        <div className="nav-cta">
          <Link className="btn" href="/docs/quickstart">Quickstart</Link>
          <Link className="btn primary" href="/docs/installation">Install</Link>
        </div>
      </div>
    </header>
  );
}

const ASKS = [
  { name: "Ask ChatGPT", icon: Brand.chatgpt, base: "https://chat.openai.com/?q=" },
  { name: "Ask Gemini", icon: Brand.gemini, base: "https://www.google.com/search?udm=50&q=" },
  { name: "Ask Claude", icon: Brand.claude, base: "https://claude.ai/new?q=" },
  { name: "Ask Perplexity", icon: Brand.perplexity, base: "https://www.perplexity.ai/?q=" },
];

export function Ask() {
  return (
    <Reveal className="wrap">
      <div className="ask">
        <div className="left">
          <h3>Still wondering?</h3>
          <p>Ask your favorite LLM what it thinks of DocuSense, then make an informed decision.</p>
        </div>
        <div className="opts">
          {ASKS.map((a) => (
            <a key={a.name} href={a.base + encodeURIComponent(ASK_PROMPT)} {...ext}>
              {a.icon}{a.name}<ArrowUpRight className="arr" />
            </a>
          ))}
          <Link className="wide" href="/docs">Read the docs<ArrowRight className="arr" /></Link>
        </div>
      </div>
    </Reveal>
  );
}

const COLS: { h: string; links: [string, string][] }[] = [
  { h: "Product", links: [["How it works", "/#how"], ["Features", "/#read"], ["Benchmarks", "/#bench"], ["Agents", "/#agents"], ["Install", "/docs/installation"]] },
  { h: "Docs", links: [["Introduction", "/docs"], ["Quickstart", "/docs/quickstart"], ["Connect your agent", "/docs/connect"], ["Tracking changes", "/docs/tracking-changes"], ["FAQ", "/docs/faq"]] },
  { h: "Reference", links: [["Agent tools", "/docs/reference/tools"], ["Commands", "/docs/reference/cli"], ["Settings", "/docs/reference/settings"], ["Your savings", "/docs/guides/savings"]] },
];

export function Footer() {
  return (
    <footer className="site-foot">
      <div className="wrap">
        <div className="ft-top">
          <div className="ft-brand">
            <Link href="/" className="logo" aria-label="DocuSense home"><Image src={wordmark} alt="DocuSense" /></Link>
            <p>Your agent reads the section, not the whole file. Every answer cited to the exact passage, on your machine.</p>
          </div>
          <div className="ft-cols">
            {COLS.map((c) => (
              <div className="ft-col" key={c.h}>
                <span className="ft-h">{c.h}</span>
                {c.links.map(([label, href]) => (
                  href.startsWith("http")
                    ? <a key={label} href={href} {...ext}>{label}</a>
                    : <Link key={label} href={href}>{label}</Link>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div className="ft-bot">
          <span>© 2026 DocuSense. Runs 100% on your machine.</span>
          <div className="ft-social">
            <a href={PYPI} {...ext} aria-label="PyPI">{Brand.pypi}</a>
          </div>
        </div>
      </div>
      <div className="ft-giant" aria-hidden="true"><span>docusense</span></div>
    </footer>
  );
}
