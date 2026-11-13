import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SearchForm } from "@/components/search-form";
import { Card, Citation, EmptyState, ErrorState, PageHeader, Skeleton, VersionBadge, load } from "@/components/ui";
import { api, first, qs } from "@/lib/api";
import type { SpanView } from "@/lib/types";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage({ searchParams }: PageProps<"/search">) {
  return (
    <>
      <PageHeader title="Search" description="Find evidence across every version. Results link to the exact span, with its citation & hash." />
      <Suspense fallback={<Results.Skeleton />}>
        <Results searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function Results({ searchParams }: { searchParams: PageProps<"/search">["searchParams"] }) {
  const sp = await searchParams;
  const q = first(sp.q)?.trim() ?? "";
  const mode = first(sp.mode) ?? "hybrid";
  const doc = first(sp.doc) ?? "";

  const form = (
    <div className="mb-8 max-w-2xl">
      <SearchForm q={q} mode={mode} doc={doc} autoFocus={!q} />
    </div>
  );
  if (!q) {
    return (
      <>
        {form}
        <EmptyState title="Search the Corpus">
          Try “implicit grant”, “maximum length of a text line” or “code_verifier minimum length”.
        </EmptyState>
      </>
    );
  }

  const { data, error } = await load(() => api<{ results: SpanView[] }>(`/api/search${qs({ q, mode, doc, k: 15 })}`));
  if (error) return (<>{form}<ErrorState error={error} /></>);
  const results = data!.results;

  return (
    <>
      {form}
      <p className="mb-3 text-sm text-fg-muted" aria-live="polite">
        <span className="tabular-nums">{results.length}</span> results for “{q}” · {mode}
        {doc ? <> · in <span translate="no">{doc}</span></> : null}
      </p>
      {results.length === 0 ? (
        <EmptyState title="No Matching Spans">Try fewer words, or switch to Semantic mode for paraphrased questions.</EmptyState>
      ) : (
        <ol className="flex flex-col gap-3">
          {results.map((r) => (
            <li key={r.span_id}>
              <Card className="p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/docs/${r.version}?span=${r.span_id}#span-${r.span_id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    <span translate="no">{r.version}</span> · §{r.section}
                  </Link>
                  <VersionBadge latest={!r.newer_version} newer={r.newer_version} />
                  <span className="text-[13px] text-fg-subtle tabular-nums">p.&nbsp;{r.page}</span>
                </div>
                <p className="mt-2 line-clamp-4 text-sm text-pretty text-fg-muted">{r.text.split(/\s+/).join(" ")}</p>
                <div className="mt-2">
                  <Citation value={r.citation} />
                </div>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

Results.Skeleton = function ResultsSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading results…">
      <Skeleton className="mb-8 h-[84px] max-w-2xl" />
      <div className="flex flex-col gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="h-[132px] p-4">
            <Skeleton className="h-5 w-1/3" />
            <Skeleton className="mt-3 h-4 w-full" />
            <Skeleton className="mt-2 h-4 w-5/6" />
          </Card>
        ))}
      </div>
    </div>
  );
};
