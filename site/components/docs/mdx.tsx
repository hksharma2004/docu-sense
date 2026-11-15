import Link from "next/link";
import { Children, isValidElement, type ReactElement, type ReactNode } from "react";
import { CopyButton } from "@/components/client";

/* ---------------- text helpers ---------------- */

export function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

export const slug = (s: string) =>
  s.toLowerCase().replace(/[`'’]/g, "").replace(/[^a-z0-9_]+/g, "-").replace(/^-+|-+$/g, "");

/* ---------------- headings with anchors ---------------- */

function Heading({ as: Tag, children }: { as: "h2" | "h3" | "h4"; children: ReactNode }) {
  const id = slug(textOf(children));
  return (
    <Tag id={id} className="dh">
      <a href={`#${id}`} className="anchor" aria-label="Link to this section">#</a>
      {children}
    </Tag>
  );
}

/* ---------------- tiny syntax highlighter (bash / json / toml-ish) ---------------- */

type Tok = { t: string; c?: string };

function hlBash(line: string): Tok[] {
  if (/^\s*#/.test(line)) return [{ t: line, c: "tk-com" }];
  const out: Tok[] = [];
  let rest = line;
  const prompt = rest.match(/^(\s*\$ )/);
  if (prompt) { out.push({ t: prompt[1], c: "tk-dim" }); rest = rest.slice(prompt[1].length); }
  const re = /(\s+#.*$)|("[^"]*"|'[^']*')|(--?[A-Za-z][\w-]*)|([A-Z_][A-Z0-9_]+=)|(\s+)|([^\s"']+)/g;
  let first = true, m: RegExpExecArray | null;
  while ((m = re.exec(rest))) {
    if (m[1]) out.push({ t: m[1], c: "tk-com" });
    else if (m[2]) out.push({ t: m[2], c: "tk-str" });
    else if (m[3]) out.push({ t: m[3], c: "tk-flag" });
    else if (m[4]) out.push({ t: m[4], c: "tk-key" });
    else if (m[5]) out.push({ t: m[5] });
    else { out.push({ t: m[6], c: first ? "tk-cmd" : undefined }); first = false; }
  }
  return out;
}

function hlJson(line: string): Tok[] {
  const out: Tok[] = [];
  const re = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\b\d+(?:\.\d+)?\b)|(\btrue\b|\bfalse\b|\bnull\b)|([^"\d\-tfn]+|.)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) {
    if (m[1]) { out.push({ t: m[1], c: m[2] ? "tk-key" : "tk-str" }); if (m[2]) out.push({ t: m[2] }); }
    else if (m[3]) out.push({ t: m[3], c: "tk-num" });
    else if (m[4]) out.push({ t: m[4], c: "tk-bool" });
    else out.push({ t: m[5] });
  }
  return out;
}

function hlEnv(line: string): Tok[] {
  if (/^\s*#/.test(line)) return [{ t: line, c: "tk-com" }];
  const m = line.match(/^([A-Z_][A-Z0-9_]*)(=)(.*)$/);
  return m ? [{ t: m[1], c: "tk-key" }, { t: m[2] }, { t: m[3], c: "tk-str" }] : [{ t: line }];
}

function highlight(code: string, lang: string): ReactNode {
  const fn = ["bash", "sh", "shell", "console", "zsh"].includes(lang) ? hlBash : lang === "json" ? hlJson : lang === "env" ? hlEnv : null;
  if (!fn) return code;
  return code.split("\n").map((line, i, arr) => (
    <span key={i}>
      {fn(line).map((tk, j) => (tk.c ? <span key={j} className={tk.c}>{tk.t}</span> : tk.t))}
      {i < arr.length - 1 ? "\n" : null}
    </span>
  ));
}

const LANG_LABEL: Record<string, string> = { bash: "terminal", sh: "terminal", shell: "terminal", console: "terminal", json: "json", env: ".env", text: "output", python: "python", ts: "typescript" };

export function Pre({ children }: { children?: ReactNode }) {
  const code = Children.only(children) as ReactElement<{ className?: string; children?: ReactNode }>;
  const lang = (code.props.className || "").replace("language-", "") || "text";
  const raw = textOf(code.props.children).replace(/\n$/, "");
  const copyText = ["bash", "sh", "shell", "zsh"].includes(lang)
    ? raw.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).map((l) => l.replace(/^\$ /, "").replace(/\s+#.*$/, "")).join("\n")
    : raw;
  return (
    <div className="codeblock">
      <div className="cb-bar"><span>{LANG_LABEL[lang] ?? lang}</span><CopyButton text={copyText} /></div>
      <pre><code>{highlight(raw, lang)}</code></pre>
    </div>
  );
}

/* ---------------- callouts, steps, cards, tool headers ---------------- */

export function Callout({ type = "note", title, children }: { type?: "note" | "tip" | "warning"; title?: string; children: ReactNode }) {
  return (
    <div className={`callout ${type}`}>
      <div className="callout-h">{title ?? type}</div>
      <div className="callout-b">{children}</div>
    </div>
  );
}

export function Steps({ children }: { children: ReactNode }) {
  return <div className="steps-v">{children}</div>;
}

export function Step({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="step-v">
      <div className="step-h">{title}</div>
      <div className="step-b">{children}</div>
    </div>
  );
}

export function Cards({ children }: { children: ReactNode }) {
  return <div className="dcards">{children}</div>;
}

export function Card({ title, href, children }: { title: string; href: string; children: ReactNode }) {
  const external = href.startsWith("http");
  const body = (
    <>
      <div className="dc-h"><span>{title}</span><span className="dc-arr">{external ? "↗" : "→"}</span></div>
      <p>{children}</p>
    </>
  );
  return external ? <a className="dcard" href={href} target="_blank" rel="noopener">{body}</a> : <Link className="dcard" href={href}>{body}</Link>;
}

/** Header strip for one MCP tool in the reference. */
export function Tool({ name, core, writes, children }: { name: string; core?: boolean; writes?: boolean; children?: ReactNode }) {
  return (
    <div className="tool" id={name}>
      <div className="tool-h">
        <a href={`#${name}`} className="tool-name">{name}</a>
        <span className="tool-tags">
          {core && <span className="tag ind">core</span>}
          <span className={`tag ${writes ? "bad" : "ok"}`}>{writes ? "writes" : "read-only"}</span>
        </span>
      </div>
      {children && <div className="tool-b">{children}</div>}
    </div>
  );
}

export function A({ href = "", children }: { href?: string; children?: ReactNode }) {
  if (href.startsWith("/")) return <Link href={href}>{children}</Link>;
  if (href.startsWith("#")) return <a href={href}>{children}</a>;
  return <a href={href} target="_blank" rel="noopener">{children}</a>;
}

export const H2 = ({ children }: { children?: ReactNode }) => <Heading as="h2">{children}</Heading>;
export const H3 = ({ children }: { children?: ReactNode }) => <Heading as="h3">{children}</Heading>;
export const H4 = ({ children }: { children?: ReactNode }) => <Heading as="h4">{children}</Heading>;
export const Table = ({ children }: { children?: ReactNode }) => <div className="dtable"><table>{children}</table></div>;
