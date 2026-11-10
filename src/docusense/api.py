"""REST API for the viewer. Thin wrapper over services.DocuSense.

Run:  uv run docusense serve-api   (http://localhost:8000, docs at /docs)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from docusense.config import get_settings
from docusense.services import DocuSense, NotFound

pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = ConnectionPool(get_settings().database_url, min_size=1, max_size=8,
                          kwargs={"row_factory": dict_row, "autocommit": True}, open=True)
    yield
    pool.close()


app = FastAPI(title="DocuSense API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(NotFound)
async def not_found(_: Request, exc: NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def bad_request(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def run(fn, *args, **kwargs):
    with pool.connection() as conn:
        return fn(DocuSense(conn), *args, **kwargs)


# Sync endpoints run in FastAPI's thread pool, so blocking DB calls don't stall the event loop.

@app.get("/api/health")
def health():
    return run(lambda ds: {"ok": True, "versions": ds.conn.execute("SELECT count(*) AS n FROM versions").fetchone()["n"]})


@app.get("/api/documents")
def documents():
    return run(lambda ds: ds.list_documents())


@app.get("/api/documents/{doc}/versions")
def versions(doc: str):
    return run(lambda ds: ds.list_versions(doc))


@app.get("/api/documents/{doc}/affected")
def affected(doc: str):
    return run(lambda ds: ds.find_affected_documents(doc, max_tokens=20000))


@app.get("/api/versions/{version_id}")
def version_document(version_id: str):
    return run(lambda ds: ds.version_document(version_id))


@app.get("/api/spans/{span_id}")
def span(span_id: int):
    return run(lambda ds: ds.get_evidence(span_id))


@app.get("/api/spans/{span_id}/verify")
def verify(span_id: int, deep: bool = False):
    return run(lambda ds: ds.verify_span(span_id, deep))


@app.get("/api/spans/{span_id}/blame")
def blame(span_id: int):
    return run(lambda ds: ds.blame(span_id))


@app.get("/api/spans/{span_id}/references")
def references(span_id: int):
    return run(lambda ds: ds.resolve_reference(span_id=span_id, max_tokens=20000))


@app.get("/api/diff")
def diff(doc: str, from_version: str | None = Query(None, alias="from"),
         to_version: str | None = Query(None, alias="to"), level: str = "section"):
    return run(lambda ds: ds.diff_versions(doc, from_version, to_version, level, max_tokens=200000))


@app.get("/api/search")
def search(q: str, mode: str = "hybrid", doc: str | None = None, k: int = 10):
    if not q.strip():
        raise HTTPException(400, "query is empty")
    return run(lambda ds: ds.search(q, mode, doc, k, max_tokens=20000))


@app.get("/api/contradictions")
def contradictions(doc: str | None = None, history: bool = False, rejected: bool = False, k: int = 50):
    return run(lambda ds: ds.find_contradictions(doc, history, rejected, k, max_tokens=200000))
