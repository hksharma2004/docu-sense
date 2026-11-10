"""Database access for two backends behind one small interface.

- SQLite (default, embedded, zero setup): DATABASE_URL unset or sqlite:///path.
- Postgres + pgvector (team/hosted use): DATABASE_URL=postgresql://… (needs the `postgres` extra).

Callers write Postgres-flavoured SQL with %s placeholders. For SQLite the wrapper rewrites
placeholders, expands `= ANY(%s)` list parameters into `IN (…)`, stores JSON / text-array columns as
JSON text (decoded on read via declared column types) and registers the few SQL functions the
queries rely on. Anything not expressible that way branches on `db.dialect`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

from docusense.config import get_settings

MIN_SQLITE = (3, 38, 0)  # RETURNING (3.35), ->> JSON operator (3.38)


def _sqlite_path(url: str) -> Path:
    path = url.removeprefix("sqlite:///").removeprefix("sqlite://")
    return Path(path).expanduser()


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


# ── SQLite type plumbing ─────────────────────────────────────────────────────

def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


sqlite3.register_adapter(list, _json_text)
sqlite3.register_adapter(dict, _json_text)
sqlite3.register_converter("JSONB", json.loads)
sqlite3.register_converter("TEXTARRAY", json.loads)
sqlite3.register_converter("TIMESTAMPTZ", lambda b: datetime.fromisoformat(b.decode()))
try:  # numpy scalars sneak into parameters (scores, confidences)
    import numpy as np

    sqlite3.register_adapter(np.float32, float)
    sqlite3.register_adapter(np.float64, float)
    sqlite3.register_adapter(np.int64, int)
    sqlite3.register_adapter(np.int32, int)
except ImportError:  # pragma: no cover
    pass

_PARAM = re.compile(r"=\s*ANY\(\s*%s\s*\)|%s|%%")


def _translate(sql: str, params: tuple | list | None) -> tuple[str, list]:
    """Postgres-style SQL + params → SQLite SQL + flat params."""
    params = list(params or ())
    out_params: list = []
    index = 0

    def repl(m: re.Match) -> str:
        nonlocal index
        token = m.group(0)
        if token == "%%":
            return "%"
        value = params[index]
        index += 1
        if token != "%s":  # = ANY(%s)
            values = list(value)
            out_params.extend(values)
            return "IN (" + ", ".join("?" * len(values)) + ")"
        out_params.append(value)
        return "?"

    return _PARAM.sub(repl, sql), out_params


def _regexp_replace(text, pattern, replacement, flags=""):
    if text is None:
        return None
    count = 0 if "g" in (flags or "") else 1
    return re.sub(pattern, replacement, text, count=count, flags=re.I if "i" in (flags or "") else 0)


def _json_array_length(value):
    return None if value is None else len(json.loads(value))


def _topic_overlap(a, b):
    if a is None or b is None:
        return 0
    return len(set(json.loads(a)) & set(json.loads(b)))


def _dict_row(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {d[0]: v for d, v in zip(cursor.description, row)}


# ── unified connection ───────────────────────────────────────────────────────

class Database:
    """Thin wrapper exposing the subset of the psycopg connection API DocuSense uses."""

    def __init__(self, raw: Any, dialect: str):
        self.raw = raw
        self.dialect = dialect
        self._depth = 0

    # queries
    def execute(self, sql: str, params: tuple | list | None = None):
        if self.dialect == "sqlite":
            sql, flat = _translate(sql, params)
            return self.raw.execute(sql, flat)
        return self.raw.execute(sql, params)

    def executemany(self, sql: str, rows: list) -> None:
        if self.dialect == "sqlite":
            if not rows:
                return
            translated, _ = _translate(sql, rows[0])
            self.raw.executemany(translated, [_translate(sql, r)[1] for r in rows])
            return
        with self.raw.cursor() as cur:
            cur.executemany(sql, rows)

    def json(self, value: Any) -> Any:
        """Wrap a value bound for a JSONB column."""
        if self.dialect == "sqlite":
            return _json_text(value)
        from psycopg.types.json import Jsonb

        return Jsonb(value)

    # transactions
    @property
    def autocommit(self) -> bool:
        return bool(self.raw.autocommit)

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        if self.dialect == "sqlite" and value and self.raw.in_transaction:
            self.raw.commit()
        self.raw.autocommit = value

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.dialect == "postgres":
            with self.raw.transaction():
                yield
            return
        self._depth += 1
        name = f"ds_sp{self._depth}"
        self.raw.execute(f"SAVEPOINT {name}")
        try:
            yield
        except BaseException:
            self.raw.execute(f"ROLLBACK TO {name}")
            self.raw.execute(f"RELEASE {name}")
            raise
        else:
            self.raw.execute(f"RELEASE {name}")
            if self._depth == 1:
                self.raw.commit()
        finally:
            self._depth -= 1

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


def _connect_sqlite(path: Path) -> Database:
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise RuntimeError(
            f"SQLite {sqlite3.sqlite_version} is too old (need {'.'.join(map(str, MIN_SQLITE))}+). "
            "Use a Python built against a newer SQLite (e.g. `uv python install 3.12`) or set DATABASE_URL to Postgres."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False,
                          timeout=30, autocommit=True)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=ON")
    raw.execute("PRAGMA synchronous=NORMAL")
    raw.row_factory = _dict_row
    raw.create_function("regexp_replace", -1, _regexp_replace, deterministic=True)
    raw.create_function("jsonb_array_length", 1, _json_array_length, deterministic=True)
    raw.create_function("topic_overlap", 2, _topic_overlap, deterministic=True)
    raw.autocommit = False  # PEP 249 transactions, matching psycopg's default
    return Database(raw, "sqlite")


def connect(url: str | None = None) -> Database:
    url = url or get_settings().resolved_database_url
    if is_sqlite(url):
        return _connect_sqlite(_sqlite_path(url))
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Postgres support needs the extra: pip install 'docusense[postgres]'") from e
    return Database(psycopg.connect(url, row_factory=dict_row), "postgres")


def init_schema(db: Database) -> None:
    if db.dialect == "sqlite":
        db.raw.executescript(files("docusense.db").joinpath("schema_sqlite.sql").read_text())
    else:
        db.execute(files("docusense.db").joinpath("schema.sql").read_text())
    db.commit()


def reset_schema(db: Database) -> None:
    """Drop everything and recreate. Dev only: this is the one way evidence gets removed."""
    if db.dialect == "sqlite":
        db.commit()
        db.raw.autocommit = True
        db.raw.execute("PRAGMA foreign_keys=OFF")
        tables = [r["name"] for r in db.raw.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        for t in tables:
            db.raw.execute(f'DROP TABLE IF EXISTS "{t}"')
        db.raw.execute("PRAGMA foreign_keys=ON")
        db.raw.autocommit = False
    else:
        db.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        db.commit()
    init_schema(db)


class ConnectionPool:
    """Per-request connections for the REST API. Postgres uses psycopg_pool; SQLite opens cheaply."""

    def __init__(self, url: str | None = None):
        self.url = url or get_settings().resolved_database_url
        self._pg = None
        if not is_sqlite(self.url):
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool as PgPool

            self._pg = PgPool(self.url, min_size=1, max_size=8, kwargs={"row_factory": dict_row, "autocommit": True}, open=True)

    @contextmanager
    def connection(self) -> Iterator[Database]:
        if self._pg is None:
            with connect(self.url) as db:
                yield db
            return
        with self._pg.connection() as raw:
            yield Database(raw, "postgres")

    def close(self) -> None:
        if self._pg is not None:
            self._pg.close()
