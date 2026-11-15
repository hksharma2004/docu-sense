// Single source of truth for the docs sidebar, prev/next links and search.

export type DocPage = { href: string; title: string; desc: string; keywords?: string };
export type DocGroup = { title: string; pages: DocPage[] };

export const DOCS: DocGroup[] = [
  {
    title: "Getting started",
    pages: [
      { href: "/docs", title: "Introduction", desc: "What DocuSense does, and when you need it.", keywords: "overview why tokens" },
      { href: "/docs/installation", title: "Installation", desc: "Install DocuSense in one command.", keywords: "install uv pipx upgrade uninstall" },
      { href: "/docs/quickstart", title: "Quickstart", desc: "From a folder of files to cited answers in a minute.", keywords: "start setup add ask savings" },
      { href: "/docs/connect", title: "Connect your agent", desc: "Claude Code, Claude Desktop, Cursor and any MCP client.", keywords: "setup claude code desktop cursor vscode config" },
    ],
  },
  {
    title: "Using DocuSense",
    pages: [
      { href: "/docs/adding-documents", title: "Adding documents", desc: "Add files and folders, and keep every version.", keywords: "add pdf word docx versions folder" },
      { href: "/docs/asking-questions", title: "Asking questions", desc: "How your agent finds the passage that answers.", keywords: "search ask rules definitions sections" },
      { href: "/docs/citations", title: "Citations you can trust", desc: "Every quote points to exact text, and can be checked.", keywords: "citation verify quote evidence" },
      { href: "/docs/tracking-changes", title: "Tracking changes", desc: "See what changed between versions of a document.", keywords: "diff versions changes blame history" },
      { href: "/docs/contradictions", title: "Finding contradictions", desc: "Spot where documents disagree with each other.", keywords: "conflict contradiction compare" },
    ],
  },
  {
    title: "Guides",
    pages: [
      { href: "/docs/guides/policy-audit", title: "Check a policy against a standard", desc: "Find where internal rules break a spec.", keywords: "compliance audit policy standard" },
      { href: "/docs/guides/team", title: "Share with your team", desc: "One document library for several agents.", keywords: "http team share server token" },
      { href: "/docs/guides/savings", title: "See what you saved", desc: "How many tokens DocuSense saved your agents.", keywords: "savings tokens report" },
    ],
  },
  {
    title: "Reference",
    pages: [
      { href: "/docs/reference/tools", title: "Agent tools", desc: "What your agent can do with your documents.", keywords: "tools mcp search read evidence diff" },
      { href: "/docs/reference/cli", title: "Commands", desc: "Every docusense command.", keywords: "cli commands add list verify setup" },
      { href: "/docs/reference/settings", title: "Settings", desc: "Optional settings you can change.", keywords: "env settings configuration folders" },
    ],
  },
  {
    title: "Help",
    pages: [
      { href: "/docs/faq", title: "FAQ & troubleshooting", desc: "Answers to common questions and problems.", keywords: "faq errors help problems privacy" },
    ],
  },
];

export const ALL_PAGES: DocPage[] = DOCS.flatMap((g) => g.pages);

const norm = (p: string) => (p.length > 1 ? p.replace(/\/+$/, "") : p);

export function neighbours(pathname: string) {
  const i = ALL_PAGES.findIndex((p) => p.href === norm(pathname));
  return { prev: i > 0 ? ALL_PAGES[i - 1] : null, next: i >= 0 && i < ALL_PAGES.length - 1 ? ALL_PAGES[i + 1] : null };
}
