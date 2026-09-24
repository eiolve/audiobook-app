"""
Хранилище прогресса прослушивания.

Используем SQLite-файл — для MVP и локального запуска этого достаточно,
не нужно поднимать отдельную БД. Пользователь идентифицируется по
произвольному user_id, который присылает фронтенд (в простом вебе — это
может быть id, сохранённый в localStorage браузера).
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", "/data/audiobook.db"))
# На случай, если постоянный диск ещё не примонтирован при первом запуске
# (или используется локальный путь без диска) — создаём родительскую папку сами.
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS progress (
                user_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                position_seconds REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, file_id)
            )
            """
        )


def save_progress(user_id: str, file_id: str, position_seconds: float) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO progress (user_id, file_id, position_seconds, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id, file_id)
            DO UPDATE SET position_seconds = excluded.position_seconds,
                          updated_at = excluded.updated_at
            """,
            (user_id, file_id, position_seconds),
        )


def get_progress(user_id: str, file_id: str) -> float:
    with _connect() as conn:
        row = conn.execute(
            "SELECT position_seconds FROM progress WHERE user_id = ? AND file_id = ?",
            (user_id, file_id),
        ).fetchone()
        return row[0] if row else 0.0


def get_all_progress(user_id: str) -> dict[str, float]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT file_id, position_seconds FROM progress WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {file_id: position for file_id, position in rows}
