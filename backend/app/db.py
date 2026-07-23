import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "butaca.db"

# Las sesiones expiran: un token robado deja de servir pasado esto.
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 días


def _hash_token(token: str) -> str:
    # Igual que los tokens de reset/verificación (auth.hash_token — duplicado
    # acá porque auth importa db y sería circular): en la DB solo viven
    # hasheados, así una filtración de la DB no regala sesiones activas.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    email TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_attempts (
    username TEXT PRIMARY KEY,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rated_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    rating REAL NOT NULL,
    review TEXT NOT NULL DEFAULT '',
    watched_date TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recommendation_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    mood TEXT NOT NULL DEFAULT '',
    taste_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recommendations_served (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES recommendation_sessions(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    tmdb_id INTEGER,
    title TEXT NOT NULL,
    year INTEGER NOT NULL,
    kind TEXT NOT NULL,
    why TEXT NOT NULL,
    match_score INTEGER NOT NULL,
    tags TEXT NOT NULL,
    mood TEXT NOT NULL DEFAULT '',
    poster_path TEXT,
    backdrop_path TEXT,
    overview TEXT NOT NULL DEFAULT '',
    vote_average REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    recommendation_id INTEGER NOT NULL REFERENCES recommendations_served(id),
    status TEXT NOT NULL CHECK (status IN ('interested', 'not_interested', 'seen')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS taste_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    profile_json TEXT NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL
);
"""

# same tables as SCHEMA_SQLITE, adapted for Postgres (Neon): SERIAL instead of
# AUTOINCREMENT, and a DEFAULT that renders the identical "YYYY-MM-DD HH:MM:SS"
# UTC string SQLite's datetime('now') produces — frontend/src/pages/History.tsx
# parses created_at by appending "Z", so both backends must match that format.
_PG_NOW = "to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')"
SCHEMA_POSTGRES = f"""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    email TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW}),
    expires_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_attempts (
    username TEXT PRIMARY KEY,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS rated_items (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    rating REAL NOT NULL,
    review TEXT NOT NULL DEFAULT '',
    watched_date TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS recommendation_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    mood TEXT NOT NULL DEFAULT '',
    taste_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS recommendations_served (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES recommendation_sessions(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    tmdb_id INTEGER,
    title TEXT NOT NULL,
    year INTEGER NOT NULL,
    kind TEXT NOT NULL,
    why TEXT NOT NULL,
    match_score INTEGER NOT NULL,
    tags TEXT NOT NULL,
    mood TEXT NOT NULL DEFAULT '',
    poster_path TEXT,
    backdrop_path TEXT,
    overview TEXT NOT NULL DEFAULT '',
    vote_average REAL,
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    recommendation_id INTEGER NOT NULL REFERENCES recommendations_served(id),
    status TEXT NOT NULL CHECK (status IN ('interested', 'not_interested', 'seen')),
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS taste_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    profile_json TEXT NOT NULL,
    computed_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL
);
"""


def _db_path() -> str:
    return os.environ.get("BUTACA_DB_PATH", str(DEFAULT_DB_PATH))


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or None


def _is_postgres() -> bool:
    return _database_url() is not None


def qmark_to_pyformat(sql: str) -> str:
    """Translate sqlite3's '?' placeholders to psycopg2's '%s'.

    Safe here because none of this module's queries contain a literal '?'
    inside a string — every '?' is a parameter placeholder.
    """
    return sql.replace("?", "%s")


class _PostgresConnWrapper:
    """Makes a psycopg2 connection quack like sqlite3.Connection for this
    module's call sites: conn.execute(...).fetchone()/.fetchall(), and
    conn.executemany(...). Reuses one cursor since no call site here nests
    or interleaves cursors within the same `with get_connection()` block."""

    def __init__(self, pg_conn):
        self._conn = pg_conn
        self._cursor = pg_conn.cursor()

    def execute(self, sql, params=()):
        self._cursor.execute(qmark_to_pyformat(sql), params)
        return self._cursor

    def executemany(self, sql, seq_of_params):
        self._cursor.executemany(qmark_to_pyformat(sql), seq_of_params)
        return self._cursor

    def executescript(self, sql):
        self._cursor.execute(sql)

    def commit(self):
        self._conn.commit()


def _has_column(conn, table: str, column: str) -> bool:
    if _is_postgres():
        row = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
            (table, column),
        ).fetchone()
        return row is not None
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in columns)


def _run_migrations(conn) -> None:
    if not _has_column(conn, "recommendations_served", "session_id"):
        conn.execute(
            "ALTER TABLE recommendations_served ADD COLUMN session_id INTEGER REFERENCES recommendation_sessions(id)"
        )
    if not _has_column(conn, "recommendations_served", "tmdb_id"):
        conn.execute("ALTER TABLE recommendations_served ADD COLUMN tmdb_id INTEGER")
    if not _has_column(conn, "rated_items", "watched_date"):
        conn.execute("ALTER TABLE rated_items ADD COLUMN watched_date TEXT NOT NULL DEFAULT ''")
    if not _has_column(conn, "users", "email"):
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if not _has_column(conn, "users", "email_verified"):
        conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
    if not _has_column(conn, "sessions", "expires_at"):
        # Las filas preexistentes quedan con expires_at=0 → expiradas. A la vez
        # se pasó a guardar el token hasheado, así que esas filas viejas (token
        # crudo) no matchearían igual: se borran acá y los usuarios se loguean
        # de nuevo una única vez.
        conn.execute("ALTER TABLE sessions ADD COLUMN expires_at INTEGER NOT NULL DEFAULT 0")
        conn.execute("DELETE FROM sessions")


def _last_insert_id(conn, cursor):
    """cursor.lastrowid works for sqlite3; psycopg2 has no equivalent, so
    Postgres INSERTs that need the new id append RETURNING id and this reads
    it back from the same cursor instead."""
    if _is_postgres():
        return cursor.fetchone()["id"]
    return cursor.lastrowid


_PG_POOL = None  # psycopg2.pool.ThreadedConnectionPool, created lazily on first use

# ponytail: keyed by target (db path, or the Postgres URL) rather than a
# bare bool — tests point BUTACA_DB_PATH at a fresh tmp file per test, so a
# single global flag would skip schema creation for every db after the first.
# Harmless if two threads race this at cold start: CREATE TABLE IF NOT EXISTS
# is idempotent, worst case is redundant work once, not a correctness bug.
_initialized_targets: set[str] = set()


def _get_pg_pool():
    global _PG_POOL
    if _PG_POOL is None:
        from psycopg2.pool import ThreadedConnectionPool

        _PG_POOL = ThreadedConnectionPool(1, 10, _database_url())
    return _PG_POOL


def _ensure_schema_ready(conn) -> None:
    target = _database_url() or _db_path()
    if target in _initialized_targets:
        return
    conn.executescript(SCHEMA_POSTGRES if _is_postgres() else SCHEMA_SQLITE)
    _run_migrations(conn)
    conn.commit()
    _initialized_targets.add(target)


@contextmanager
def get_connection():
    # ponytail: this used to run executescript()+_run_migrations() on every
    # single call — each round trip crosses Render <-> Neon's cross-region
    # link (~400-500ms), so a connection alone used to cost ~3s before any
    # actual query ran, which is most of why login and every other
    # DB-touching request felt slow. _ensure_schema_ready now only pays that
    # cost once per process. Postgres also reuses a pooled connection instead
    # of a fresh TCP+TLS handshake per request.
    if _is_postgres():
        from psycopg2.extras import RealDictCursor

        pool = _get_pg_pool()
        pg_conn = pool.getconn()
        pg_conn.cursor_factory = RealDictCursor
        conn = _PostgresConnWrapper(pg_conn)
        _ensure_schema_ready(conn)
        try:
            yield conn
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()
            raise
        finally:
            conn._cursor.close()
            pool.putconn(pg_conn)
    else:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_schema_ready(conn)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def create_user(username: str, password_hash: str, password_salt: str, email: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, password_salt, email) VALUES (?, ?, ?, ?)"
            + (" RETURNING id" if _is_postgres() else ""),
            (username, password_hash, password_salt, email),
        )
        return _last_insert_id(conn, cursor)


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def create_session(token: str, user_id: int) -> None:
    now = int(time.time())
    with get_connection() as conn:
        # limpieza oportunista: las sesiones vencidas no sirven para nada
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (_hash_token(token), user_id, now + SESSION_TTL_SECONDS),
        )


def get_user_by_token(token: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (_hash_token(token), int(time.time())),
        ).fetchone()


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (_hash_token(token),))


def delete_sessions_for_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def update_user_password(user_id: int, password_hash: str, password_salt: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?",
            (password_hash, password_salt, user_id),
        )


def get_login_attempt(username: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM login_attempts WHERE username = ?", (username,)
        ).fetchone()


def save_login_attempt(username: str, failed_attempts: int, locked_until: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO login_attempts (username, failed_attempts, locked_until)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                failed_attempts = excluded.failed_attempts,
                locked_until = excluded.locked_until
            """,
            (username, failed_attempts, locked_until),
        )


def clear_login_attempts(username: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM login_attempts WHERE username = ?", (username,))


def save_password_reset_token(user_id: int, token_hash: str, expires_at: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )


def get_password_reset_token(token_hash: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT password_reset_tokens.*, users.username
            FROM password_reset_tokens
            JOIN users ON users.id = password_reset_tokens.user_id
            WHERE password_reset_tokens.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()


def delete_password_reset_tokens_for_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))


def save_email_verification_token(user_id: int, token_hash: str, expires_at: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO email_verification_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )


def get_email_verification_token(token_hash: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT email_verification_tokens.*, users.username
            FROM email_verification_tokens
            JOIN users ON users.id = email_verification_tokens.user_id
            WHERE email_verification_tokens.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()


def mark_email_verified(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,))


def delete_user_completely(user_id: int, username: str) -> None:
    """Wipe a user and everything that references them, child tables first so
    FK constraints hold (SQLite runs with foreign_keys=ON). One connection =
    one transaction: get_connection commits on clean exit, rolls back on error,
    so a partial delete can't leave orphaned rows. login_attempts is keyed by
    username, not user_id."""
    with get_connection() as conn:
        conn.execute("DELETE FROM feedback WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM recommendations_served WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM recommendation_sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM rated_items WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM taste_profiles WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM watchlist_items WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def save_rated_items(user_id: int, items: list[tuple[str, float, str, str]]) -> None:
    if not items:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO rated_items (user_id, title, rating, review, watched_date) VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, title, rating, review, watched_date)
                for title, rating, review, watched_date in items
            ],
        )


