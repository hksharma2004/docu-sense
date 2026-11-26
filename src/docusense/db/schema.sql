-- docusense schema. versions, sections and spans are append-only.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  id            TEXT PRIMARY KEY,                 -- 'smtp'
  title         TEXT NOT NULL,
  source_family TEXT NOT NULL                     -- 'rfc' | 'synthetic'
);

CREATE TABLE IF NOT EXISTS versions (
  id             TEXT PRIMARY KEY,                -- 'smtp@rfc5321'
  document_id    TEXT NOT NULL REFERENCES documents(id),
  label          TEXT NOT NULL,                   -- 'rfc5321'
  seq            INT  NOT NULL,                   -- order within document, 1 = oldest
  format         TEXT NOT NULL,                   -- 'pdf' | 'md'
  source_path    TEXT NOT NULL,
  source_sha256  TEXT NOT NULL UNIQUE,            -- hash of the original file bytes
  text_sha256    TEXT NOT NULL,                   -- hash of the canonical text blob
  text_bytes     INT  NOT NULL,
  page_map       JSONB NOT NULL,                  -- byte offset where each page starts
  parser_version TEXT NOT NULL,
  origin         JSONB,                           -- where the source came from
  ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, seq),
  UNIQUE (document_id, label)
);

CREATE TABLE IF NOT EXISTS sections (
  id          BIGSERIAL PRIMARY KEY,
  version_id  TEXT NOT NULL REFERENCES versions(id),
  parent_id   BIGINT REFERENCES sections(id),
  number      TEXT,                               -- '4.5.3.1', 'A.1', NULL for unnumbered
  title       TEXT NOT NULL,
  level       INT  NOT NULL,                      -- 0 = front matter
  ordinal     INT  NOT NULL,                      -- document order
  start_byte  INT  NOT NULL,
  end_byte    INT  NOT NULL,
  page_start  INT  NOT NULL,
  page_end    INT  NOT NULL,
  sha256      TEXT NOT NULL,
  UNIQUE (version_id, ordinal)
);

CREATE TABLE IF NOT EXISTS spans (
  id                BIGSERIAL PRIMARY KEY,
  version_id        TEXT NOT NULL REFERENCES versions(id),
  section_id        BIGINT REFERENCES sections(id),
  kind              TEXT NOT NULL,                -- paragraph | table | sentence
  ordinal           INT  NOT NULL,
  start_byte        INT  NOT NULL,
  end_byte          INT  NOT NULL,
  page              INT  NOT NULL,
  sha256            TEXT NOT NULL,
  text              TEXT NOT NULL,
  parser_version    TEXT NOT NULL,
  extraction_method TEXT NOT NULL,                -- layout | regex | llm
  model_id          TEXT,
  prompt_hash       TEXT,
  confidence        REAL,
  CHECK (end_byte > start_byte)
);
CREATE INDEX IF NOT EXISTS spans_version_idx ON spans(version_id);
CREATE INDEX IF NOT EXISTS spans_section_idx ON spans(section_id);

-- kept apart from spans so spans stay strictly append-only.
CREATE TABLE IF NOT EXISTS span_embeddings (
  span_id   BIGINT PRIMARY KEY REFERENCES spans(id),
  model     TEXT NOT NULL,
  embedding vector(384) NOT NULL
);

CREATE TABLE IF NOT EXISTS refs (
  id                  BIGSERIAL PRIMARY KEY,
  span_id             BIGINT NOT NULL REFERENCES spans(id),
  raw                 TEXT NOT NULL,              -- 'Section 3.4 of [RFC5322]'
  target_doc          TEXT,                       -- NULL = internal
  target_rfc          TEXT,
  target_section      TEXT,
  resolved_section_id BIGINT REFERENCES sections(id),
  status              TEXT NOT NULL               -- resolved | unresolved | external
);

