"""Portable SQL fragments shared across modules (valid on both Postgres and SQLite)."""

# Latest version of every document (portable replacement for DISTINCT ON).
LATEST_VERSIONS_SQL = """SELECT v.document_id, v.id, v.seq FROM versions v
WHERE v.seq = (SELECT max(w.seq) FROM versions w WHERE w.document_id = v.document_id)
ORDER BY v.document_id"""

LATEST_VERSION_IDS_SUBQUERY = """(SELECT v.id FROM versions v
WHERE v.seq = (SELECT max(w.seq) FROM versions w WHERE w.document_id = v.document_id))"""
