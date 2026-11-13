import Link from "next/link";
import { Suspense } from "react";

import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton, Stat, StatusBadge, load } from "@/components/ui";
import { api, first, qs } from "@/lib/api";
import type { ClaimDiff, ClaimView, RefDiff, SectionDiff, SectionDiffRow } from "@/lib/types";

const LEVELS = [
  { value: "section", label: "Sections" },
  { value: "claim", label: "Claims" },
  { value: "reference", label: "References" },
];

export async function generateMetadata({ params }: PageProps<"/diff/[doc]">) {
  const { doc } = await params;
  return { title: `Compare ${doc}` };
}

export default function DiffPage({ params, searchParams }: PageProps<"/diff/[doc]">) {
  return (
    <Suspense fallback={<DiffSkeleton />}>
      <DiffView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

type Versions = { versions: { version_id: string; label: string; seq: number; is_latest: boolean; declares: string[] }[] };

async function DiffView({ params, searchParams }: PageProps<"/diff/[doc]">) {
  const { doc } = await params;
  const sp = await searchParams;
  const level = first(sp.level) ?? "section";
  const versionsRes = await load(() => api<Versions>(`/api/documents/${doc}/versions`));
  if (versionsRes.error) return <ErrorState error={versionsRes.error} />;
  const versions = versionsRes.data!.versions;
  if (versions.length < 2) {
    return (
      <>
        <PageHeader title={`Compare ${doc}`} />
        <EmptyState title="Only 1 Version">
          <Link href={`/docs/${versions[0].version_id}`} className="underline underline-offset-4">
            Read {versions[0].version_id}
          </Link>{" "}
          instead.
        </EmptyState>
      </>
    );
  }
  const to = first(sp.to) ?? versions.at(-1)!.label;
  const toSeq = versions.find((v) => v.label === to)?.seq ?? versions.at(-1)!.seq;
  const from = first(sp.from) ?? versions.filter((v) => v.seq < toSeq).at(-1)?.label ?? versions[0].label;
  const link = (patch: Record<string, string>) => `/diff/${doc}${qs({ from, to, level, ...patch })}`;

  return (
    <>
      <PageHeader
        title={
          <>
            Compare <span translate="no">{doc}</span>
          </>
        }
        description="Section-, claim- & reference-level changes between two versions. Earlier versions stay stored; nothing is overwritten."
      />

      <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-3">
        <VersionPicker label="From" versions={versions} current={from} href={(label) => link({ from: label })} />
        <span aria-hidden="true" className="text-fg-subtle">→</span>
        <VersionPicker label="To" versions={versions} current={to} href={(label) => link({ to: label })} />
      </div>

      <nav aria-label="Diff level" className="mb-6 flex gap-1 border-b border-border">
        {LEVELS.map((l) => (
          <Link
            key={l.value}
            href={link({ level: l.value })}
            aria-current={level === l.value ? "page" : undefined}
            className="-mb-px inline-flex h-10 items-center border-b-2 border-transparent px-3 text-sm text-fg-muted hover:text-fg aria-[current=page]:border-fg aria-[current=page]:font-medium aria-[current=page]:text-fg"
          >
            {l.label}
          </Link>
        ))}
      </nav>

      <Suspense key={`${from}-${to}-${level}`} fallback={<DiffSkeleton.Body />}>
        <DiffBody doc={doc} from={from} to={to} level={level} />
      </Suspense>
    </>
  );
}

function VersionPicker({ label, versions, current, href }: { label: string; versions: Versions["versions"]; current: string; href: (label: string) => string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[13px] text-fg-subtle">{label}</span>
      <div className="flex gap-1">
        {versions.map((v) => (
          <Link
            key={v.label}
            href={href(v.label)}
            aria-current={v.label === current ? "true" : undefined}
            translate="no"
            className="inline-flex h-8 items-center rounded-md px-2.5 text-[13px] text-fg-muted ring-1 ring-border ring-inset hover:bg-bg-muted aria-[current=true]:bg-fg aria-[current=true]:text-bg aria-[current=true]:ring-fg"
          >
            {v.label.toUpperCase()}
          </Link>
        ))}
      </div>
    </div>
  );
}

async function DiffBody({ doc, from, to, level }: { doc: string; from: string; to: string; level: string }) {
  if (from === to) return <EmptyState title="Same Version Selected">Pick two different versions to compare.</EmptyState>;
  const res = await load(() => api<SectionDiff | ClaimDiff | RefDiff>(`/api/diff${qs({ doc, from, to, level })}`));
  if (res.error) return <ErrorState error={res.error} />;
  if (level === "claim") return <ClaimDiffView d={res.data as ClaimDiff} />;
  if (level === "reference") return <RefDiffView d={res.data as RefDiff} />;
  return <SectionDiffView d={res.data as SectionDiff} />;
}

function SectionDiffView({ d }: { d: SectionDiff }) {
  const s = d.summary;
  return (
    <>
      <Card className="mb-6 grid grid-cols-2 divide-x divide-border sm:grid-cols-4">
        <Stat label="Modified" value={s.modified} tone="amber" />
        <Stat label="Added" value={s.added} tone="green" />
        <Stat label="Removed" value={s.removed} tone="red" />
        <Stat label="Unchanged" value={s.unchanged} />
      </Card>
      {d.sections.length === 0 ? (
        <EmptyState title="No Section Changes" />
      ) : (
        <ol className="flex flex-col gap-2">
          {d.sections.map((row, i) => (
            <li key={i}>
              <SectionRow row={row} from={d.from} to={d.to} />
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

function SectionRow({ row, from, to }: { row: SectionDiffRow; from: string; to: string }) {
  const label = (
    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <StatusBadge status={row.status} />
      <span className="min-w-0 font-medium text-pretty">{row.new ?? row.old}</span>
      {row.renumbered && row.old && row.new ? <span className="text-[13px] text-fg-subtle">was {row.old}</span> : null}
    </span>
  );
  const links = (
    <span className="flex shrink-0 gap-3 text-[13px]">
      {row.old_section_id ? (
        <Link href={`/docs/${encodeURIComponent(from)}#s-${row.old_section_id}`} className="text-fg-muted underline-offset-4 hover:text-fg hover:underline">
          Old
        </Link>
      ) : null}
      {row.new_section_id ? (
        <Link href={`/docs/${encodeURIComponent(to)}#s-${row.new_section_id}`} className="text-fg-muted underline-offset-4 hover:text-fg hover:underline">
          New
        </Link>
      ) : null}
    </span>
  );

  if (row.status !== "modified" || !row.changes) {
    return (
      <Card className="flex items-center justify-between gap-3 px-4 py-3">
        {label}
        {links}
      </Card>
    );
  }
  return (
    <Card>
      <details>
        <summary className="flex min-h-12 cursor-pointer items-center justify-between gap-3 rounded-xl px-4 py-3 hover:bg-bg-subtle">
          <span className="flex min-w-0 items-center gap-2">
            <span aria-hidden="true" className="chevron inline-block text-fg-subtle">›</span>
            {label}
          </span>
          <span className="flex shrink-0 items-center gap-3">
            <span className="text-[13px] text-fg-subtle tabular-nums">{Math.round((row.similarity ?? 0) * 100)}% similar</span>
          </span>
        </summary>
        <div className="flex flex-col gap-2 border-t border-border px-4 py-3">
          {row.changes.removed.map((t, i) => (
            <ChangeLine key={`r${i}`} kind="removed" text={t} />
          ))}
          {row.changes.added.map((t, i) => (
            <ChangeLine key={`a${i}`} kind="added" text={t} />
          ))}
          {row.changes.added.length + row.changes.removed.length === 0 ? (
            <p className="text-[13px] text-fg-subtle">Whitespace or layout changes only.</p>
          ) : null}
          <div className="pt-1">{links}</div>
        </div>
      </details>
    </Card>
  );
}

function ChangeLine({ kind, text }: { kind: "added" | "removed"; text: string }) {
  const style =
    kind === "added"
      ? "bg-[var(--green-bg)] ring-[var(--green-border)]"
      : "bg-[var(--red-bg)] ring-[var(--red-border)]";
  return (
    <p className={`grid grid-cols-[auto_1fr] gap-2 rounded-md px-3 py-2 text-sm ring-1 ring-inset ${style}`}>
      <span className={kind === "added" ? "text-[var(--green-fg)]" : "text-[var(--red-fg)]"}>
        <span aria-hidden="true">{kind === "added" ? "+" : "−"}</span>
        <span className="sr-only">{kind === "added" ? "Added:" : "Removed:"}</span>
      </span>
      <span className="text-pretty">{text}</span>
    </p>
  );
}

function ClaimDiffView({ d }: { d: ClaimDiff }) {
  const s = d.summary;
  return (
    <>
      <Card className="mb-6 grid grid-cols-2 divide-x divide-border sm:grid-cols-5">
        <Stat label="Modality Changed" value={s.modality_changed} tone="red" />
        <Stat label="Value Changed" value={s.value_changed} tone="red" />
        <Stat label="Reworded" value={s.changed - s.modality_changed - s.value_changed} tone="amber" />
        <Stat label="Added" value={s.added} tone="green" />
        <Stat label="Removed" value={s.removed} tone="red" />
      </Card>
      <h2 className="mb-3 text-[15px] font-semibold">Changed Claims</h2>
      {d.changed.length === 0 ? <EmptyState title="No Changed Claims" /> : null}
      <ol className="mb-8 flex flex-col gap-2">
        {d.changed.map((c, i) => (
          <li key={i}>
            <Card className="p-4">
              <div className="mb-3 flex flex-wrap gap-1.5">
                {c.change.map((k) => (
                  <Badge key={k} tone={k === "reworded" ? "amber" : "red"}>
                    {k === "modality_changed" ? "Modality Changed" : k === "value_changed" ? "Value Changed" : "Reworded"}
                  </Badge>
                ))}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <ClaimSide claim={c.old} version={d.from} label="Before" />
                <ClaimSide claim={c.new} version={d.to} label="After" />
              </div>
            </Card>
          </li>
        ))}
      </ol>
      <div className="grid gap-6 md:grid-cols-2">
        <ClaimList title="Added Claims" claims={d.added} version={d.to} kind="added" />
        <ClaimList title="Removed Claims" claims={d.removed} version={d.from} kind="removed" />
      </div>
    </>
  );
}

function ClaimSide({ claim, version, label }: { claim: ClaimView; version: string; label: string }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 flex flex-wrap items-center gap-2 text-[13px]">
        <span className="text-fg-subtle">{label}</span>
        {claim.modality ? <Badge tone="blue">{claim.modality}</Badge> : null}
        {claim.value !== null ? (
          <Badge>
            {claim.value}&nbsp;{claim.unit}
          </Badge>
        ) : null}
      </div>
      <Link
        href={`/docs/${encodeURIComponent(version)}?span=${claim.span_id}#span-${claim.span_id}`}
        className="text-sm text-pretty underline-offset-4 hover:underline"
      >
        {claim.text}
      </Link>
      {claim.section ? <p className="mt-1 text-[13px] text-fg-subtle">§{claim.section}</p> : null}
    </div>
  );
}

function ClaimList({ title, claims, version, kind }: { title: string; claims: ClaimView[]; version: string; kind: "added" | "removed" }) {
  return (
    <section>
      <h2 className="mb-3 text-[15px] font-semibold">
        {title} <span className="text-fg-subtle tabular-nums">({claims.length})</span>
      </h2>
      {claims.length === 0 ? (
        <EmptyState title="None" />
      ) : (
        <ol className="flex flex-col gap-2">
          {claims.map((c) => (
            <li key={c.span_id}>
              <Link href={`/docs/${encodeURIComponent(version)}?span=${c.span_id}#span-${c.span_id}`} className="block rounded-md hover:bg-bg-subtle">
                <ChangeLine kind={kind} text={c.text} />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function RefDiffView({ d }: { d: RefDiff }) {
  const list = (items: RefDiff["added"], kind: "added" | "removed") =>
    items.length === 0 ? (
      <EmptyState title="None" />
    ) : (
      <ul className="flex flex-col gap-1.5">
        {items.map((r) => (
          <li key={`${r.relation}-${r.target}`} className="flex items-center gap-2 text-sm">
            <StatusBadge status={kind} />
            <span translate="no">{r.target}</span>
            <span className="text-fg-subtle">{r.relation}</span>
          </li>
        ))}
      </ul>
    );
  return (
    <>
      <Card className="mb-6 grid grid-cols-3 divide-x divide-border">
        <Stat label="Added" value={d.added.length} tone="green" />
        <Stat label="Removed" value={d.removed.length} tone="red" />
        <Stat label="Kept" value={d.kept} />
      </Card>
      <div className="grid gap-6 md:grid-cols-2">
        <section>
          <h2 className="mb-3 text-[15px] font-semibold">New Citations</h2>
          {list(d.added, "added")}
        </section>
        <section>
          <h2 className="mb-3 text-[15px] font-semibold">Dropped Citations</h2>
          {list(d.removed, "removed")}
        </section>
      </div>
    </>
  );
}

function DiffSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading comparison…">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="mt-3 h-5 w-[28rem] max-w-full" />
      <Skeleton className="mt-8 h-8 w-96 max-w-full" />
      <Skeleton className="mt-6 h-10 w-80" />
      <DiffSkeleton.Body />
    </div>
  );
}

DiffSkeleton.Body = function DiffBodySkeleton() {
  return (
    <div className="mt-6 flex flex-col gap-2" aria-hidden="true">
      <Skeleton className="mb-4 h-[68px]" />
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-12" />
      ))}
    </div>
  );
};
