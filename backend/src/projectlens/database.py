"""Supabase Postgres connection helpers."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


def get_connection() -> psycopg.Connection:
    """Open a connection using the Supabase DATABASE_URL from .env."""
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


@contextmanager
def connection_scope() -> Iterator[psycopg.Connection]:
    """Yield a connection and close it after use."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
