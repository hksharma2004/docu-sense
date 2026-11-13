import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geist = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "DocuSense", template: "%s · DocuSense" },
  description: "Verifiable, version-native document evidence for AI agents.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

const NAV = [
  { href: "/", label: "Documents" },
  { href: "/search", label: "Search" },
  { href: "/contradictions", label: "Contradictions" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geist.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <a
          href="#main"
          className="sr-only z-50 rounded-md bg-fg px-3 py-2 text-sm text-bg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          Skip to Content
        </a>
        <header className="sticky top-0 z-40 border-b border-border bg-bg/80 backdrop-blur-md">
          <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
            <Link href="/" className="flex items-center gap-2 text-[15px] font-semibold tracking-tight" translate="no">
              <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M12 2 22 20H2L12 2Z" fill="currentColor" />
              </svg>
              DocuSense
            </Link>
            <nav aria-label="Primary" className="flex items-center gap-1">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-md px-2.5 py-1.5 text-sm text-fg-muted transition-colors hover:bg-bg-muted hover:text-fg"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">
          {children}
        </main>
        <footer className="border-t border-border">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-[13px] text-fg-subtle sm:px-6">
            <span>Every span is anchored to byte offsets &amp; a SHA-256 hash.</span>
            <span translate="no">MCP · FastAPI · PostgreSQL + pgvector</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
