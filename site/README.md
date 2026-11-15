# DocuSense landing page

Next.js 16 (App Router), exported as a static site. No Tailwind, no runtime server.

```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # static export to ./out
```

Deploy `out/` to any static host. For GitHub Pages under `/docu-sense`, build with
`NEXT_BASE_PATH=/docu-sense npm run build`.

## Layout

- `app/layout.tsx`: fonts (Fraunces, Geist, Geist Mono via `next/font`) and metadata
- `app/page.tsx`: section order
- `app/globals.css`: all styles and design tokens
- `components/sections/content.tsx`: hero, stats, feature sections, how it works, benchmarks, agents, principles
- `components/sections/chrome.tsx`: nav, "still wondering", footer
- `components/sections/mocks.tsx`: tool-call windows shown in the feature tabs (data from `corpus/synthetic`)
- `components/client.tsx`: interactive pieces (pixel scenes, hero prompt, tabs, bars, counters, copy)
- `lib/pixel.ts`: procedural pixel-art landscapes
- `lib/site.ts`: repo and PyPI links
