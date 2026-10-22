import psycopg
import pytest

from docusense.config import get_settings
from docusense.db.conn import connect, reset_schema
from docusense.store.blobs import BlobStore

TEST_DB = "docusense_test"


def _admin_url() -> str:
    return get_settings().database_url


@pytest.fixture(scope="session")
def test_db_url() -> str:
    base = _admin_url()
    try:
        with psycopg.connect(base, autocommit=True) as admin:
            exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
            if not exists:
                admin.execute(f"CREATE DATABASE {TEST_DB}")
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable (run `docker compose up -d`)")
    return base.rsplit("/", 1)[0] + "/" + TEST_DB


@pytest.fixture
def conn(test_db_url):
    with connect(test_db_url) as c:
        reset_schema(c)
        yield c


@pytest.fixture
def store(tmp_path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")
