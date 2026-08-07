import hashlib
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "butaca.db"

# Las sesiones expiran: un token robado deja de servir pasado esto.
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 días
RATING_SOURCE_PRIORITY = {"import": 3, "star": 2, "manual": 1, "like": 0}


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
    is_guest INTEGER NOT NULL DEFAULT 0,
    google_sub TEXT UNIQUE,
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
    -- 'import' (Letterboxd, rating numerico real 0.5-5.0) vs 'manual' (click
    -- de boton en el modo "Sin cuenta", mapeado a un rating sintetico) — la
    -- distincion importa solo para como se CITA el rating en el "why" del
    -- LLM, no para el scoring (que trata ambos igual)
    source TEXT NOT NULL DEFAULT 'import',
    -- id de TMDb ya resuelto (el tmdb:movieId del feed RSS de username) —
    -- NULL para zip/manual, que no lo traen. Cuando está, se evita una
    -- búsqueda por texto en taste_profile/_enrich_loved_ratings_with_genre_tags
    tmdb_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- "puntuar más" (/titles/swipe-batch): registra cada título YA ofrecido a
-- este usuario (lo haya puntuado o marcado "no la vi") para que la próxima
-- tanda rote de verdad y nunca repita nada -- pedido explícito de Matías,
-- 2026-08-03.
CREATE TABLE IF NOT EXISTS swipe_asked_titles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- _swipe_popular_pool arrancaba SIEMPRE de la página 1 de TMDb populares y
-- confiaba en swipe_asked_titles para saltear lo ya visto -- para un usuario
-- con historial grande (mucho ya visto/ya ofrecido) eso significa: cada
-- llamada más lenta (rescanea más páginas ya agotadas) y, al llegar al tope
-- de SWIPE_POPULAR_MAX_PAGES, un muro permanente sin salida ("esto no puede
-- pasar", reportado por Matías 2026-08-03). Este cursor recuerda por dónde
-- se quedó cada kind para retomar ahí la próxima vez, en vez de rescanear
-- desde cero.
CREATE TABLE IF NOT EXISTS swipe_pool_cursor (
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    next_page INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, kind)
);

-- juego "¿cuál te gustó más?": solo compara títulos que el usuario YA vio y
-- puntuó (nunca inventa un "vista" falso). Elegir un ganador no le pone un
-- rating nuevo -- ambos ya tienen uno real -- sino que queda como preferencia
-- relativa, usada por recommender._find_reference_title para desempatar
-- entre "amados" con el mismo rating (bug + rediseño reportados por Matías,
-- 2026-08-03).
CREATE TABLE IF NOT EXISTS pairwise_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    winner_title TEXT NOT NULL,
    loser_title TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS title_embeddings (
    tmdb_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    model TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tmdb_id, kind, model)
);

CREATE TABLE IF NOT EXISTS title_clusters (
    tmdb_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    l1_cluster_id INTEGER NOT NULL,
    l2_cluster_id INTEGER NOT NULL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tmdb_id, kind)
);

CREATE TABLE IF NOT EXISTS cluster_labels (
    level INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    sample_titles TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (level, cluster_id)
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
    is_guest INTEGER NOT NULL DEFAULT 0,
    google_sub TEXT UNIQUE,
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
    source TEXT NOT NULL DEFAULT 'import',
    tmdb_id INTEGER,
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS swipe_asked_titles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT ({_PG_NOW})
);

CREATE TABLE IF NOT EXISTS swipe_pool_cursor (
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,
    next_page INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, kind)
);

CREATE TABLE IF NOT EXISTS pairwise_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    winner_title TEXT NOT NULL,
    loser_title TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS title_embeddings (
    tmdb_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    model TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    computed_at TEXT NOT NULL DEFAULT ({_PG_NOW}),
    PRIMARY KEY (tmdb_id, kind, model)
);

CREATE TABLE IF NOT EXISTS title_clusters (
    tmdb_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    l1_cluster_id INTEGER NOT NULL,
    l2_cluster_id INTEGER NOT NULL,
    computed_at TEXT NOT NULL DEFAULT ({_PG_NOW}),
    PRIMARY KEY (tmdb_id, kind)
);

