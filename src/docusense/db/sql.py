"""portable sql fragments shared across modules (postgres + sqlite)"""

# latest version of each document (portable DISTINCT ON)
LATEST_VERSIONS_SQL = """SELECT v.document_id, v.id, v.seq FROM versions v
WHERE v.seq = (SELECT max(w.seq) FROM versions w WHERE w.document_id = v.document_id)
ORDER BY v.document_id"""

LATEST_VERSION_IDS_SUBQUERY = """(SELECT v.id FROM versions v
WHERE v.seq = (SELECT max(w.seq) FROM versions w WHERE w.document_id = v.document_id))"""
