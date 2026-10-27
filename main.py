"""
Jukebox comercial — servidor FastAPI (Raspberry Pi 4 / kiosk).

Rutas base preparadas según REQUISITOS.md. La lógica de negocio vive en:
  credits_manager, youtube_service, player_engine, database.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from youtube_service import DEFAULT_SEARCH_LIMIT

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from credits_manager import CreditsManager
from database import get_top_canciones, init_db
from player_engine import PlayerEngine, PlayerState, QueueItem
from youtube_service import search_youtube

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=DEFAULT_SEARCH_LIMIT, ge=1, le=12)


class EnqueueRequest(BaseModel):
    id_youtube: str
    titulo: str
    miniatura: str = ""
    duration_seconds: int


class ConnectionManager:
    """Hub WebSocket para empujar créditos / cola / estado a la UI kiosk."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._connections)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


ws_manager = ConnectionManager()
_loop: asyncio.AbstractEventLoop | None = None


def _broadcast_threadsafe(payload: dict[str, Any]) -> None:
    loop = _loop
    if loop is None or not loop.is_running():
        return
    asyncio.run_coroutine_threadsafe(ws_manager.broadcast(payload), loop)


def _notify_credits_changed(creditos: int) -> None:
    _broadcast_threadsafe(
        {"type": "credits", "creditos_disponibles": creditos}
    )


def _notify_state_changed(state: PlayerState) -> None:
    _broadcast_threadsafe({"type": "state", "state": state.value})


def _notify_queue_changed(queue: list[QueueItem]) -> None:
    _broadcast_threadsafe(
        {
            "type": "queue",
            "queue": [item.to_dict() for item in queue],
        }
    )


def _notify_track_changed(track: QueueItem | None) -> None:
    _broadcast_threadsafe(
        {
            "type": "track",
            "current": track.to_dict() if track else None,
        }
    )


def _notify_player_error(message: str) -> None:
    _broadcast_threadsafe({"type": "error", "detail": message})


credits = CreditsManager(on_credits_changed=_notify_credits_changed)
player = PlayerEngine(
    credits_manager=credits,
    on_state_changed=_notify_state_changed,
    on_queue_changed=_notify_queue_changed,
    on_track_changed=_notify_track_changed,
    on_error=_notify_player_error,
)
# Botones físicos: skip (GPIO 22) y reboot hold (GPIO 23) → ver credits_manager
credits.on_skip = player.skip_current


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    init_db()
    credits.start()
    player.start()
    yield
    player.stop()
    credits.stop()
    _loop = None


app = FastAPI(title="Rockola Raspberry", lifespan=lifespan)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# UI kiosk
# ---------------------------------------------------------------------------


@app.get("/")
async def index() -> FileResponse:
    """Sirve la interfaz táctil en modo kiosk."""
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# Créditos
# ---------------------------------------------------------------------------


@app.get("/api/credits")
async def get_credits() -> dict[str, int]:
    """Devuelve el número actual de fichas disponibles."""
    return {"creditos_disponibles": credits.get_credits()}


@app.post("/api/credits/add")
async def add_test_credit(amount: int = 1) -> dict[str, int]:
    """Añade créditos de prueba / mantenimiento (equivalente al botón GPIO 27)."""
    return {"creditos_disponibles": credits.add_credit(amount)}


@app.post("/api/player/skip")
async def api_skip() -> dict[str, Any]:
    """Salta la pista actual (equivalente al botón GPIO 22)."""
    player.skip_current()
    return {"ok": True, **player.status()}


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------


@app.post("/api/search")
async def api_search(body: SearchRequest) -> dict[str, Any]:
    """Busca en YouTube vía yt-dlp (flat + caché) y filtro elegible (<= 10 min)."""
    results = await asyncio.to_thread(search_youtube, body.query, body.limit)
    return {"results": results}


# ---------------------------------------------------------------------------
# Cola y reproducción
# ---------------------------------------------------------------------------


@app.get("/api/queue")
async def get_queue() -> dict[str, Any]:
    """Lista la cola de próximas canciones y el estado del reproductor."""
    return player.status()


@app.post("/api/queue")
async def enqueue_song(body: EnqueueRequest) -> dict[str, Any]:
    """
    Encola una canción validada:
      - verifica elegibilidad (<= 600 s)
      - consume 1 crédito (Transición a Pago + fade-out ambiente)
      - el motor pasa a PLAYING con mpv
    """
    item = QueueItem(
        id_youtube=body.id_youtube,
        titulo=body.titulo,
        miniatura=body.miniatura,
        duration_seconds=body.duration_seconds,
    )
    return player.request_play(item)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


@app.get("/api/top")
async def api_top(limit: int = 10) -> dict[str, Any]:
    """Top N de 'Las Más Sonadas' (reproducciones DESC). Por defecto Top 10."""
    return {"top": get_top_canciones(limit=limit)}


# ---------------------------------------------------------------------------
# Tiempo real (créditos / cola / estado)
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Canal en tiempo real para créditos, cola y estado del reproductor."""
    await ws_manager.connect(websocket)
    status = player.status()
    await websocket.send_json(
        {
            "type": "snapshot",
            "creditos_disponibles": credits.get_credits(),
            "state": status["state"],
            "current": status["current"],
            "queue": status["queue"],
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