def get_watched_items(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT title, rating, review, watched_date, created_at
            FROM rated_items
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    seen_titles: set[str] = set()
    items: list[dict] = []
    for row in rows:
        normalized_title = row["title"].strip().lower()
        if normalized_title not in seen_titles:
            seen_titles.add(normalized_title)
            items.append(dict(row))
    return items


def get_profile_summary(user_id: int) -> dict:
    """Datos de cuenta + resumen de actividad para la página de perfil, todo
    en una conexión. AS n en los COUNT para que la fila lea igual vía
    sqlite3.Row y RealDictCursor (mismo criterio que count_sessions_since)."""
    with get_connection() as conn:
        user = conn.execute(
            "SELECT username, email, email_verified, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        rated = conn.execute(
            "SELECT COUNT(DISTINCT title) AS n FROM rated_items WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"]
        sessions = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendation_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"]
        feedback_count = conn.execute(
            "SELECT COUNT(*) AS n FROM feedback WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"]
        watchlist = conn.execute(
            "SELECT COUNT(*) AS n FROM watchlist_items WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"]
        top = conn.execute(
            "SELECT title, rating FROM rated_items WHERE user_id = ? ORDER BY rating DESC, id DESC LIMIT 1",
            (user_id,),
        ).fetchone()

    return {
        "username": user["username"],
        "email": user["email"],
        "email_verified": bool(user["email_verified"]),
        "member_since": user["created_at"],
        "rated_count": rated,
        "session_count": sessions,
        "feedback_count": feedback_count,
        "watchlist_count": watchlist,
        "top_title": top["title"] if top else None,
        "top_rating": top["rating"] if top else None,
    }


def create_recommendation_session(user_id: int, mood: str, taste_summary: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recommendation_sessions (user_id, mood, taste_summary)
            VALUES (?, ?, ?)
            """
            + (" RETURNING id" if _is_postgres() else ""),
            (user_id, mood, taste_summary),
        )
        return _last_insert_id(conn, cursor)


def count_sessions_since(user_id: int, since: str) -> int:
    # created_at is a lexicographically-sortable "YYYY-MM-DD HH:MM:SS" UTC
    # string in both backends, so a plain string >= comparison is a correct
    # datetime comparison — no datetime() / date functions needed (those
    # differ between SQLite and Postgres). AS n aliases COUNT(*) so the row
    # reads the same via sqlite3.Row and psycopg2's RealDictCursor.
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendation_sessions WHERE user_id = ? AND created_at >= ?",
            (user_id, since),
        ).fetchone()
    return row["n"]


def save_recommendations(session_id: int, user_id: int, mood: str, items: list[dict]) -> list[int]:
    ids: list[int] = []
    with get_connection() as conn:
        for item in items:
            cursor = conn.execute(
                """
                INSERT INTO recommendations_served
                    (session_id, user_id, tmdb_id, title, year, kind, why, match_score, tags, mood,
                     poster_path, backdrop_path, overview, vote_average)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                + (" RETURNING id" if _is_postgres() else ""),
                (
                    session_id,
                    user_id,
                    item.get("tmdb_id"),
                    item["title"],
                    item["year"],
                    item["kind"],
                    item["why"],
                    item["match_score"],
                    json.dumps(item["tags"]),
                    mood,
                    item.get("poster_path"),
                    item.get("backdrop_path"),
                    item.get("overview", ""),
                    item.get("vote_average"),
                ),
            )
            ids.append(_last_insert_id(conn, cursor))
    return ids


def get_recently_recommended_titles(user_id: int, limit: int = 100) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT title FROM recommendations_served WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [row["title"] for row in rows]


def get_recommendation_history(user_id: int) -> list[dict]:
    with get_connection() as conn:
        sessions = conn.execute(
            """
            SELECT id, mood, taste_summary, created_at
            FROM recommendation_sessions
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
        if not sessions:
            return []

        recommendations = conn.execute(
            """
            SELECT
                id, session_id, tmdb_id, title, year, kind, why, match_score, tags, poster_path,
                backdrop_path, overview, vote_average
            FROM recommendations_served
            WHERE user_id = ? AND session_id IS NOT NULL
            ORDER BY session_id DESC, id ASC
            """,
            (user_id,),
        ).fetchall()

    recommendations_by_session: dict[int, list[dict]] = {}
    for row in recommendations:
        recommendations_by_session.setdefault(row["session_id"], []).append(
            {
                "id": row["id"],
                "tmdb_id": row["tmdb_id"],
                "title": row["title"],
                "year": row["year"],
                "kind": row["kind"],
                "why": row["why"],
                "match_score": row["match_score"],
                "tags": json.loads(row["tags"]),
                "poster_path": row["poster_path"],
                "backdrop_path": row["backdrop_path"],
                "overview": row["overview"],
                "vote_average": row["vote_average"],
            }
        )

    return [
        {
            "id": session["id"],
            "mood": session["mood"],
            "taste_summary": session["taste_summary"],
            "created_at": session["created_at"],
            "recommendations": recommendations_by_session.get(session["id"], []),
        }
        for session in sessions
    ]


def get_recommendation_session(session_id: int, user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, mood, taste_summary FROM recommendation_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
    return dict(row) if row is not None else None


def get_session_recommendations(session_id: int, user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, tmdb_id, title, year, kind, why, match_score, tags,
                   poster_path, backdrop_path, overview, vote_average
            FROM recommendations_served
            WHERE session_id = ? AND user_id = ?
            ORDER BY id ASC
            """,
            (session_id, user_id),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "tmdb_id": row["tmdb_id"],
            "title": row["title"],
            "year": row["year"],
            "kind": row["kind"],
            "why": row["why"],
            "match_score": row["match_score"],
            "tags": json.loads(row["tags"]),
            "poster_path": row["poster_path"],
            "backdrop_path": row["backdrop_path"],
            "overview": row["overview"],
            "vote_average": row["vote_average"],
        }
        for row in rows
    ]


