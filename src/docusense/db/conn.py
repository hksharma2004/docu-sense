from importlib.resources import files

import psycopg
from psycopg.rows import dict_row

from docusense.config import get_settings


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or get_settings().database_url, row_factory=dict_row)


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(files("docusense.db").joinpath("schema.sql").read_text())
    conn.commit()


def reset_schema(conn: psycopg.Connection) -> None:
    """Drop everything and recreate. Dev only: this is the one way evidence gets removed."""
    conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    conn.commit()
    init_schema(conn)
