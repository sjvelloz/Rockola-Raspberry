"""
Base de datos SQLite (jukebox.db) y ranking "Las Más Sonadas".

Tabla canciones según REQUISITOS.md:
  id_youtube TEXT PRIMARY KEY,
  titulo TEXT,
  miniatura TEXT,
  reproducciones INTEGER DEFAULT 1,
  ultima_reproduccion TIMESTAMP
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent / "jukebox.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS canciones (
    id_youtube TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    miniatura TEXT,
    reproducciones INTEGER NOT NULL DEFAULT 1,
    ultima_reproduccion TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_canciones_reproducciones
    ON canciones (reproducciones DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def get_connection(db_path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Abre una conexión SQLite con filas tipo dict y commit/rollback automático."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str = DB_PATH) -> None:
    """Crea jukebox.db y la tabla canciones si no existen."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


def registrar_reproduccion(
    id_youtube: str,
    titulo: str,
    miniatura: str = "",
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """
    Registra una reproducción.

    Si el id_youtube es nuevo → INSERT con reproducciones = 1.
    Si ya existe → ON CONFLICT incrementa reproducciones en +1 y actualiza
    titulo, miniatura y ultima_reproduccion.
    """
    video_id = (id_youtube or "").strip()
    if not video_id:
        raise ValueError("id_youtube es obligatorio")

    titulo = (titulo or "Sin título").strip() or "Sin título"
    miniatura = miniatura or ""
    now = _now_iso()

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO canciones (
                id_youtube, titulo, miniatura, reproducciones, ultima_reproduccion
            )
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(id_youtube) DO UPDATE SET
                reproducciones = canciones.reproducciones + 1,
                titulo = excluded.titulo,
                miniatura = excluded.miniatura,
                ultima_reproduccion = excluded.ultima_reproduccion
            """,
            (video_id, titulo, miniatura, now),
        )
        row = conn.execute(
            """
            SELECT id_youtube, titulo, miniatura, reproducciones, ultima_reproduccion
            FROM canciones
            WHERE id_youtube = ?
            """,
            (video_id,),
        ).fetchone()

    return dict(row) if row else {}


def get_top_canciones(
    limit: int = 10,
    db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """
    Top N de canciones más escuchadas (por defecto Top 10),
    ordenado por reproducciones DESC.
    """
    limit = max(1, int(limit))
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id_youtube, titulo, miniatura, reproducciones, ultima_reproduccion
            FROM canciones
            ORDER BY reproducciones DESC, ultima_reproduccion DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_top_10(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Atajo del ranking 'Las Más Sonadas' (Top 10)."""
    return get_top_canciones(limit=10, db_path=db_path)
