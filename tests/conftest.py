import pytest

from docusense.config import get_settings
from docusense.db.conn import connect, is_sqlite, reset_schema
from docusense.store.blobs import BlobStore

TEST_DB = "docusense_test"


def _postgres_test_url() -> str:
    """postgres test db next to the configured one (skips if postgres isn't set up or reachable)"""
    base = get_settings().database_url
    if not base or is_sqlite(base):
        pytest.skip("Postgres not configured (set DOCUSENSE_DATABASE_URL=postgresql://…)")
    try:
        import psycopg
    except ImportError:
        pytest.skip("psycopg not installed (postgres extra)")
    try:
        with psycopg.connect(base, autocommit=True) as admin:
            exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
            if not exists:
                admin.execute(f"CREATE DATABASE {TEST_DB}")
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable (run `docker compose up -d`)")
    return base.rsplit("/", 1)[0] + "/" + TEST_DB


@pytest.fixture(params=["sqlite", "postgres"])
def conn(request, tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}" if request.param == "sqlite" else _postgres_test_url()
    with connect(url) as c:
        reset_schema(c)
        yield c


@pytest.fixture
def store(tmp_path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")
