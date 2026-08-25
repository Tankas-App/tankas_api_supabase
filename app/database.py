"""
database.py — asyncpg connection pool for Koyeb PostgreSQL

Usage across the codebase:

    # Option A: get a single connection (most service methods)
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    # Option B: run a query directly from the pool (fire-and-forget / simple reads)
    rows = await pool_query("SELECT * FROM issues WHERE status = $1", "open")

Pool lifecycle:
    - init_db()  called once at app startup  (main.py lifespan)
    - close_db() called once at app shutdown (main.py lifespan)
"""

import asyncpg
from contextlib import asynccontextmanager
from typing import Optional, Union
from urllib.parse import urlparse
from app.config import config


# Hosts that speak plain TCP with no TLS: Railway's private network, a Postgres
# container on a compose/Docker network, and anything local.
_NO_TLS_SUFFIXES = (".railway.internal",)
_NO_TLS_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}


def _resolve_ssl() -> Union[str, bool]:
    """
    Decide whether to require TLS for the database connection.

    Set DB_SSL explicitly ('require' | 'prefer' | 'disable') to override.
    Otherwise TLS is required for managed providers (Supabase, Koyeb, Neon) and
    skipped for Railway's private network and local/containerised Postgres,
    which do not terminate TLS and will refuse the handshake.
    """
    override = (config.DB_SSL or "").strip().lower()
    if override:
        return False if override == "disable" else override

    host = (urlparse(config.DATABASE_URL).hostname or "").lower()
    if host in _NO_TLS_HOSTS or host.endswith(_NO_TLS_SUFFIXES):
        return False
    return "require"

# ---------------------------------------------------------------------------
# Module-level pool — None until init_db() is called
# ---------------------------------------------------------------------------
_pool: Optional[asyncpg.Pool] = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """
    Create the asyncpg connection pool.
    Call this once at application startup.
    """
    global _pool

    ssl_mode = _resolve_ssl()

    _pool = await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=config.DB_POOL_MIN,
        max_size=config.DB_POOL_MAX,
        command_timeout=30,  # seconds before a query is killed
        ssl=ssl_mode,
    )
    print(f"[DB] Connection pool created ✅ (ssl={ssl_mode or 'disabled'})")


async def close_db() -> None:
    """
    Close all connections in the pool.
    Call this once at application shutdown.
    """
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[DB] Connection pool closed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_pool() -> asyncpg.Pool:
    """Return the pool — raises if init_db() was never called."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_db() first.")
    return _pool


@asynccontextmanager
async def get_connection():
    """
    Async context manager that yields a single connection from the pool.

    Example:
        async with get_connection() as conn:
            row = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
    """
    pool = get_pool()
    async with pool.acquire() as connection:
        yield connection


async def pool_query(query: str, *args):
    """
    Run a SELECT and return all rows — convenience wrapper.

    Example:
        rows = await pool_query("SELECT * FROM issues WHERE status = $1", "open")
    """
    async with get_connection() as conn:
        return await conn.fetch(query, *args)


async def pool_fetchrow(query: str, *args):
    """
    Run a SELECT and return a single row (or None).

    Example:
        row = await pool_fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    """
    async with get_connection() as conn:
        return await conn.fetchrow(query, *args)


async def pool_execute(query: str, *args) -> str:
    """
    Run an INSERT / UPDATE / DELETE. Returns the command tag string.

    Example:
        tag = await pool_execute(
            "UPDATE users SET total_points = $1 WHERE id = $2",
            new_points, user_id
        )
    """
    async with get_connection() as conn:
        return await conn.execute(query, *args)


async def pool_executemany(query: str, args_list: list) -> None:
    """
    Run the same statement for multiple rows in one round trip.

    Example:
        await pool_executemany(
            "INSERT INTO user_badges (user_id, badge_type) VALUES ($1, $2)",
            [(uid1, "bronze"), (uid2, "silver")]
        )
    """
    async with get_connection() as conn:
        await conn.executemany(query, args_list)


async def pool_fetchval(query: str, *args):
    """
    Run a SELECT and return a single scalar value (or None).

    Example:
        count = await pool_fetchval("SELECT COUNT(*) FROM users")
    """
    async with get_connection() as conn:
        return await conn.fetchval(query, *args)
