"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { paintScene, type SceneName } from "@/lib/pixel";

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Calls `onEnter` once the element scrolls into view. */
function useInView<T extends Element>(onEnter: () => void, threshold = 0.12) {
  const ref = useRef<T>(null);
  const cb = useRef(onEnter);
  useEffect(() => { cb.current = onEnter; });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) { cb.current(); io.disconnect(); } }),
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return ref;
}

/* ---------------- pixel-art scene ---------------- */

export function PixelScene({ scene, seed, className = "", children }: { scene: SceneName; seed: number; className?: string; children?: ReactNode }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = canvas.current;
    if (!c?.parentElement) return;
    let t: ReturnType<typeof setTimeout>;
    let lastW = 0, lastH = 0;
    const draw = () => {
      const p = c.parentElement!;
      if (p.clientWidth === lastW && p.clientHeight === lastH) return;
      lastW = p.clientWidth; lastH = p.clientHeight;
      paintScene(c, scene, seed);
    };
    draw();
    const ro = new ResizeObserver(() => { clearTimeout(t); t = setTimeout(draw, 120); });
    ro.observe(c.parentElement);
    return () => { ro.disconnect(); clearTimeout(t); };
  }, [scene, seed]);
  return (
    <div className={`scene ${className}`}>
      <canvas ref={canvas} aria-hidden="true" />
      {children}
    </div>
  );
}

/* ---------------- scroll reveal ---------------- */

export function Reveal({ children, className = "", id, as: Tag = "section" }: { children: ReactNode; className?: string; id?: string; as?: "section" | "div" }) {
  const [shown, setShown] = useState(false);
  const ref = useInView<HTMLElement>(() => setShown(true));
  return (
    <Tag ref={ref as never} id={id} className={`rv ${shown ? "in" : ""} ${className}`}>
      {children}
    </Tag>
  );
}

/* ---------------- hero prompt (types a question, shows a cited answer) ---------------- */

const QA = [
  { q: "What's the max line length in our mail policy, and does it match RFC 5321?", a: "Yes. v2 says a line MUST NOT exceed 1000 octets, matching RFC 5321 §4.5.3.1.6.", c: "ds://mail-policy@v2#§3.1:b812-951", t: "478 tokens" },
  { q: "What changed between v1 and v2 of the mail policy?", a: "Line length 2000 → 1000 octets, recipients ≥100, retry 10 → 15 min, and STARTTLS is now required.", c: "diff mail-policy v1 → v2", t: "2,776 tokens" },
  { q: "Does anything in our policy contradict the SMTP standard?", a: "One conflict: §4.2 gives up after 2 days, RFC 5321 §4.5.4.1 says at least 4-5 days.", c: "ds://mail-policy@v2#§4.2:b1530-1611", t: "3,615 tokens" },
];

export function HeroPrompt() {
  const [typed, setTyped] = useState("");
  const [shown, setShown] = useState<number | null>(null);
  const [cur, setCur] = useState(0);

  useEffect(() => {
    let alive = true;
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const reduce = prefersReducedMotion();
    (async () => {
      for (let i = 0; alive; i = (i + 1) % QA.length) {
        const { q } = QA[i];
        setCur(i); setShown(null); setTyped("");
        if (reduce) setTyped(q);
        else for (let n = 1; n <= q.length && alive; n++) { setTyped(q.slice(0, n)); await sleep(28 + Math.random() * 30); }
        await sleep(500);
        if (!alive) return;
        setShown(i);
        await sleep(4200);
        if (!reduce) for (let n = q.length; n > 0 && alive; n -= 3) { setTyped(q.slice(0, n)); await sleep(12); }
      }
    })();
    return () => { alive = false; };
  }, []);

  const qa = QA[shown ?? cur];
  return (
    <div className="prompt">
      <div className={`answer ${shown !== null ? "show" : ""}`} aria-live="polite">
        {qa.a}
        <br />
        <span className="cite">✓ {qa.c}</span>
        <span className="meta">{qa.t}</span>
      </div>
      <div className="q">{typed}</div>
      <div className="row">
        <div className="plus">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
        </div>
        <div className="chips"><span className="chip">@mail-policy</span><span className="chip">@rfc5321</span></div>
        <div className="send">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
        </div>
      </div>
    </div>
  );
}