def update_session_refinement(
    session_id: int, taste_summary: str, why_by_id: list[tuple[int, str]]
) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE recommendation_sessions SET taste_summary = ? WHERE id = ?",
            (taste_summary, session_id),
        )
        for rec_id, why in why_by_id:
            conn.execute(
                "UPDATE recommendations_served SET why = ? WHERE id = ?", (why, rec_id)
            )


def get_recommendation(recommendation_id: int, user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM recommendations_served WHERE id = ? AND user_id = ?",
            (recommendation_id, user_id),
        ).fetchone()


def save_feedback(user_id: int, recommendation_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO feedback (user_id, recommendation_id, status) VALUES (?, ?, ?)",
            (user_id, recommendation_id, status),
        )


def get_feedback_signals(user_id: int) -> dict:
    """Latest feedback per recommendation for this user, split into what
    recommend() consumes: titles marked seen/not_interested (excluded from
    future picks) and the tags of not_interested picks (penalized in scoring).
    'interested' is stored but not a signal here."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT feedback.recommendation_id, feedback.status,
                   recommendations_served.title, recommendations_served.tags
            FROM feedback
            JOIN recommendations_served
                ON recommendations_served.id = feedback.recommendation_id
            WHERE feedback.user_id = ?
            ORDER BY feedback.id ASC
            """,
            (user_id,),
        ).fetchall()

    # a user can re-submit feedback for the same pick; ASC order + overwrite
    # keeps the most recent verdict per recommendation
    latest: dict[int, dict] = {}
    for row in rows:
        latest[row["recommendation_id"]] = {
            "status": row["status"],
            "title": row["title"],
            "tags": json.loads(row["tags"]),
        }

    seen_titles: list[str] = []
    not_interested: list[dict] = []
    for entry in latest.values():
        if entry["status"] == "seen":
            seen_titles.append(entry["title"])
        elif entry["status"] == "not_interested":
            not_interested.append({"title": entry["title"], "tags": entry["tags"]})
    return {"seen_titles": seen_titles, "not_interested": not_interested}


