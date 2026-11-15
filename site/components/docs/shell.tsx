"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ALL_PAGES, DOCS, neighbours, type DocPage } from "@/lib/docs-nav";

const norm = (p: string) => (p.length > 1 ? p.replace(/\/+$/, "") : p);
const GROUP_COLORS = ["rose", "indigo", "lime", "amber", "muted"];

function groupOf(href: string) {
  const i = DOCS.findIndex((g) => g.pages.some((p) => p.href === href));
  return i >= 0 ? { group: DOCS[i], color: GROUP_COLORS[i % GROUP_COLORS.length] } : null;
}

/* ---------------- sidebar (+ mobile drawer) ---------------- */

export function DocsSidebar() {
  const pathname = norm(usePathname());
  const [open, setOpen] = useState(false);
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) { setLastPath(pathname); setOpen(false); } // close the drawer on navigation
  const current = ALL_PAGES.find((p) => p.href === pathname);
  return (
    <>
      <button className="docs-menu" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>{open ? "Close" : "Menu"}</span>
        <span className="docs-menu-cur">{current?.title}</span>
      </button>
      <aside className={`docs-side ${open ? "open" : ""}`}>
        <DocsSearchButton />
        {DOCS.map((g) => (
          <div className="ds-group" key={g.title}>
            <div className="ds-title">{g.title}</div>
            {g.pages.map((p) => (
              <Link key={p.href} href={p.href} className={`ds-link ${p.href === pathname ? "on" : ""}`}>{p.title}</Link>
            ))}
          </div>
        ))}
        <div className="ds-group">
          <div className="ds-title">Links</div>
          <a className="ds-link" href="https://pypi.org/project/docusense-mcp/" target="_blank" rel="noopener">PyPI ↗</a>
        </div>
      </aside>
    </>
  );
}

/* ---------------- page title from the nav config ---------------- */

export function DocTitle() {
  const pathname = norm(usePathname());
  const page = ALL_PAGES.find((p) => p.href === pathname);
  if (!page) return null;
  const g = groupOf(page.href);
  return (
    <header className="doc-head">
      {g && <div className={`eyebrow ${g.color}`}>{g.group.title}</div>}
      <h1 className="doc-h1">{page.title}</h1>
      <p className="doc-lede">{page.desc}</p>
    </header>
  );
}

/** Kept for MDX pages that want a custom header; most pages use DocTitle from the layout. */
export function DocHeader({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: React.ReactNode }) {
  return (
    <header className="doc-head">
      {eyebrow && <div className="eyebrow indigo">{eyebrow}</div>}
      <h1 className="doc-h1">{title}</h1>
      {children && <p className="doc-lede">{children}</p>}
    </header>
  );
}

/* ---------------- on this page (scrollspy) ---------------- */

type Head = { id: string; text: string; level: number };

export function DocsToc() {
  const pathname = usePathname();
  const [heads, setHeads] = useState<Head[]>([]);
  const [active, setActive] = useState("");

  useEffect(() => {
    const els = [...document.querySelectorAll<HTMLElement>(".doc-article h2[id], .doc-article h3[id]")];
    const frame = requestAnimationFrame(() => {
      setHeads(els.map((el) => ({ id: el.id, text: (el.textContent || "").replace(/^#/, ""), level: el.tagName === "H2" ? 2 : 3 })));
      setActive(els[0]?.id ?? "");
    });
    const io = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (vis[0]) setActive(vis[0].target.id);
      },
      { rootMargin: "-80px 0px -65% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => { cancelAnimationFrame(frame); io.disconnect(); };
  }, [pathname]);

  if (!heads.length) return <aside className="docs-toc" />;
  return (
    <aside className="docs-toc">
      <div className="toc-inner">
        <div className="ds-title">On this page</div>
        {heads.map((h) => (
          <a key={h.id} href={`#${h.id}`} className={`toc-link l${h.level} ${active === h.id ? "on" : ""}`}>{h.text}</a>
        ))}
        <div className="toc-foot">
          <a href="#top">Back to top ↑</a>
        </div>
      </div>
    </aside>
  );
}

/* ---------------- prev / next ---------------- */

export function DocsPager() {
  const { prev, next } = neighbours(usePathname());
  return (
    <nav className="pager">
      {prev ? (
        <Link href={prev.href} className="pg prev"><span className="pg-l">← Previous</span><span className="pg-t">{prev.title}</span></Link>
      ) : <span />}
      {next ? (
        <Link href={next.href} className="pg next"><span className="pg-l">Next →</span><span className="pg-t">{next.title}</span></Link>
      ) : <span />}
    </nav>
  );
}

/* ---------------- search (⌘K) ---------------- */

const OPEN_EVENT = "docs-search-open";

export function DocsSearchButton() {
  return (
    <button className="ds-search" onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <span>Search docs</span>
      <kbd>⌘K</kbd>
    </button>
  );
}

function score(p: DocPage, q: string) {
  const hay = `${p.title} ${p.desc} ${p.keywords ?? ""}`.toLowerCase();
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.every((t) => hay.includes(t))) return -1;
  return terms.reduce((s, t) => s + (p.title.toLowerCase().includes(t) ? 3 : 0) + (p.desc.toLowerCase().includes(t) ? 1 : 0), 0);
}

export function DocsSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const show = () => { setOpen(true); setQ(""); setSel(0); };
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); show(); }
      else if (e.key === "/" && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) { e.preventDefault(); show(); }
      else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener(OPEN_EVENT, show);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener(OPEN_EVENT, show); window.removeEventListener("keydown", key); };
  }, []);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);

  const results = useMemo(() => {
    if (!q.trim()) return ALL_PAGES;
    return ALL_PAGES.map((p) => [p, score(p, q)] as const).filter(([, s]) => s >= 0).sort((a, b) => b[1] - a[1]).map(([p]) => p);
  }, [q]);

  if (!open) return null;
  const go = (p?: DocPage) => { if (p) { setOpen(false); router.push(p.href); } };

  return (
    <div className="search-bg" onClick={() => setOpen(false)}>
      <div className="search-box" role="dialog" aria-label="Search docs" onClick={(e) => e.stopPropagation()}>
        <div className="search-in">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <input
            ref={input}
            value={q}
            placeholder="Search tools, commands, concepts…"
            onChange={(e) => { setQ(e.target.value); setSel(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
              else if (e.key === "Enter") go(results[sel]);
            }}
          />
          <kbd>esc</kbd>
        </div>
        <div className="search-res">
          {results.length === 0 && <div className="search-empty">No pages match “{q}”.</div>}
          {results.map((p, i) => {
            const g = groupOf(p.href);
            return (
              <button key={p.href} className={`sr ${i === sel ? "on" : ""}`} onMouseEnter={() => setSel(i)} onClick={() => go(p)}>
                <span className="sr-g">{g?.group.title}</span>
                <span className="sr-t">{p.title}</span>
                <span className="sr-d">{p.desc}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
