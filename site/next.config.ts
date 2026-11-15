import type { NextConfig } from "next";
import createMDX from "@next/mdx";

// Static export: `npm run build` writes a plain HTML site to ./out
// (deployable to GitHub Pages, Vercel, Netlify, any static host).
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  pageExtensions: ["ts", "tsx", "mdx"],
  // For GitHub Pages under /docu-sense, set NEXT_BASE_PATH=/docu-sense at build time.
  basePath: process.env.NEXT_BASE_PATH || undefined,
};

// Plugins are passed by name so they work under Turbopack.
const withMDX = createMDX({
  options: { remarkPlugins: [["remark-gfm"]] },
});

export default withMDX(nextConfig);