CREATE TABLE IF NOT EXISTS cluster_labels (
    level INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    sample_titles TEXT NOT NULL DEFAULT '',
    size INTEGER NOT NULL DEFAULT 0,
    computed_at TEXT NOT NULL DEFAULT ({_PG_NOW}),
    PRIMARY KEY (level, cluster_id)
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
    if not _has_column(conn, "rated_items", "source"):
        conn.execute("ALTER TABLE rated_items ADD COLUMN source TEXT NOT NULL DEFAULT 'import'")
    if not _has_column(conn, "rated_items", "tmdb_id"):
        conn.execute("ALTER TABLE rated_items ADD COLUMN tmdb_id INTEGER")
    if not _has_column(conn, "users", "email"):
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if not _has_column(conn, "users", "email_verified"):
        conn.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")
    if not _has_column(conn, "users", "letterboxd_username"):
        # Tu usuario de Letterboxd (pedido de Matías, 2026-07-31). No es solo
        # una comodidad para no re-tipearlo: importar por username persiste los
        # ratings al perfil, así que un amigo probando la página con SU usuario
        # te pisaba el tuyo. Con esto seteado, un username distinto genera
        # recomendaciones sin guardar nada.
        conn.execute("ALTER TABLE users ADD COLUMN letterboxd_username TEXT")
    if not _has_column(conn, "users", "is_guest"):
        # Columna explícita en vez de deducirlo de email IS NULL: la migración
        # que agregó `email` dejó en NULL a los usuarios pre-existentes, así
        # que hay cuentas reales sin email que no son invitados.
        conn.execute("ALTER TABLE users ADD COLUMN is_guest INTEGER NOT NULL DEFAULT 0")
    if not _has_column(conn, "users", "google_sub"):
        # el `sub` de Google, no el mail: el mail de una cuenta de Google puede
        # cambiar, el sub no. UNIQUE va aparte porque ALTER TABLE ADD COLUMN no
        # lo acepta en SQLite.
        conn.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)"
        )
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


def _checkout_live_connection(pool):
    """Sacar del pool una conexión que de verdad siga viva.

    Neon es serverless y cierra las conexiones ociosas por su cuenta, pero
    `pool.getconn()` te la devuelve igual: `closed` solo refleja lo que sabe
    este proceso, no que el server la haya cortado del otro lado. La primera
    query real explota entonces con "SSL connection has been closed
    unexpectedly" (visto 2026-08-02 guardando los clusters después de ~6 min
    sin tocar la base). El `SELECT 1` es la única forma de enterarse antes.

    No es un caso de borde del job offline: en producción UptimeRobot mantiene
    el proceso vivo pegándole a /health, que no toca la base — así que el pool
    puede quedarse horas con conexiones que Neon ya cerró, y el primer usuario
    que llega después se come un 500.
    """
    import psycopg2

    last_error = None
    for _ in range(3):
        conn = pool.getconn()
        try:
            with conn.cursor() as probe:
                probe.execute("SELECT 1")
            return conn
        except psycopg2.Error as exc:  # conexión muerta: descartarla y pedir otra
            last_error = exc
            pool.putconn(conn, close=True)
    raise last_error


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
        pg_conn = _checkout_live_connection(pool)
        pg_conn.cursor_factory = RealDictCursor
        conn = _PostgresConnWrapper(pg_conn)
        _ensure_schema_ready(conn)
        try:
            yield conn
            pg_conn.commit()
        except Exception:
            # el rollback va best-effort: si lo que falló fue la conexión, este
            # rollback tira InterfaceError y taparía el error de verdad, que es
            # el que dice qué pasó (visto 2026-08-02).
            try:
                pg_conn.rollback()
            except Exception:
                logger.warning("Rollback fallido, la conexión ya estaba caída", exc_info=True)
            raise
        finally:
            try:
                conn._cursor.close()
            except Exception:
                pass
            pool.putconn(pg_conn, close=pg_conn.closed != 0)
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


def create_user(
    username: str,
    password_hash: str,
    password_salt: str,
    email: str | None,
    is_guest: bool = False,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, password_salt, email, is_guest)"
            " VALUES (?, ?, ?, ?, ?)"
            + (" RETURNING id" if _is_postgres() else ""),
            (username, password_hash, password_salt, email, int(is_guest)),
        )
        return _last_insert_id(conn, cursor)