def get_admin_stats() -> dict:
    """Aggregate counts for the metrics defined in docs/product-mvp.md. All
    COUNTs aliased AS n and all date cutoffs done by string comparison on
    created_at, so the same SQL runs on SQLite and Postgres."""
    now = datetime.now(timezone.utc)
    since_7 = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    since_30 = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        sessions_total = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendation_sessions"
        ).fetchone()["n"]
        sessions_7 = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendation_sessions WHERE created_at >= ?", (since_7,)
        ).fetchone()["n"]
        sessions_30 = conn.execute(
            "SELECT COUNT(*) AS n FROM recommendation_sessions WHERE created_at >= ?", (since_30,)
        ).fetchone()["n"]
        picks_served = conn.execute("SELECT COUNT(*) AS n FROM recommendations_served").fetchone()["n"]
        feedback_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM feedback GROUP BY status"
        ).fetchall()

    feedback = {row["status"]: row["n"] for row in feedback_rows}
    counts = {status: feedback.get(status, 0) for status in ("interested", "not_interested", "seen")}
    counts["total"] = sum(counts.values())
    rate = {
        status: (round(100 * counts[status] / picks_served, 1) if picks_served else 0.0)
        for status in ("interested", "not_interested", "seen")
    }
    return {
        "users": users,
        "sessions": {"total": sessions_total, "last_7_days": sessions_7, "last_30_days": sessions_30},
        "picks_served": picks_served,
        "feedback": counts,
        "feedback_rate_pct": rate,
    }


