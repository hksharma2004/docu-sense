import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, Citation, EmptyState, ErrorState, PageHeader, Skeleton, StatusBadge, VersionBadge, load } from "@/components/ui";
import { api, first, qs } from "@/lib/api";
import type { Contradiction, SpanView } from "@/lib/types";

export const metadata: Metadata = { title: "Contradictions" };

export default function ContradictionsPage({ searchParams }: PageProps<"/contradictions">) {
  return (
    <>
      <PageHeader
        title="Contradictions"
        description="Claims from different documents that can’t both hold. Both sides stay as evidence; DocuSense never picks a winner."
      />
      <Suspense fallback={<ListSkeleton />}>
        <ContradictionList searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function ContradictionList({ searchParams }: { searchParams: PageProps<"/contradictions">["searchParams"] }) {
  const sp = await searchParams;
  const doc = first(sp.doc) ?? "";
  const history = first(sp.history) === "1";
  const rejected = first(sp.rejected) === "1";
  const toggle = (patch: Record<string, string | undefined>) =>
    `/contradictions${qs({ doc, history: history ? "1" : undefined, rejected: rejected ? "1" : undefined, ...patch })}`;

  const res = await load(() =>
    api<{ contradictions: Contradiction[] }>(`/api/contradictions${qs({ doc, history, rejected, k: 60 })}`),
  );

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <FilterLink href={toggle({ history: history ? undefined : "1" })} active={history}>
          Include Obsolete Versions
        </FilterLink>
        <FilterLink href={toggle({ rejected: rejected ? undefined : "1" })} active={rejected}>
          Show Judge-Rejected
        </FilterLink>
        {doc ? (
          <FilterLink href={toggle({ doc: undefined })} active>
            Document: <span translate="no">{doc}</span> ×
          </FilterLink>
        ) : null}
      </div>
      {res.error ? (
        <ErrorState error={res.error} />
      ) : res.data!.contradictions.length === 0 ? (
        <EmptyState title="No Contradictions">Run “uv run docusense conflicts --llm-judge” after ingesting new documents.</EmptyState>
      ) : (
        <ol className="flex flex-col gap-3">
          {res.data!.contradictions.map((c) => (
            <li key={c.conflict_id}>
              <ContradictionCard c={c} />
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

function FilterLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-pressed={active}
      className="inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] text-fg-muted ring-1 ring-border ring-inset hover:bg-bg-muted aria-pressed:bg-fg aria-pressed:text-bg aria-pressed:ring-fg"
    >
      {children}
    </Link>
  );
}

function ContradictionCard({ c }: { c: Contradiction }) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <StatusBadge status={c.status} />
        <Badge tone={c.reason === "value_mismatch" ? "amber" : "blue"}>
          {c.reason === "value_mismatch" ? "Value Mismatch" : "Modality Mismatch"}
        </Badge>
        <span className="text-[13px] text-fg-subtle tabular-nums">score {c.score.toFixed(2)}</span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Side span={c.a} />
        <Side span={c.b} />
      </div>
      {c.judge?.explanation ? (
        <p className="mt-3 border-t border-border pt-3 text-[13px] text-pretty text-fg-muted">
          <span className="font-medium text-fg">Judge:</span> {c.judge.explanation}{" "}
          <span className="text-fg-subtle" translate="no">
            ({c.judge.model_id})
          </span>
        </p>
      ) : null}
    </Card>
  );
}

function Side({ span }: { span: SpanView }) {
  return (
    <div className="min-w-0 rounded-lg bg-bg-subtle p-3 ring-1 ring-border ring-inset">
      <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[13px]">
        <Link
          href={`/docs/${encodeURIComponent(span.version)}?span=${span.span_id}#span-${span.span_id}`}
          className="font-medium underline-offset-4 hover:underline"
        >
          <span translate="no">{span.version}</span> §{span.section}
        </Link>
        <VersionBadge latest={!span.newer_version} newer={span.newer_version} />
      </div>
      <blockquote className="text-sm text-pretty">“{span.text.split(/\s+/).join(" ")}”</blockquote>
      <div className="mt-2">
        <Citation value={span.citation} />
      </div>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading contradictions…">
      <Skeleton className="mb-3 h-8 w-80" />
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i} className="p-4">
          <Skeleton className="h-5 w-48" />
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        </Card>
      ))}
    </div>
  );
}