def get_user_by_google_sub(google_sub: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
        ).fetchone()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def link_google_account(user_id: int, google_sub: str, email: str) -> None:
    """Ata una cuenta existente a Google. Marca el mail como verificado porque
    Google ya lo verificó (y solo llegamos acá con email_verified del token)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET google_sub = ?, email = ?, email_verified = 1, is_guest = 0"
            " WHERE id = ?",
            (google_sub, email, user_id),
        )


def claim_guest_account(
    user_id: int, username: str, password_hash: str, password_salt: str, email: str
) -> None:
    """Convierte al invitado en cuenta real sobre la MISMA fila, para que su
    historial y sus ratings sobrevivan — registrarse de cero crearía un
    usuario nuevo y el invitado perdería todo lo que puntuó."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET username = ?, password_hash = ?, password_salt = ?,"
            " email = ?, is_guest = 0 WHERE id = ?",
            (username, password_hash, password_salt, email, user_id),
        )


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def set_letterboxd_username(user_id: int, letterboxd_username: str) -> None:
    """Cadena vacía = desvincular (vuelve a NULL), así el perfil puede borrarlo
    sin un endpoint aparte."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET letterboxd_username = ? WHERE id = ?",
            (letterboxd_username.strip() or None, user_id),
        )


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


def save_rated_items(
    user_id: int, items: list[tuple[str, float, str, str, str, int | None]]
) -> None:
    if not items:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO rated_items (user_id, title, rating, review, watched_date, source, tmdb_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (user_id, title, rating, review, watched_date, source, tmdb_id)
                for title, rating, review, watched_date, source, tmdb_id in items
            ],
        )


def get_swipe_asked_titles(user_id: int) -> set[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT title FROM swipe_asked_titles WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {row["title"].strip().lower() for row in rows}


def record_swipe_asked_titles(user_id: int, titles: list[str]) -> None:
    if not titles:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO swipe_asked_titles (user_id, title) VALUES (?, ?)",
            [(user_id, title) for title in titles],
        )


def get_swipe_pool_cursor(user_id: int, kind: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT next_page FROM swipe_pool_cursor WHERE user_id = ? AND kind = ?", (user_id, kind)
        ).fetchone()
    return row["next_page"] if row else 1


def set_swipe_pool_cursor(user_id: int, kind: str, next_page: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO swipe_pool_cursor (user_id, kind, next_page)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, kind) DO UPDATE SET next_page = excluded.next_page
            """,
            (user_id, kind, next_page),
        )


def record_pairwise_preference(user_id: int, winner_title: str, loser_title: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO pairwise_preferences (user_id, winner_title, loser_title) VALUES (?, ?, ?)",
            (user_id, winner_title, loser_title),
        )


def get_pairwise_win_counts(user_id: int) -> dict[str, int]:
    """Cuántas veces ganó cada título (normalizado) en el juego "¿cuál te
    gustó más?" — usado solo para desempatar entre "amados" con el mismo
    rating en recommender._find_reference_title, no para el scoring."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT winner_title, COUNT(*) AS wins FROM pairwise_preferences WHERE user_id = ? GROUP BY winner_title",
            (user_id,),
        ).fetchall()
    return {row["winner_title"].strip().lower(): row["wins"] for row in rows}


def get_watched_items(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT title, rating, review, watched_date, source, tmdb_id, created_at
            FROM rated_items
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    # Un rating preciso de Letterboxd es la fuente de verdad aunque haya un
    # click de Butaca posterior. Entre filas de la misma fuente gana la más
    # reciente porque la query ya viene DESC.
    items_by_title: dict[str, dict] = {}
    for row in rows:
        normalized_title = row["title"].strip().lower()
        current = items_by_title.get(normalized_title)
        item = dict(row)
        if current is None or RATING_SOURCE_PRIORITY.get(
            item["source"], 0
        ) > RATING_SOURCE_PRIORITY.get(current["source"], 0):
            items_by_title[normalized_title] = item
    return list(items_by_title.values())


def get_preferred_rated_item(
    user_id: int, title: str, tmdb_id: int | None = None
) -> dict | None:
    items = get_watched_items(user_id)
    normalized_title = title.strip().casefold()
    matches = (
        item
        for item in items
        if (tmdb_id is not None and item.get("tmdb_id") == tmdb_id)
        or item["title"].strip().casefold() == normalized_title
    )
    return max(
        matches,
        key=lambda item: RATING_SOURCE_PRIORITY.get(item["source"], 0),
        default=None,
    )


def invalidate_taste_profile(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM taste_profiles WHERE user_id = ?", (user_id,))


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
    interested: list[dict] = []
    for entry in latest.values():
        if entry["status"] == "seen":
            seen_titles.append(entry["title"])
        elif entry["status"] == "not_interested":
            not_interested.append({"title": entry["title"], "tags": entry["tags"]})
        elif entry["status"] == "interested":
            # 'interested' se guardaba desde siempre pero nadie lo leía: el
            # botón se pintaba como elegido y no movía el motor (preguntado por
            # Matías, 2026-08-07). Ahora es el espejo de not_interested — mismo
            # umbral, mismo peso, signo opuesto. NO excluye el título: que algo
            # te interese no es razón para dejar de mostrártelo.
            interested.append({"title": entry["title"], "tags": entry["tags"]})
    return {
        "seen_titles": seen_titles,
        "not_interested": not_interested,
        "interested": interested,
    }


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


def get_title_embeddings(keys: list[tuple[int, str]], model: str) -> dict[tuple[int, str], list[float]]:
    """Fetch cached embeddings in chunks; TMDb ids overlap between movie and TV.

    `model` es parte de la clave a propósito: los vectores de dos modelos
    distintos no viven en el mismo espacio, así que mezclarlos daría clusters
    sin sentido (y acá, con dimensiones distintas, un crash al armar la
    matriz). Cambiar de modelo simplemente deja el cache viejo sin usar.
    """
    found: dict[tuple[int, str], list[float]] = {}
    for start in range(0, len(keys), 400):
        chunk = keys[start:start + 400]
        if not chunk:
            continue
        where = " OR ".join("(tmdb_id = ? AND kind = ?)" for _ in chunk)
        params = [value for key in chunk for value in key] + [model]
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT tmdb_id, kind, vector_json FROM title_embeddings WHERE ({where}) AND model = ?",
                params,
            ).fetchall()
        found.update({(row["tmdb_id"], row["kind"]): json.loads(row["vector_json"]) for row in rows})
    return found


def save_title_embeddings(entries: list[tuple[int, str, list[float]]], model: str) -> None:
    if not entries:
        return
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO title_embeddings (tmdb_id, kind, model, vector_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tmdb_id, kind, model) DO UPDATE SET vector_json = excluded.vector_json
            """,
            [(tmdb_id, kind, model, json.dumps(vector)) for tmdb_id, kind, vector in entries],
        )


