"""SQLite persistence layer for wheels.

Each wheel is an independent session: its own name list, admin password,
and optional rigged outcome. Wheels are keyed by an unguessable code.
"""

import json
import os
import sqlite3
import threading
from pathlib import Path

_lock = threading.Lock()


def _db_path() -> Path:
    """Return the SQLite database path, honoring the DATA_DIR env var."""
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "wheels.db"


def _connect() -> sqlite3.Connection:
    """Open a connection with row access by column name."""
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create the wheels table if it does not exist."""
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wheels (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                names_json TEXT NOT NULL DEFAULT '[]',
                rig_index INTEGER,
                rig_mode TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )


def create_wheel(code: str, title: str, password_hash: str, names: list[str]) -> None:
    """Insert a new wheel."""
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO wheels (code, title, password_hash, names_json) VALUES (?, ?, ?, ?)",
            (code, title, password_hash, json.dumps(names)),
        )


def get_wheel(code: str) -> sqlite3.Row | None:
    """Fetch a wheel by its code, or None if it does not exist."""
    with _lock, _connect() as conn:
        return conn.execute("SELECT * FROM wheels WHERE code = ?", (code,)).fetchone()


def wheel_names(wheel: sqlite3.Row) -> list[str]:
    """Decode the name list stored on a wheel row."""
    return json.loads(wheel["names_json"])


def update_names(code: str, names: list[str]) -> None:
    """Replace the name list for a wheel."""
    with _lock, _connect() as conn:
        conn.execute("UPDATE wheels SET names_json = ? WHERE code = ?", (json.dumps(names), code))


def update_title(code: str, title: str) -> None:
    """Update the display title for a wheel."""
    with _lock, _connect() as conn:
        conn.execute("UPDATE wheels SET title = ? WHERE code = ?", (title, code))


def set_rig(code: str, rig_index: int, rig_mode: str) -> None:
    """Set the rigged winner index and mode ('once' or 'sticky')."""
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE wheels SET rig_index = ?, rig_mode = ? WHERE code = ?",
            (rig_index, rig_mode, code),
        )


def clear_rig(code: str) -> None:
    """Remove any rigged outcome from a wheel."""
    with _lock, _connect() as conn:
        conn.execute("UPDATE wheels SET rig_index = NULL, rig_mode = NULL WHERE code = ?", (code,))


def delete_wheel(code: str) -> None:
    """Permanently delete a wheel."""
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM wheels WHERE code = ?", (code,))
