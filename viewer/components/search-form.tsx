const MODES = [
  { value: "hybrid", label: "Hybrid" },
  { value: "lexical", label: "Lexical" },
  { value: "semantic", label: "Semantic" },
];

/** Plain GET form: the URL is the state, Enter submits, Back/Forward & sharing just work. */
export function SearchForm({ q = "", mode = "hybrid", doc = "", autoFocus = false }: { q?: string; mode?: string; doc?: string; autoFocus?: boolean }) {
  return (
    <form action="/search" method="get" role="search" className="flex flex-col gap-3">
      <div className="flex gap-2">
        <label htmlFor="q" className="sr-only">
          Search the corpus
        </label>
        <input
          id="q"
          name="q"
          type="search"
          defaultValue={q}
          autoFocus={autoFocus}
          autoComplete="off"
          spellCheck={false}
          placeholder="maximum length of a text line…"
          className="h-10 min-w-0 flex-1 rounded-md bg-bg px-3 text-base shadow-[var(--shadow-card)] placeholder:text-fg-subtle sm:text-sm"
        />
        {doc ? <input type="hidden" name="doc" value={doc} /> : null}
        <button type="submit" className="h-10 rounded-md bg-fg px-4 text-sm font-medium text-bg transition-colors hover:bg-fg/85">
          Search
        </button>
      </div>
      <fieldset className="flex flex-wrap items-center gap-1">
        <legend className="sr-only">Retrieval mode</legend>
        {MODES.map((m) => (
          <label
            key={m.value}
            className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md px-2.5 text-[13px] text-fg-muted ring-1 ring-transparent ring-inset hover:bg-bg-muted has-[:checked]:bg-bg-muted has-[:checked]:text-fg has-[:checked]:ring-border has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-focus"
          >
            <input type="radio" name="mode" value={m.value} defaultChecked={mode === m.value} className="sr-only" />
            {m.label}
          </label>
        ))}
        <span className="ml-1 text-[13px] text-fg-subtle">BM25, embeddings, or both fused</span>
      </fieldset>
    </form>
  );
}
