"""background ingestion for the mcp server.

an add re-runs extraction, conflicts and indexing, and the first run downloads the embedding
model. that can outlast a client's tool timeout, so `add_document` queues a job here and waits
briefly; agents poll `ingest_status` for the rest. one worker, so writers never contend.
"""

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from docusense.config import get_settings


@dataclass
class Job:
    id: str
    paths: list[str]
    status: str = "queued"  # queued | running | done | failed
    stage: str = "queued"
    results: list[dict] = field(default_factory=list)
    derived: dict = field(default_factory=dict)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def view(self) -> dict:
        out = asdict(self)
        out["elapsed_s"] = round((self.finished_at or time.time()) - self.created_at, 1)
        return out


def allowed_roots() -> list[Path]:
    raw = get_settings().add_roots
    roots = [Path(p).expanduser().resolve() for p in raw.split(",") if p.strip()] if raw else [Path.home().resolve()]
    return roots


def check_allowed(path: Path) -> Path:
    """agents can only add files under the configured roots (default: home dir)"""
    resolved = path.expanduser().resolve()
    roots = allowed_roots()
    if not any(resolved == r or r in resolved.parents for r in roots):
        raise PermissionError(
            f"{resolved} is outside the allowed folders ({', '.join(map(str, roots))}); "
            "set DOCUSENSE_ADD_ROOTS to allow more"
        )
    return resolved


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="docusense-ingest")

    def submit(self, paths: list[Path], doc: str | None = None, title: str | None = None,
               label: str | None = None) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], paths=[str(p) for p in paths])
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, paths, doc, title, label)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def recent(self, n: int = 10) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:n]

    def wait(self, job: Job, seconds: float) -> Job:
        deadline = time.time() + max(0.0, seconds)
        while job.status in ("queued", "running") and time.time() < deadline:
            time.sleep(0.2)
        return job

    def _run(self, job: Job, paths: list[Path], doc, title, label) -> None:
        from docusense.db.conn import connect, init_schema
        from docusense.ingest.add import add_file, refresh_derived

        job.status = "running"
        try:
            with connect() as conn:
                init_schema(conn)
                added = 0
                for p in paths:
                    job.stage = f"parsing {p.name}"
                    try:
                        r = add_file(conn, p, doc=doc, title=title, label=label)
                        job.results.append({"file": str(p), "version_id": r.version_id, "status": r.status,
                                            "pages": r.pages, "sections": r.sections, "spans": r.spans,
                                            **({"note": r.note} if r.note else {})})
                        added += r.status == "ingested"
                    except (ValueError, OSError) as e:
                        job.results.append({"file": str(p), "status": "error", "error": str(e)})
                if added:
                    job.stage = "extracting claims/references, indexing (first run downloads the embedding model)"
                    job.derived = refresh_derived(conn, index=True)
            job.status = "done"
            job.stage = "done"
        except Exception as e:  # report, never crash the server
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.stage = "failed"
            traceback.print_exc()
        finally:
            job.finished_at = time.time()


jobs = JobManager()
