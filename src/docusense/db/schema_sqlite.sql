-- docusense schema, sqlite dialect. mirrors schema.sql (postgres) as it stands now.
-- declared types JSONB / TEXTARRAY / TIMESTAMPTZ drive python-side converters (see db/conn.py).
-- versions, sections and spans are append-only (triggers at the bottom).

CREATE TABLE IF NOT EXISTS documents (
  id            TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  source_family TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS versions (
  id             TEXT PRIMARY KEY,
  document_id    TEXT NOT NULL REFERENCES documents(id),
  label          TEXT NOT NULL,
  seq            INTEGER NOT NULL,
  format         TEXT NOT NULL,
  source_path    TEXT NOT NULL,
  source_sha256  TEXT NOT NULL UNIQUE,
  text_sha256    TEXT NOT NULL,
  text_bytes     INTEGER NOT NULL,
  page_map       JSONB NOT NULL,
  parser_version TEXT NOT NULL,
  origin         JSONB,
  ingested_at    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
  UNIQUE (document_id, seq),
  UNIQUE (document_id, label)
);

CREATE TABLE IF NOT EXISTS sections (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id  TEXT NOT NULL REFERENCES versions(id),
  parent_id   INTEGER REFERENCES sections(id),
  number      TEXT,
  title       TEXT NOT NULL,
  level       INTEGER NOT NULL,
  ordinal     INTEGER NOT NULL,
  start_byte  INTEGER NOT NULL,
  end_byte    INTEGER NOT NULL,
  page_start  INTEGER NOT NULL,
  page_end    INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  UNIQUE (version_id, ordinal)
);

CREATE TABLE IF NOT EXISTS spans (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id        TEXT NOT NULL REFERENCES versions(id),
  section_id        INTEGER REFERENCES sections(id),
  kind              TEXT NOT NULL,
  ordinal           INTEGER NOT NULL,
  start_byte        INTEGER NOT NULL,
  end_byte          INTEGER NOT NULL,
  page              INTEGER NOT NULL,
  sha256            TEXT NOT NULL,
  text              TEXT NOT NULL,
  parser_version    TEXT NOT NULL,
  extraction_method TEXT NOT NULL,
  model_id          TEXT,
  prompt_hash       TEXT,
  confidence        REAL,
  CHECK (end_byte > start_byte)
);
CREATE INDEX IF NOT EXISTS spans_version_idx ON spans(version_id);
CREATE INDEX IF NOT EXISTS spans_section_idx ON spans(section_id);
CREATE UNIQUE INDEX IF NOT EXISTS spans_unique_range ON spans(version_id, kind, start_byte, end_byte);

-- float32 little-endian vector bytes, searched with numpy (see index/embed.py).
CREATE TABLE IF NOT EXISTS span_embeddings (
  span_id   INTEGER PRIMARY KEY REFERENCES spans(id),
  model     TEXT NOT NULL,
  embedding BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS refs (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  span_id             INTEGER NOT NULL REFERENCES spans(id),
  raw                 TEXT NOT NULL,
  target_doc          TEXT,
  target_rfc          TEXT,
  target_section      TEXT,
  resolved_section_id INTEGER REFERENCES sections(id),
  status              TEXT NOT NULL,
  target_version      TEXT,
  version_id          TEXT REFERENCES versions(id),
  relation            TEXT
);
CREATE INDEX IF NOT EXISTS refs_version_idx ON refs(version_id);
CREATE INDEX IF NOT EXISTS refs_span_idx ON refs(span_id);
CREATE INDEX IF NOT EXISTS refs_target_idx ON refs(target_doc);

CREATE TABLE IF NOT EXISTS definitions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  term       TEXT NOT NULL,
  term_norm  TEXT NOT NULL,
  span_id    INTEGER NOT NULL REFERENCES spans(id),
  version_id TEXT NOT NULL REFERENCES versions(id),
  method     TEXT NOT NULL,
  section_id INTEGER REFERENCES sections(id)
);
CREATE INDEX IF NOT EXISTS definitions_term_idx ON definitions(term_norm);

CREATE TABLE IF NOT EXISTS claims (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  span_id     INTEGER NOT NULL REFERENCES spans(id),
  version_id  TEXT NOT NULL REFERENCES versions(id),
  claim_type  TEXT NOT NULL,
  subject     TEXT,
  subject_key TEXT,
  modality    TEXT,
  value_num   REAL,
  unit        TEXT,
  method      TEXT NOT NULL,
  model_id    TEXT,
  prompt_hash TEXT,
  confidence  REAL,
  predicate   TEXT,
  topic_terms TEXTARRAY
);
CREATE INDEX IF NOT EXISTS claims_subject_idx ON claims(subject_key);
CREATE INDEX IF NOT EXISTS claims_version_idx ON claims(version_id);

CREATE TABLE IF NOT EXISTS conflicts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_a     INTEGER NOT NULL REFERENCES claims(id),
  claim_b     INTEGER NOT NULL REFERENCES claims(id),
  reason      TEXT NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')),
  method      TEXT,
  confidence  REAL,
  details     JSONB
);

-- append-only: evidence is never rewritten or removed.
CREATE TRIGGER IF NOT EXISTS versions_append_only_u BEFORE UPDATE ON versions
BEGIN SELECT RAISE(ABORT, 'append-only table versions: UPDATE not allowed'); END;
CREATE TRIGGER IF NOT EXISTS versions_append_only_d BEFORE DELETE ON versions
BEGIN SELECT RAISE(ABORT, 'append-only table versions: DELETE not allowed'); END;
CREATE TRIGGER IF NOT EXISTS sections_append_only_u BEFORE UPDATE ON sections
BEGIN SELECT RAISE(ABORT, 'append-only table sections: UPDATE not allowed'); END;
CREATE TRIGGER IF NOT EXISTS sections_append_only_d BEFORE DELETE ON sections
BEGIN SELECT RAISE(ABORT, 'append-only table sections: DELETE not allowed'); END;
CREATE TRIGGER IF NOT EXISTS spans_append_only_u BEFORE UPDATE ON spans
BEGIN SELECT RAISE(ABORT, 'append-only table spans: UPDATE not allowed'); END;
CREATE TRIGGER IF NOT EXISTS spans_append_only_d BEFORE DELETE ON spans
BEGIN SELECT RAISE(ABORT, 'append-only table spans: DELETE not allowed'); END;
