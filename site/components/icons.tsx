import type { ReactNode, SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

const Stroke = ({ children, w = 1.8, ...p }: P & { children: ReactNode; w?: number }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>
    {children}
  </svg>
);

export const ArrowUpRight = (p: P) => <Stroke w={2} {...p}><path d="M7 17 17 7M8 7h9v9" /></Stroke>;
export const ArrowRight = (p: P) => <Stroke w={2} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Stroke>;

export const I = {
  list: <Stroke><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" /></Stroke>,
  book: <Stroke><path d="M2 5h6a4 4 0 0 1 4 4v11a3 3 0 0 0-3-3H2zM22 5h-6a4 4 0 0 0-4 4v11a3 3 0 0 1 3-3h7z" /></Stroke>,
  search: <Stroke><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Stroke>,
  link: <Stroke><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" /><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" /></Stroke>,
  shield: <Stroke><path d="M12 3 4.5 6v5.5c0 4.5 3.2 8.2 7.5 9.5 4.3-1.3 7.5-5 7.5-9.5V6z" /><path d="m9 12 2 2 4-4" /></Stroke>,
  box: <Stroke><path d="M21 8 12 3 3 8v8l9 5 9-5z" /><path d="m3 8 9 5 9-5M12 13v8" /></Stroke>,
  warn: <Stroke><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" /></Stroke>,
  diff: <Stroke><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M6 8.5V15a3 3 0 0 0 3 3h6.5M18 15.5V9a3 3 0 0 0-3-3H8.5" /></Stroke>,
  clock: <Stroke><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Stroke>,
  swap: <Stroke><path d="M7 4 3 8l4 4M3 8h11M17 12l4 4-4 4M21 16H10" /></Stroke>,
  tree: <Stroke><circle cx="12" cy="5" r="2.5" /><circle cx="5" cy="19" r="2.5" /><circle cx="19" cy="19" r="2.5" /><path d="M12 7.5v4M12 11.5 6.5 17M12 11.5l5.5 5.5" /></Stroke>,
  file: <Stroke w={2}><path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z" /><path d="M14 3v5h5" /></Stroke>,
  lines: <Stroke w={2}><path d="M4 6h16M4 12h10M4 18h13" /></Stroke>,
  plus: <Stroke w={2}><path d="M12 3v18M3 12h18" /></Stroke>,
  searchBold: <Stroke w={2}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Stroke>,
  terminal: <Stroke w={1.7}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="m7 10 3 2-3 2M12 15h5" /></Stroke>,
  monitor: <Stroke w={1.7}><rect x="2.5" y="4" width="19" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></Stroke>,
  cursor: <Stroke w={1.7}><path d="M4 4l7 17 2.5-7.5L21 11z" /></Stroke>,
  globe: <Stroke w={1.7}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></Stroke>,
  plug: <Stroke w={1.7}><path d="M9 3v4M15 3v4M7 7h10v4a5 5 0 0 1-10 0zM12 16v5" /></Stroke>,
  sliders: <Stroke w={1.7}><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" /></Stroke>,
};

export const FileIcons = {
  pdf: <svg viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="1.7" strokeLinejoin="round" aria-hidden="true"><path d="M14 3H6.5a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z" /><path d="M14 3v5h5" /></svg>,
  word: <svg viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="1.7" strokeLinejoin="round" aria-hidden="true"><path d="M14 3H6.5a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z" /><path d="M14 3v5h5M8.5 12l1.2 5 1.3-3.5 1.3 3.5 1.2-5" /></svg>,
  html: <svg viewBox="0 0 24 24" fill="none" stroke="#EA580C" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14" /></svg>,
  md: <svg viewBox="0 0 24 24" fill="none" stroke="#292524" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="2.5" y="5.5" width="19" height="13" rx="2" /><path d="M6 15V9l2.5 3L11 9v6M16.5 9v6M14.5 13l2 2 2-2" /></svg>,
  txt: <svg viewBox="0 0 24 24" fill="none" stroke="#78716C" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 10h16M4 14h10M4 18h7" /></svg>,
};

export const Brand = {
  chatgpt: <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 3.5v17M3.5 12h17" /></svg>,
  gemini: <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="#2563EB" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true"><path d="M12 2c.6 5.4 4.6 9.4 10 10-5.4.6-9.4 4.6-10 10-.6-5.4-4.6-9.4-10-10 5.4-.6 9.4-4.6 10-10z" /></svg>,
  claude: <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="#D97757" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4" /></svg>,
  perplexity: <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="#0E7490" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true"><path d="M12 2v20M5 6l7 6 7-6M5 6v12l7-6 7 6V6" /></svg>,
  pypi: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true"><path d="M12 2 3 7v10l9 5 9-5V7z" /><path d="M3 7l9 5 9-5M12 12v10" /></svg>,
};
