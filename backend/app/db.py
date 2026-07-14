import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "pelipick.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
"""


def _db_path() -> str:
    return os.environ.get("PELIPICK_DB_PATH", str(DEFAULT_DB_PATH))


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in columns)


def _run_migrations(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "recommendations_served", "session_id"):
        conn.execute(
            "ALTER TABLE recommendations_served ADD COLUMN session_id INTEGER REFERENCES recommendation_sessions(id)"
        )
    if not _has_column(conn, "recommendations_served", "tmdb_id"):
        conn.execute("ALTER TABLE recommendations_served ADD COLUMN tmdb_id INTEGER")


@contextmanager
def get_connection():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _run_migrations(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_user(username: str, password_hash: str, password_salt: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, password_salt) VALUES (?, ?, ?)",
            (username, password_hash, password_salt),
        )
        return cursor.lastrowid


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def create_session(token: str, user_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id)
        )


def get_user_by_token(token: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


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


def save_rated_items(user_id: int, items: list[tuple[str, float, str]]) -> None:
    if not items:
        return
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO rated_items (user_id, title, rating, review) VALUES (?, ?, ?, ?)",
            [(user_id, title, rating, review) for title, rating, review in items],
        )


def get_watched_items(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT title, rating, review, created_at
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


def create_recommendation_session(user_id: int, mood: str, taste_summary: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recommendation_sessions (user_id, mood, taste_summary)
            VALUES (?, ?, ?)
            """,
            (user_id, mood, taste_summary),
        )
        return cursor.lastrowid


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
                """,
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
            ids.append(cursor.lastrowid)
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
