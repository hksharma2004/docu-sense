import Link from "next/link";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";

type Tone = "green" | "red" | "amber" | "blue" | "gray";

const TONE: Record<Tone, string> = {
  green: "bg-[var(--green-bg)] text-[var(--green-fg)] ring-[var(--green-border)]",
  red: "bg-[var(--red-bg)] text-[var(--red-fg)] ring-[var(--red-border)]",
  amber: "bg-[var(--amber-bg)] text-[var(--amber-fg)] ring-[var(--amber-border)]",
  blue: "bg-[var(--blue-bg)] text-[var(--blue-fg)] ring-[var(--blue-border)]",
  gray: "bg-[var(--gray-bg)] text-[var(--gray-fg)] ring-[var(--gray-border)]",
};

export function Badge({ tone = "gray", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap ring-1 ring-inset ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}

const STATUS: Record<string, { tone: Tone; label: string; mark: string }> = {
  added: { tone: "green", label: "Added", mark: "+" },
  removed: { tone: "red", label: "Removed", mark: "−" },
  modified: { tone: "amber", label: "Modified", mark: "~" },
  unchanged: { tone: "gray", label: "Unchanged", mark: "=" },
  confirmed: { tone: "red", label: "Confirmed", mark: "!" },
  candidate: { tone: "amber", label: "Candidate", mark: "?" },
  rejected: { tone: "gray", label: "Rejected", mark: "×" },
  resolved: { tone: "green", label: "Resolved", mark: "→" },
  external: { tone: "gray", label: "External", mark: "↗" },
  unresolved: { tone: "red", label: "Unresolved", mark: "?" },
  identical: { tone: "green", label: "Identical", mark: "=" },
  similar: { tone: "amber", label: "Similar", mark: "≈" },
  absent: { tone: "gray", label: "Absent", mark: "∅" },
};

/** Status is never conveyed by color alone: every badge has a symbol & a text label. */
export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { tone: "gray" as Tone, label: status, mark: "·" };
  return (
    <Badge tone={s.tone}>
      <span aria-hidden="true">{s.mark}</span>
      {s.label}
    </Badge>
  );
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <Badge tone="green" title="SHA-256 of the stored bytes matches">
      <span aria-hidden="true">✓</span>Verified
    </Badge>
  ) : (
    <Badge tone="red" title="SHA-256 mismatch: the evidence was altered">
      <span aria-hidden="true">✗</span>Hash Mismatch
    </Badge>
  );
}

export function VersionBadge({ latest, newer }: { latest: boolean; newer?: string }) {
  return latest ? (
    <Badge tone="blue">Latest</Badge>
  ) : (
    <Badge tone="amber" title={newer ? `Superseded by ${newer}` : undefined}>
      Obsolete
    </Badge>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl bg-bg shadow-[var(--shadow-card)] ${className}`}>{children}</div>;
}

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-[28px]">{title}</h1>
        {description ? <p className="mt-1.5 max-w-2xl text-[15px] text-pretty text-fg-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function Citation({ value }: { value: string }) {
  return (
    <code translate="no" className="text-[13px] break-all text-fg-subtle tabular-nums">
      {value}
    </code>
  );
}

export function Stat({ label, value, tone }: { label: string; value: number | string; tone?: Tone }) {
  const color = tone ? TONE[tone].split(" ")[1] : "text-fg";
  return (
    <div className="flex flex-col gap-0.5 px-4 py-3">
      <span className="text-xs text-fg-subtle">{label}</span>
      <span className={`text-xl font-semibold tabular-nums ${color}`}>{value}</span>
    </div>
  );
}

export function ButtonLink({ href, children, variant = "secondary" }: { href: string; children: ReactNode; variant?: "primary" | "secondary" }) {
  const styles =
    variant === "primary"
      ? "bg-fg text-bg hover:bg-fg/85"
      : "bg-bg text-fg shadow-[var(--shadow-card)] hover:bg-bg-subtle";
  return (
    <Link
      href={href}
      className={`inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium transition-colors ${styles}`}
    >
      {children}
    </Link>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-md bg-bg-muted motion-reduce:animate-none ${className}`} />;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border-strong px-6 py-12 text-center">
      <p className="font-medium">{title}</p>
      {children ? <div className="mt-1.5 text-sm text-fg-muted">{children}</div> : null}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : "Something went wrong while loading this page.";
  const offline = error instanceof ApiError && error.status === 503;
  return (
    <div role="alert" className="rounded-xl bg-[var(--red-bg)] px-5 py-4 ring-1 ring-[var(--red-border)] ring-inset">
      <p className="font-medium text-[var(--red-fg)]">{offline ? "API Unavailable" : "Couldn’t Load This View"}</p>
      <p className="mt-1 text-sm text-fg-muted">{message}</p>
      <div className="mt-3 flex gap-2">
        <ButtonLink href="/">Back to Documents</ButtonLink>
      </div>
    </div>
  );
}

/** Runs an async data loader inside a server component & renders ErrorState on failure. */
export async function load<T>(fn: () => Promise<T>): Promise<{ data: T; error: null } | { data: null; error: unknown }> {
  try {
    return { data: await fn(), error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

export function short(hash: string, n = 12): string {
  return `${hash.slice(0, n)}…`;
}
