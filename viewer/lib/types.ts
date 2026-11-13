export type VersionRef = { version_id: string; label: string; seq: number; pages: number; is_latest: boolean };

export type DocumentEntry = { document: string; title: string; family: string; versions: VersionRef[] };

export type SpanView = {
  span_id: number;
  citation: string;
  version: string;
  section: string;
  page: number;
  kind?: string; // omitted for plain paragraphs
  text: string;
  newer_version?: string;
};

export type Section = {
  id: number;
  parent_id: number | null;
  number: string | null;
  title: string;
  level: number;
  page_start: number;
  page_end: number;
};

export type DocSpan = {
  id: number;
  section_id: number | null;
  kind: string;
  page: number;
  start_byte: number;
  end_byte: number;
  sha256: string;
  text: string;
};

export type VersionDocument = {
  version_id: string;
  document: string;
  title: string;
  family: string;
  label: string;
  format: string;
  is_latest: boolean;
  latest_version: string;
  pages: number;
  text_sha256: string;
  source_sha256: string;
  parser_version: string;
  versions: { id: string; label: string; seq: number }[];
  sections: Section[];
  spans: DocSpan[];
};

export type Evidence = SpanView & {
  section_path: string[];
  is_latest: boolean;
  latest_version: string;
  verified: boolean;
  provenance: Record<string, string | number>;
};

export type Verification = {
  span_id: number;
  verified: boolean;
  hash_match?: boolean;
  text_match?: boolean;
  blob_intact?: boolean;
  recomputed_sha256?: string;
  stored_sha256: string;
  error?: string;
};

export type Blame = {
  introduced_in: string | null;
  history: { version: string; status: "identical" | "similar" | "absent"; similarity: number; span_id?: number }[];
};

export type RefTarget = {
  raw: string;
  relation: string;
  status: "resolved" | "external" | "unresolved";
  target_version: string | null;
  target_section: string | null;
  target_section_title?: string;
  target_rfc?: string;
  newer_version?: string;
  preview?: SpanView[];
};

export type SectionDiffRow = {
  status: "added" | "removed" | "modified" | "unchanged";
  old: string | null;
  new: string | null;
  old_section_id?: number;
  new_section_id?: number;
  renumbered?: boolean;
  similarity?: number;
  changes?: { added: string[]; removed: string[] };
};

export type ClaimView = {
  span_id: number;
  section: string | null;
  modality: string | null;
  subject: string | null;
  value: number | null;
  unit: string | null;
  text: string;
};

export type SectionDiff = {
  from: string;
  to: string;
  summary: Record<"added" | "removed" | "modified" | "unchanged", number>;
  sections: SectionDiffRow[];
};

export type ClaimDiff = {
  from: string;
  to: string;
  summary: Record<string, number>;
  changed: { change: string[]; similarity: number; old: ClaimView; new: ClaimView }[];
  added: ClaimView[];
  removed: ClaimView[];
};

export type RefDiff = {
  from: string;
  to: string;
  added: { relation: string; target: string }[];
  removed: { relation: string; target: string }[];
  kept: number;
};

export type Contradiction = {
  conflict_id: number;
  reason: "value_mismatch" | "modality_mismatch";
  status: "confirmed" | "candidate" | "rejected";
  score: number;
  method: string;
  judge?: { contradiction: boolean; confidence: number; explanation: string; model_id: string } | null;
  a: SpanView;
  b: SpanView;
};
