import type { NextConfig } from "next";
import createMDX from "@next/mdx";

// static export: `npm run build` writes a plain html site to ./out (any static host)
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  pageExtensions: ["ts", "tsx", "mdx"],
  // for github pages under /docu-sense, set NEXT_BASE_PATH=/docu-sense at build time
  basePath: process.env.NEXT_BASE_PATH || undefined,
};

// plugins passed by name so they work under turbopack
const withMDX = createMDX({
  options: { remarkPlugins: [["remark-gfm"]] },
});

export default withMDX(nextConfig);
