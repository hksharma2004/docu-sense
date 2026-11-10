import Link from "next/link";

import { Card, Citation, ErrorState, StatusBadge, VerifiedBadge, VersionBadge, load } from "@/components/ui";
import { api } from "@/lib/api";
import type { Blame, Evidence, RefTarget, Verification } from "@/lib/types";

export async function EvidencePanel({ spanId, closeHref }: { spanId: number; closeHref: string }) {
  const [evidence, verification, blame, refs] = await Promise.all([
    load(() => api<Evidence>(`/api/spans/${spanId}`)),
    load(() => api<Verification>(`/api/spans/${spanId}/verify`)),
    load(() => api<Blame>(`/api/spans/${spanId}/blame`)),
    load(() => api<{ references: RefTarget[] }>(`/api/spans/${spanId}/references`)),
  ]);
  if (evidence.error) return <ErrorState error={evidence.error} />;
  const ev = evidence.data!;
  const v = verification.data;

  return (
    <Card className="fade-in flex flex-col divide-y divide-border">
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <h2 className="text-sm font-semibold">Evidence</h2>
        <Link href={closeHref} scroll={false} className="inline-flex h-7 items-center rounded-md px-2 text-[13px] text-fg-muted hover:bg-bg-muted hover:text-fg">
          Close
        </Link>
      </div>

      <section className="flex flex-col gap-3 px-4 py-4" aria-label="Provenance">
        <div className="flex flex-wrap items-center gap-2">
          {v ? <VerifiedBadge verified={v.verified} /> : null}
          <VersionBadge latest={ev.is_latest} newer={ev.latest_version} />
        </div>
        {v && !v.verified ? (
          <p className="text-[13px] text-[var(--red-fg)]">
            The stored bytes no longer hash to the recorded SHA-256. Don’t cite this span; re-ingest the source.
          </p>
        ) : null}
        <Citation value={ev.citation} />
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[13px]">
          <dt className="text-fg-subtle">Section</dt>
          <dd>{ev.section_path.join(" › ") || ev.section}</dd>
          <dt className="text-fg-subtle">Page</dt>
          <dd className="tabular-nums">{ev.page}</dd>
          <dt className="text-fg-subtle">Bytes</dt>
          <dd className="tabular-nums" translate="no">
            {ev.provenance.start_byte}–{ev.provenance.end_byte}
          </dd>
          <dt className="text-fg-subtle">SHA-256</dt>
          <dd className="break-all tabular-nums" translate="no">
            {ev.sha256}
          </dd>
          <dt className="text-fg-subtle">Parser</dt>
          <dd translate="no">{String(ev.provenance.parser_version)}</dd>
        </dl>
        {!ev.is_latest ? (
          <p className="text-[13px] text-fg-muted">
            Superseded by{" "}
            <Link className="font-medium text-fg underline underline-offset-4" href={`/docs/${encodeURIComponent(ev.latest_version)}`}>
              {ev.latest_version}
            </Link>
            .
          </p>
        ) : null}
      </section>

      <section className="px-4 py-4" aria-labelledby="blame-heading">
        <h3 id="blame-heading" className="mb-2 text-[13px] font-semibold">
          History
        </h3>
        {blame.data ? (
          <>
            <p className="mb-3 text-[13px] text-fg-muted">
              Introduced in <span className="font-medium text-fg" translate="no">{blame.data.introduced_in ?? "—"}</span>
            </p>
            <ol className="flex flex-col gap-2">
              {blame.data.history.map((h) => (
                <li key={h.version} className="flex items-center justify-between gap-2 text-[13px]">
                  {h.span_id && h.span_id !== spanId ? (
                    <Link
                      href={`/docs/${encodeURIComponent(h.version)}?span=${h.span_id}#span-${h.span_id}`}
                      className="underline-offset-4 hover:underline"
                      translate="no"
                    >
                      {h.version}
                    </Link>
                  ) : (
                    <span translate="no">{h.version}</span>
                  )}
                  <span className="flex items-center gap-2">
                    <span className="text-fg-subtle tabular-nums">{Math.round(h.similarity * 100)}%</span>
                    <StatusBadge status={h.status} />
                  </span>
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="text-[13px] text-fg-subtle">History unavailable for this span.</p>
        )}
      </section>

      <section className="px-4 py-4" aria-labelledby="refs-heading">
        <h3 id="refs-heading" className="mb-2 text-[13px] font-semibold">
          References
        </h3>
        {refs.data && refs.data.references.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {refs.data.references.map((r, i) => {
              const preview = r.preview?.[0];
              const href = preview
                ? `/docs/${encodeURIComponent(preview.version)}?span=${preview.span_id}#span-${preview.span_id}`
                : r.target_version
                  ? `/docs/${encodeURIComponent(r.target_version)}`
                  : null;
              return (
                <li key={`${r.raw}-${i}`} className="text-[13px]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium" translate="no">
                      {r.raw}
                    </span>
                    <StatusBadge status={r.status} />
                  </div>
                  {href ? (
                    <Link href={href} className="mt-0.5 block text-fg-muted underline-offset-4 hover:text-fg hover:underline">
                      <span translate="no">{r.target_version}</span>
                      {r.target_section ? ` §${r.target_section}` : ""}
                      {r.target_section_title ? ` ${r.target_section_title}` : ""}
                    </Link>
                  ) : (
                    <p className="mt-0.5 text-fg-subtle">{r.target_rfc ? `${r.target_rfc} is outside the corpus` : "Outside the corpus"}</p>
                  )}
                  {r.newer_version ? <p className="mt-0.5 text-[var(--amber-fg)]">Cites an obsolete version; latest is {r.newer_version}.</p> : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-[13px] text-fg-subtle">No cross-references in this span.</p>
        )}
      </section>
    </Card>
  );
}