CREATE TABLE IF NOT EXISTS definitions (
  id         BIGSERIAL PRIMARY KEY,
  term       TEXT NOT NULL,
  term_norm  TEXT NOT NULL,
  span_id    BIGINT NOT NULL REFERENCES spans(id),
  version_id TEXT NOT NULL REFERENCES versions(id),
  method     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
  id          BIGSERIAL PRIMARY KEY,
  span_id     BIGINT NOT NULL REFERENCES spans(id),
  version_id  TEXT NOT NULL REFERENCES versions(id),
  claim_type  TEXT NOT NULL,                      -- requirement | numeric | exclusion | procedure
  subject     TEXT,
  subject_key TEXT,
  modality    TEXT,
  value_num   DOUBLE PRECISION,
  unit        TEXT,
  method      TEXT NOT NULL,
  model_id    TEXT,
  prompt_hash TEXT,
  confidence  REAL
);

CREATE TABLE IF NOT EXISTS conflicts (
  id          BIGSERIAL PRIMARY KEY,
  claim_a     BIGINT NOT NULL REFERENCES claims(id),
  claim_b     BIGINT NOT NULL REFERENCES claims(id),
  reason      TEXT NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- later additions (idempotent so `db init` upgrades an existing db).
ALTER TABLE claims ADD COLUMN IF NOT EXISTS predicate TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS topic_terms TEXT[];
ALTER TABLE refs ADD COLUMN IF NOT EXISTS target_version TEXT;
ALTER TABLE refs ADD COLUMN IF NOT EXISTS version_id TEXT REFERENCES versions(id);
ALTER TABLE refs ADD COLUMN IF NOT EXISTS relation TEXT;  -- section | cites | obsoletes | updates
ALTER TABLE definitions ADD COLUMN IF NOT EXISTS section_id BIGINT REFERENCES sections(id);

-- more additions.
ALTER TABLE conflicts ADD COLUMN IF NOT EXISTS method TEXT;
ALTER TABLE conflicts ADD COLUMN IF NOT EXISTS confidence REAL;
ALTER TABLE conflicts ADD COLUMN IF NOT EXISTS details JSONB;

-- sentence spans are deterministic, so re-extraction must not duplicate them.
CREATE UNIQUE INDEX IF NOT EXISTS spans_unique_range ON spans(version_id, kind, start_byte, end_byte);
CREATE INDEX IF NOT EXISTS refs_version_idx ON refs(version_id);
CREATE INDEX IF NOT EXISTS refs_span_idx ON refs(span_id);
CREATE INDEX IF NOT EXISTS refs_target_idx ON refs(target_doc);
CREATE INDEX IF NOT EXISTS definitions_term_idx ON definitions(term_norm);
CREATE INDEX IF NOT EXISTS claims_subject_idx ON claims(subject_key);
CREATE INDEX IF NOT EXISTS claims_version_idx ON claims(version_id);
CREATE INDEX IF NOT EXISTS claims_topic_idx ON claims USING gin(topic_terms);

-- see schema_sqlite.sql for what a compaction is.
CREATE TABLE IF NOT EXISTS compactions (
  version_id   TEXT NOT NULL REFERENCES versions(id),
  level        TEXT NOT NULL CHECK (level IN ('cold', 'pruned')),
  compacted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  span_count   INTEGER NOT NULL,
  spans_root   TEXT NOT NULL,
  bytes_freed  BIGINT NOT NULL,
  policy       JSONB,
  PRIMARY KEY (version_id, level)
);

-- portable helper (sqlite registers the same function in python).
CREATE OR REPLACE FUNCTION topic_overlap(a TEXT[], b TEXT[]) RETURNS INT LANGUAGE sql IMMUTABLE AS $$
  SELECT cardinality(ARRAY(SELECT unnest(a) INTERSECT SELECT unnest(b)))
$$;

-- append-only: evidence is never rewritten or removed.
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'append-only table %: % not allowed', TG_TABLE_NAME, TG_OP;
END $$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['versions', 'sections', 'spans', 'compactions'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = t || '_append_only') THEN
      EXECUTE format(
        'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION forbid_mutation()',
        t || '_append_only', t);
    END IF;
  END LOOP;
END $$;
