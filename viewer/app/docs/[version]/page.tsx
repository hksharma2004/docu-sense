import Link from "next/link";
import { Suspense } from "react";

import { EvidencePanel } from "@/components/evidence-panel";
import { Badge, ButtonLink, ErrorState, Skeleton, VersionBadge, load, short } from "@/components/ui";
import { api, first } from "@/lib/api";
import type { DocSpan, Section, VersionDocument } from "@/lib/types";

export async function generateMetadata({ params }: PageProps<"/docs/[version]">) {
  const { version } = await params;
  return { title: decodeURIComponent(version) };
}

export default function DocPage({ params, searchParams }: PageProps<"/docs/[version]">) {
  return (
    <Suspense fallback={<DocSkeleton />}>
      <DocView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

async function DocView({ params, searchParams }: PageProps<"/docs/[version]">) {
  const { version } = await params;
  const spanParam = first((await searchParams).span);
  const selected = spanParam ? Number(spanParam) : null;
  const versionId = decodeURIComponent(version);

  const { data: doc, error } = await load(() => api<VersionDocument>(`/api/versions/${encodeURIComponent(versionId)}`));
  if (error) return <ErrorState error={error} />;
  const d = doc!;

  const spansBySection = new Map<number | null, DocSpan[]>();
  for (const s of d.spans) {
    const list = spansBySection.get(s.section_id) ?? [];
    list.push(s);
    spansBySection.set(s.section_id, list);
  }
  const base = `/docs/${encodeURIComponent(d.version_id)}`;

  return (
    <div className={`grid gap-8 ${selected ? "lg:grid-cols-[220px_minmax(0,1fr)_340px]" : "lg:grid-cols-[220px_minmax(0,1fr)]"}`}>
      <Toc sections={d.sections} />

      <article className="min-w-0">
        <header className="mb-8 border-b border-border pb-6">
          <div className="flex flex-wrap items-center gap-2">
            <VersionBadge latest={d.is_latest} newer={d.latest_version} />
            {d.family === "synthetic" ? <Badge tone="amber">Synthetic</Badge> : null}
            <Badge>{d.format.toUpperCase()}</Badge>
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-balance sm:text-[28px]">{d.title}</h1>
          <p className="mt-1 text-sm text-fg-subtle" translate="no">
            {d.version_id}
          </p>

          {!d.is_latest ? (
            <p className="mt-4 rounded-lg bg-[var(--amber-bg)] px-3 py-2 text-sm text-[var(--amber-fg)] ring-1 ring-[var(--amber-border)] ring-inset">
              This version is obsolete.{" "}
              <Link href={`/docs/${encodeURIComponent(d.latest_version)}`} className="font-medium underline underline-offset-4">
                Read {d.latest_version}
              </Link>{" "}
              or{" "}
              <Link href={`/diff/${d.document}?from=${d.label}&to=${d.latest_version.split("@")[1]}`} className="font-medium underline underline-offset-4">
                see what changed
              </Link>
              .
            </p>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <nav aria-label="Versions" className="flex flex-wrap gap-1">
              {d.versions.map((v) => (
                <Link
                  key={v.id}
                  href={`/docs/${encodeURIComponent(v.id)}`}
                  aria-current={v.id === d.version_id ? "page" : undefined}
                  className="inline-flex h-8 items-center rounded-md px-2.5 text-[13px] text-fg-muted ring-1 ring-border ring-inset hover:bg-bg-muted aria-[current=page]:bg-fg aria-[current=page]:text-bg aria-[current=page]:ring-fg"
                  translate="no"
                >
                  {v.label.toUpperCase()}
                </Link>
              ))}
            </nav>
            {d.versions.length > 1 ? <ButtonLink href={`/diff/${d.document}`}>Compare Versions</ButtonLink> : null}
            <ButtonLink href={`/search?doc=${encodeURIComponent(d.version_id)}`}>Search This Version</ButtonLink>
          </div>

          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-4">
            <Meta label="Pages" value={String(d.pages)} />
            <Meta label="Sections" value={String(d.sections.length)} />
            <Meta label="Text SHA-256" value={short(d.text_sha256)} title={d.text_sha256} />
            <Meta label="Parser" value={d.parser_version} />
          </dl>
        </header>

        <div className="flex flex-col">
          {d.sections.map((s) => (
            <SectionBlock key={s.id} section={s} spans={spansBySection.get(s.id) ?? []} selected={selected} base={base} />
          ))}
        </div>
      </article>

      {selected ? (
        <aside aria-label="Evidence" className="lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:self-start lg:overflow-y-auto">
          <Suspense fallback={<Skeleton className="h-96" />}>
            <EvidencePanel spanId={selected} closeHref={base} />
          </Suspense>
        </aside>
      ) : null}
    </div>
  );
}

function Meta({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-fg-subtle">{label}</dt>
      <dd className="truncate tabular-nums" title={title} translate="no">
        {value}
      </dd>
    </div>
  );
}

function Toc({ sections }: { sections: Section[] }) {
  const items = sections.filter((s) => s.level <= 3);
  const list = (
    <ol className="flex flex-col text-[13px]">
      {items.map((s) => (
        <li key={s.id}>
          <a
            href={`#s-${s.id}`}
            className="flex min-h-7 items-baseline gap-1.5 rounded-md py-1 pr-2 text-fg-muted hover:bg-bg-muted hover:text-fg"
            style={{ paddingLeft: `${Math.max(0, s.level - 1) * 12 + 8}px` }}
          >
            {s.number ? <span className="shrink-0 text-fg-subtle tabular-nums">{s.number}</span> : null}
            <span className="line-clamp-2">{s.title}</span>
          </a>
        </li>
      ))}
    </ol>
  );
  return (
    <nav aria-label="Sections" className="min-w-0">
      <details className="rounded-lg ring-1 ring-border ring-inset lg:hidden">
        <summary className="flex h-10 cursor-pointer items-center gap-2 px-3 text-sm font-medium">
          <span aria-hidden="true" className="chevron inline-block text-fg-subtle">›</span>
          Sections ({items.length})
        </summary>
        <div className="max-h-80 overflow-y-auto overscroll-contain px-1 pb-2">{list}</div>
      </details>
      <div className="hidden lg:sticky lg:top-20 lg:block lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto lg:overscroll-contain">
        <p className="mb-2 px-2 text-xs font-medium text-fg-subtle">Sections</p>
        {list}
      </div>
    </nav>
  );
}

function SectionBlock({ section, spans, selected, base }: { section: Section; spans: DocSpan[]; selected: number | null; base: string }) {
  const Heading = section.level <= 1 ? "h2" : section.level === 2 ? "h3" : "h4";
  const size = section.level <= 1 ? "text-xl" : section.level === 2 ? "text-[17px]" : "text-[15px]";
  const containsSelected = selected !== null && spans.some((s) => s.id === selected);
  return (
    <section aria-labelledby={`s-${section.id}`} className={containsSelected ? "" : "doc-section"}>
      <Heading id={`s-${section.id}`} className={`group mt-8 mb-3 flex items-baseline gap-2 font-semibold tracking-tight text-balance ${size}`}>
        {section.number ? <span className="text-fg-subtle tabular-nums">{section.number}</span> : null}
        <span>{section.title}</span>
        <a href={`#s-${section.id}`} aria-label={`Link to section ${section.number ?? section.title}`} className="text-fg-subtle opacity-0 group-hover:opacity-100 focus-visible:opacity-100">
          #
        </a>
      </Heading>
      {spans.map((s) => (
        <SpanBlock key={s.id} span={s} active={s.id === selected} base={base} />
      ))}
    </section>
  );
}

function SpanBlock({ span, active, base }: { span: DocSpan; active: boolean; base: string }) {
  const prose = span.kind === "paragraph" && !isStructured(span.text);
  return (
    <div
      id={`span-${span.id}`}
      className={`group relative -mx-3 grid grid-cols-[1fr_auto] gap-3 rounded-md px-3 py-1.5 ${active ? "span-target" : ""}`}
    >
      {prose ? (
        <p className="text-[15px] leading-7 text-pretty">{reflow(span.text)}</p>
      ) : (
        <div className="evidence-pre text-[14px] leading-6">{dedent(span.text)}</div>
      )}
      <Link
        href={`${base}?span=${span.id}#span-${span.id}`}
        scroll={false}
        aria-label={`Inspect span ${span.id} on page ${span.page}`}
        aria-current={active ? "true" : undefined}
        className="mt-1 inline-flex h-6 min-w-10 items-center justify-center self-start rounded px-1.5 text-xs text-fg-subtle tabular-nums opacity-60 ring-1 ring-transparent ring-inset group-hover:opacity-100 hover:bg-bg-muted hover:text-fg hover:ring-border focus-visible:opacity-100 aria-[current=true]:opacity-100"
      >
        p.&nbsp;{span.page}
      </Link>
    </div>
  );
}

/** Indented definition lists, column layouts & figures keep their line layout. */
function isStructured(text: string): boolean {
  const lines = text.split("\n").filter((l) => l.trim());
  if (lines.length < 2) return /\S\s{3,}\S/.test(lines[0]?.trim() ?? "");
  const indent = (l: string) => l.length - l.trimStart().length;
  const base = indent(lines[0]);
  return lines.slice(1).some((l) => indent(l) >= base + 3) || lines.some((l) => /\S\s{3,}\S/.test(l.trim()));
}

/** Display-only reflow of fixed-width paragraphs. The stored evidence bytes are untouched. */
function reflow(text: string): string {
  return text.split("\n").map((l) => l.trim()).join(" ");
}

function dedent(text: string): string {
  const lines = text.split("\n");
  const indent = Math.min(...lines.filter((l) => l.trim()).map((l) => l.length - l.trimStart().length));
  return lines.map((l) => l.slice(Number.isFinite(indent) ? indent : 0)).join("\n");
}

function DocSkeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)]" aria-busy="true" aria-label="Loading document…">
      <div className="hidden flex-col gap-2 lg:flex">
        {Array.from({ length: 14 }).map((_, i) => (
          <Skeleton key={i} className="h-5" />
        ))}
      </div>
      <div>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="mt-3 h-8 w-2/3" />
        <Skeleton className="mt-6 h-8 w-80" />
        <div className="mt-10 flex flex-col gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      </div>
    </div>
  );
}