def save_taste_profile(user_id: int, profile: dict) -> None:
    # ponytail: computed_at is set explicitly (not left to the column
    # DEFAULT) because this is an upsert and the DEFAULT only applies on
    # insert — an update needs a fresh value. datetime('now') is SQLite-only
    # and used to crash this on Postgres (see git history); compute the same
    # "YYYY-MM-DD HH:MM:SS" UTC string in Python instead so it works on both.
    computed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO taste_profiles (user_id, profile_json, computed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_json = excluded.profile_json,
                computed_at = excluded.computed_at
            """,
            (user_id, json.dumps(profile), computed_at),
        )


def get_taste_profile(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT profile_json FROM taste_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    return json.loads(row["profile_json"]) if row is not None else None


def save_watchlist_items(user_id: int, titles: list[str]) -> None:
    # replace-all: a freshly imported watchlist IS the current state, so wipe
    # the old rows and reinsert rather than trying to diff.
    with get_connection() as conn:
        conn.execute("DELETE FROM watchlist_items WHERE user_id = ?", (user_id,))
        if titles:
            conn.executemany(
                "INSERT INTO watchlist_items (user_id, title) VALUES (?, ?)",
                [(user_id, title) for title in titles],
            )


def get_watchlist_items(user_id: int) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT title FROM watchlist_items WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
    return [row["title"] for row in rows]