/* ---------------- feature tabs (auto-rotating, AutoSend-style progress bar) ---------------- */

export type FeatureItem = { k: string; title: string; desc: string; icon: ReactNode; mock: ReactNode };

const DUR = 7000;

export function FeatureTabs({ items, scene, seed }: { items: FeatureItem[]; scene: SceneName; seed: number }) {
  const [idx, setIdx] = useState(0);
  const [cycle, setCycle] = useState(0);
  const [manual, setManual] = useState(false);
  const [visible, setVisible] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || manual || prefersReducedMotion()) return;
    const t = setTimeout(() => { setIdx((i) => (i + 1) % items.length); setCycle((c) => c + 1); }, DUR);
    return () => clearTimeout(t);
  }, [visible, manual, idx, cycle, items.length]);

  const active = items[idx];
  return (
    <div className="feat-body" ref={root} style={{ ["--dur" as string]: `${DUR}ms` }}>
      <div className="items" role="tablist">
        {items.map((it, i) => (
          <button
            key={i === idx ? `${it.k}-${cycle}-${visible}` : it.k}
            role="tab"
            aria-selected={i === idx}
            className={`item ${i === idx && visible ? "on" : ""} ${manual ? "stuck" : ""}`}
            onClick={() => { setManual(true); setIdx(i); }}
          >
            {it.icon}
            <div><h4>{it.title}</h4><p>{it.desc}</p></div>
          </button>
        ))}
      </div>
      <div className="visual">
        <PixelScene scene={scene} seed={seed}>
          <div className="win">
            <div className="bar"><i /><i /><i /><span>claude · docusense</span></div>
            <div className="mock" key={active.k} role="tabpanel">{active.mock}</div>
          </div>
        </PixelScene>
      </div>
    </div>
  );
}

/* ---------------- benchmark bars ---------------- */

export function BenchRow({ title, sub, rows }: { title: string; sub: string; rows: { who: string; tokens: number; label?: string; us?: boolean }[] }) {
  const [on, setOn] = useState(false);
  const ref = useInView<HTMLDivElement>(() => setOn(true), 0.4);
  const max = Math.max(...rows.map((r) => r.tokens));
  return (
    <div className="brow" ref={ref}>
      <div className="q"><h4>{title}</h4><p>{sub}</p></div>
      <div className="bars">
        {rows.map((r) => (
          <div key={r.who} className={`bar-l ${r.us ? "us" : ""}`}>
            <span className="who">{r.who}</span>
            <span className="track"><b style={{ width: on ? `${Math.max(0.6, (r.tokens / max) * 100)}%` : 0 }} /></span>
            <span className="v">{r.label ?? r.tokens.toLocaleString("en-US")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- count-up number ---------------- */

export function CountUp({ to, suffix = "" }: { to: number; suffix?: string }) {
  const [v, setV] = useState(to);
  const ref = useInView<HTMLDivElement>(() => {
    if (prefersReducedMotion()) return;
    let start: number | null = null;
    const step = (ts: number) => {
      start ??= ts;
      const p = Math.min(1, (ts - start) / 1100);
      setV(Math.round(to * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(step);
    };
    // First frame resets to 0, so if frames never run (background tab) the final value stays.
    requestAnimationFrame(step);
  }, 0.6);
  return <div className="n" ref={ref}>{v.toLocaleString("en-US")}{suffix}</div>;
}

/* ---------------- copy button ---------------- */

export function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="copy"
      onClick={async () => {
        try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1200); } catch {}
      }}
    >
      {done ? "copied" : "copy"}
    </button>
  );
}
