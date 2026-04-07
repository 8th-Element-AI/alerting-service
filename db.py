import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from psycopg_pool import ConnectionPool

from utils.logger import get_logger

logger = get_logger(__name__)

_pool: Optional[ConnectionPool] = None


def get_database_url() -> Optional[str]:
    url = (os.getenv("DATABASE_URL") or "").strip()
    return url or None


def init_pool(database_url: str) -> None:
    """Create the shared connection pool. Safe to call multiple times (no-op after first)."""
    global _pool
    if _pool is not None:
        return
    min_size = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
    max_size = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
    pool_timeout = float(os.getenv("DB_POOL_TIMEOUT", "5"))
    statement_timeout = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "5000"))
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
    _pool = ConnectionPool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        timeout=pool_timeout,
        kwargs={
            "connect_timeout": connect_timeout,
            "options": f"-c statement_timeout={statement_timeout}",
        },
        open=True,
    )
    logger.info(
        f"DB connection pool created (min={min_size}, max={max_size}, "
        f"pool_timeout={pool_timeout}s, connect_timeout={connect_timeout}s, "
        f"statement_timeout={statement_timeout}ms)."
    )


def _get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool() or init_db() at startup.")
    return _pool


def init_db(database_url: str) -> None:
    init_pool(database_url)
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists errors (
                    id bigserial primary key,
                    received_at timestamptz,
                    error_type text not null,
                    error_message text not null,
                    stack_trace text not null,
                    service_name text,
                    environment text,
                    source_ip text,
                    mail_sent boolean not null default false,
                    mail_sent_at timestamptz,
                    payload jsonb not null
                );

                create table if not exists error_state (
                    error_key text primary key,
                    last_alerted_at timestamptz,
                    updated_at timestamptz not null default now()
                );

                create index if not exists idx_errors_received_at on errors (received_at desc);
                create index if not exists idx_errors_service on errors (service_name);
                create index if not exists idx_errors_type on errors (error_type);
                """
            )

            # Backwards-compatible migrations for existing DBs
            cur.execute("alter table errors add column if not exists mail_sent boolean not null default false;")
            cur.execute("alter table errors add column if not exists mail_sent_at timestamptz;")
        conn.commit()


def insert_error(payload: Dict[str, Any]) -> int:
    received_at = payload.get("received_at")
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into errors (
                    received_at,
                    error_type,
                    error_message,
                    stack_trace,
                    service_name,
                    environment,
                    source_ip,
                    mail_sent,
                    mail_sent_at,
                    payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                (
                    received_at,
                    payload.get("error_type"),
                    payload.get("error_message"),
                    payload.get("stack_trace"),
                    payload.get("service_name"),
                    payload.get("environment"),
                    payload.get("source_ip"),
                    False,
                    None,
                    json.dumps(payload),
                ),
            )
            row = cur.fetchone()
            assert row is not None
            inserted_id = int(row[0])
        conn.commit()
    return inserted_id


def mark_mail_sent(*, error_id: int, sent: bool) -> None:
    now = datetime.now(timezone.utc)
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update errors
                set mail_sent=%s,
                    mail_sent_at=case when %s then %s else null end
                where id=%s
                """,
                (sent, sent, now, error_id),
            )
        conn.commit()


def get_last_alerted_at(error_key: str) -> Optional[datetime]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select last_alerted_at from error_state where error_key=%s",
                (error_key,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def set_last_alerted_at(error_key: str) -> None:
    now = datetime.now(timezone.utc)
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into error_state (error_key, last_alerted_at, updated_at)
                values (%s, %s, %s)
                on conflict (error_key) do update
                set last_alerted_at=%s, updated_at=%s
                """,
                (error_key, now, now, now, now),
            )
        conn.commit()
