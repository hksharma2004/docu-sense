import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, ErrorState, PageHeader, Skeleton, VersionBadge, load } from "@/components/ui";
import { SearchForm } from "@/components/search-form";
import { api } from "@/lib/api";
import type { DocumentEntry } from "@/lib/types";

export default function Home() {
  return (
    <>
      <PageHeader
        title="Documents"
        description="Versioned RFCs & policy documents, parsed into verifiable spans. Open a version to read it, or compare versions to see what changed."
      />
      <div className="mb-8 max-w-2xl">
        <SearchForm />
      </div>
      <Suspense fallback={<DocumentsSkeleton />}>
        <DocumentList />
      </Suspense>
    </>
  );
}

async function DocumentList() {
  const { data, error } = await load(() => api<{ documents: DocumentEntry[] }>("/api/documents"));
  if (error) return <ErrorState error={error} />;
  const docs = data!.documents;
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {docs.map((d) => {
        const latest = d.versions.find((v) => v.is_latest)!;
        return (
          <li key={d.document}>
            <Card className="flex h-full flex-col p-4">
              <div className="flex items-start justify-between gap-3">
                <Link
                  href={`/docs/${latest.version_id}`}
                  className="font-medium text-pretty underline-offset-4 hover:underline"
                >
                  {d.title}
                </Link>
                {d.family === "synthetic" ? <Badge tone="amber">Synthetic</Badge> : null}
              </div>
              <p className="mt-1 text-[13px] text-fg-subtle" translate="no">
                {d.document}
              </p>
              <ol className="mt-4 flex flex-wrap items-center gap-1.5" aria-label="Versions, oldest to newest">
                {d.versions.map((v, i) => (
                  <li key={v.version_id} className="flex items-center gap-1.5">
                    {i > 0 ? <span aria-hidden="true" className="text-fg-subtle">→</span> : null}
                    <Link
                      href={`/docs/${v.version_id}`}
                      className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[13px] ring-1 ring-border ring-inset hover:bg-bg-muted"
                      translate="no"
                    >
                      {v.label.toUpperCase()}
                      <span className="text-fg-subtle tabular-nums">{v.pages}&nbsp;pp</span>
                    </Link>
                  </li>
                ))}
              </ol>
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
                <VersionBadge latest />
                {d.versions.length > 1 ? (
                  <Link href={`/diff/${d.document}`} className="text-[13px] text-fg-muted underline-offset-4 hover:text-fg hover:underline">
                    Compare {d.versions.length} Versions
                  </Link>
                ) : (
                  <span className="text-[13px] text-fg-subtle">1 version</span>
                )}
              </div>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

function DocumentsSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label="Loading documents…">
      {Array.from({ length: 9 }).map((_, i) => (
        <Card key={i} className="h-[150px] p-4">
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="mt-2 h-4 w-1/3" />
          <Skeleton className="mt-5 h-7 w-1/2" />
        </Card>
      ))}
    </div>
  );
}
