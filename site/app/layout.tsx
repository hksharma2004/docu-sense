import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Red_Hat_Display } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

const sans = Geist({ subsets: ["latin"], variable: "--font-sans" });
const display = Red_Hat_Display({ subsets: ["latin"], style: ["normal", "italic"], weight: ["600", "700", "800"], variable: "--font-display" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" });

// Absolute URLs for share images. Set NEXT_PUBLIC_SITE_URL to the deployed address.
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://docusense.xyz";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "DocuSense: Agents that quote your documents",
  description:
    "DocuSense is a local MCP server that lets Claude, Cursor and other agents read your documents by section and by claim, with a verified citation for every passage.",
  openGraph: {
    title: "DocuSense: Agents that quote your documents, at a fraction of the tokens",
    description: "Stop pasting whole documents into your agent. 23x less context, every passage cited and hash-verified.",
    type: "website",
    siteName: "DocuSense",
  },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#FAFAF9" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${display.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
