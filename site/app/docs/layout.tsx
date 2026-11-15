import type { Metadata } from "next";
import { Footer, Nav } from "@/components/sections/chrome";
import { DocTitle, DocsPager, DocsSearch, DocsSidebar, DocsToc } from "@/components/docs/shell";
import "./docs.css";

export const metadata: Metadata = {
  title: { default: "Docs · DocuSense", template: "%s · DocuSense docs" },
  description: "Documentation for DocuSense, the local MCP server that lets agents read documents by section and by claim.",
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="docs-page">
      <Nav active="docs" />
      <div className="wrap docs-wrap" id="top">
        <div className="docs-grid">
          <DocsSidebar />
          <main className="docs-main">
            <article className="doc-article">
              <DocTitle />
              {children}
            </article>
            <DocsPager />
          </main>
          <DocsToc />
        </div>
      </div>
      <Footer />
      <DocsSearch />
    </div>
  );
}