def save_vibe_clusters(labels: list[dict], assignments: list[dict]) -> None:
    """Replace one offline clustering snapshot atomically."""
    with get_connection() as conn:
        conn.execute("DELETE FROM title_clusters")
        conn.execute("DELETE FROM cluster_labels")
        if assignments:
            conn.executemany(
                """
                INSERT INTO title_clusters (tmdb_id, kind, l1_cluster_id, l2_cluster_id)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (row["tmdb_id"], row["kind"], row["l1_cluster_id"], row["l2_cluster_id"])
                    for row in assignments
                ],
            )
        if labels:
            conn.executemany(
                """
                INSERT INTO cluster_labels (level, cluster_id, label, sample_titles, size)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["level"], row["cluster_id"], row["label"],
                        json.dumps(row.get("sample_titles", [])), row["size"],
                    )
                    for row in labels
                ],
            )


def get_title_clusters_by_tmdb_ids(keys: list[tuple[int, str]]) -> dict[tuple[int, str], int]:
    """Return L2 assignments in batches, preserving movie/TV id identity."""
    found: dict[tuple[int, str], int] = {}
    for start in range(0, len(keys), 400):
        chunk = keys[start:start + 400]
        if not chunk:
            continue
        where = " OR ".join("(tmdb_id = ? AND kind = ?)" for _ in chunk)
        params = [value for key in chunk for value in key]
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT tmdb_id, kind, l2_cluster_id FROM title_clusters WHERE {where}", params
            ).fetchall()
        found.update({(row["tmdb_id"], row["kind"]): row["l2_cluster_id"] for row in rows})
    return found


def get_cluster_member_keys(cluster_id: int, limit: int) -> list[tuple[int, str]]:
    """Los (tmdb_id, kind) que cayeron en un cluster L2."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tmdb_id, kind FROM title_clusters WHERE l2_cluster_id = ? ORDER BY tmdb_id LIMIT ?",
            (cluster_id, limit),
        ).fetchall()
    return [(row["tmdb_id"], row["kind"]) for row in rows]


def get_random_cluster_keys(limit: int) -> list[tuple[int, str]]:
    """Muestra random de (tmdb_id, kind) de toda la semilla clusterizada de
    la Fase 4, sin filtrar por movimiento -- para el swipe de "marcá lo que
    viste": variada por construcción, a diferencia de un discover por
    popularidad. RANDOM() anda igual en SQLite y Postgres."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tmdb_id, kind FROM title_clusters ORDER BY RANDOM() LIMIT ?",
            (limit,),
        ).fetchall()
    return [(row["tmdb_id"], row["kind"]) for row in rows]


def get_vibe_clusters(level: int | None = None, min_size: int = 0) -> list[dict]:
    filters = []
    params: list[int] = []
    if level is not None:
        filters.append("level = ?")
        params.append(level)
    if min_size > 0:
        filters.append("size >= ?")
        params.append(min_size)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT level, cluster_id, label, sample_titles, size FROM cluster_labels"
            + (" WHERE " + " AND ".join(filters) if filters else "")
            + " ORDER BY level, cluster_id",
            tuple(params),
        ).fetchall()
    return [
        {**dict(row), "sample_titles": json.loads(row["sample_titles"] or "[]")}
        for row in rows
    ]


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
