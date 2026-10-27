"""
Búsqueda e integración con YouTube mediante yt-dlp.

Filtro de seguridad: elegible=True solo si duration_seconds <= 600.
La búsqueda usa extract_flat + caché para responder en ~1–3 s.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from yt_dlp import YoutubeDL

logger = logging.getLogger(__name__)

MAX_DURATION_SECONDS = 600
DEFAULT_SEARCH_LIMIT = 8
SEARCH_CACHE_TTL_S = 300  # 5 min
SEARCH_CACHE_MAX = 64

# extract_flat=True: no descarga formatos/codecs → mucho más rápido
_YDL_SEARCH_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": True,
    "noplaylist": True,
    "ignoreerrors": True,
    "socket_timeout": 15,
    "retries": 1,
    "fragment_retries": 1,
}

_YDL_STREAM_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "socket_timeout": 20,
    # Un solo contenedor cuando sea posible (más fácil para mpv)
    "format": "best[height<=1080][ext=mp4]/best[height<=1080]/best",
}

_YDL_AUDIO_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "socket_timeout": 20,
    "format": "bestaudio/best",
}

_cache_lock = threading.Lock()
_search_cache: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "??:??"
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def _clean_title(title: str | None) -> str:
    if not title:
        return "Sin título"
    cleaned = re.sub(r"\s+", " ", title).strip()
    return cleaned or "Sin título"


def _thumbnail_url(video_id: str, entry: dict[str, Any] | None = None) -> str:
    """Miniatura rápida sin recorrer listas enormes de thumbnails."""
    if entry:
        thumb = entry.get("thumbnail")
        if isinstance(thumb, str) and thumb.startswith("http"):
            return thumb
        thumbs = entry.get("thumbnails") or []
        if thumbs:
            # La última suele ser la de más resolución; evitar sort O(n log n) pesado
            url = thumbs[-1].get("url") if isinstance(thumbs[-1], dict) else None
            if url:
                return url
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def build_result(
    id_youtube: str,
    titulo: str,
    miniatura: str,
    duration_seconds: int | None,
) -> dict[str, Any]:
    seconds = int(duration_seconds) if duration_seconds is not None else None
    return {
        "id_youtube": id_youtube,
        "titulo": _clean_title(titulo),
        "miniatura": miniatura,
        "duration_seconds": seconds,
        "duration_formatted": _format_duration(seconds),
        "elegible": seconds is not None and seconds <= MAX_DURATION_SECONDS,
    }


def _parse_duration(entry: dict[str, Any]) -> int | None:
    duration = entry.get("duration")
    if duration is None:
        # A veces viene como string "3:33" en extractores planos
        raw = entry.get("duration_string") or entry.get("timestamp")
        if isinstance(raw, str) and ":" in raw:
            parts = raw.strip().split(":")
            try:
                nums = [int(p) for p in parts]
                if len(nums) == 2:
                    return nums[0] * 60 + nums[1]
                if len(nums) == 3:
                    return nums[0] * 3600 + nums[1] * 60 + nums[2]
            except ValueError:
                return None
        return None
    try:
        return int(duration)
    except (TypeError, ValueError):
        return None


def _entry_to_result(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry:
        return None
    video_id = entry.get("id")
    if not video_id or entry.get("_type") == "playlist":
        return None
    # IDs de búsqueda a veces vienen como URL
    video_id = str(video_id)
    if "youtube.com" in video_id or "youtu.be" in video_id:
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", video_id)
        if not m:
            return None
        video_id = m.group(1)

    return build_result(
        id_youtube=video_id,
        titulo=entry.get("title") or "",
        miniatura=_thumbnail_url(video_id, entry),
        duration_seconds=_parse_duration(entry),
    )


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    now = time.monotonic()
    with _cache_lock:
        item = _search_cache.get(key)
        if not item:
            return None
        ts, results = item
        if now - ts > SEARCH_CACHE_TTL_S:
            _search_cache.pop(key, None)
            return None
        _search_cache.move_to_end(key)
        return [dict(r) for r in results]


def _cache_set(key: str, results: list[dict[str, Any]]) -> None:
    with _cache_lock:
        _search_cache[key] = (time.monotonic(), results)
        _search_cache.move_to_end(key)
        while len(_search_cache) > SEARCH_CACHE_MAX:
            _search_cache.popitem(last=False)


def search_youtube(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[dict[str, Any]]:
    """
    Busca vídeos en YouTube (rápido: flat + caché).

    Campos: id_youtube, titulo, miniatura, duration_seconds, duration_formatted, elegible
    """
    query = (query or "").strip()
    if not query:
        return []

    limit = max(1, min(int(limit), 12))
    cache_key = f"{query.lower()}|{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Búsqueda en caché: %r", query)
        return cached

    search_url = f"ytsearch{limit}:{query}"
    t0 = time.monotonic()
    try:
        with YoutubeDL(_YDL_SEARCH_OPTS) as ydl:
            info = ydl.extract_info(search_url, download=False)
    except Exception:
        logger.exception("Error buscando en YouTube: %r", query)
        return []

    results: list[dict[str, Any]] = []
    for entry in (info or {}).get("entries") or []:
        item = _entry_to_result(entry)
        if item:
            results.append(item)

    elapsed = time.monotonic() - t0
    logger.info("Búsqueda %r → %d resultados en %.2fs", query, len(results), elapsed)
    _cache_set(cache_key, results)
    return results


def list_playlist_video_ids(playlist_url: str, limit: int = 100) -> list[str]:
    """IDs de una playlist YouTube (plano)."""
    url = (playlist_url or "").strip()
    if not url:
        return []

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "socket_timeout": 20,
        "playlistend": max(1, int(limit)),
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        logger.exception("Error leyendo playlist: %s", url)
        return []

    if not info:
        return []

    ids: list[str] = []
    entries = info.get("entries")
    if entries is None and info.get("id") and info.get("_type") != "playlist":
        return [str(info["id"])]

    for entry in entries or []:
        if not entry:
            continue
        vid = entry.get("id")
        if vid and entry.get("_type") != "playlist":
            ids.append(str(vid))
    return ids


class PlaybackError(Exception):
    """No se pudo obtener un stream reproducible (bloqueo, red, etc.)."""


def extract_playback(
    video_id: str,
    *,
    audio_only: bool = False,
) -> dict[str, Any]:
    """
    Extrae stream con el yt-dlp del venv (no el de /usr/bin).

    Devuelve: {url, audio_url?, headers, title, duration}
    Si YouTube solo ofrece DASH, audio_url va aparte para --audio-file de mpv.
    """
    video_id = (video_id or "").strip()
    if not video_id:
        raise PlaybackError("id vacío")

    page = f"https://www.youtube.com/watch?v={video_id}"
    opts = dict(_YDL_AUDIO_OPTS if audio_only else _YDL_STREAM_OPTS)
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(page, download=False)
    except Exception as exc:
        msg = str(exc)
        logger.warning("yt-dlp falló para %s: %s", video_id, msg)
        raise PlaybackError(msg) from exc

    if not info:
        raise PlaybackError("sin metadatos")

    headers = dict(info.get("http_headers") or {})
    title = info.get("title") or video_id
    duration = info.get("duration")

    # Formato fusionado (requested_formats) = vídeo + audio separados
    requested = info.get("requested_formats") or []
    if len(requested) >= 2 and not audio_only:
        video_u = audio_u = None
        for fmt in requested:
            u = fmt.get("url")
            if not u or "storyboard" in u:
                continue
            vcodec = fmt.get("vcodec") or "none"
            acodec = fmt.get("acodec") or "none"
            if vcodec != "none" and not video_u:
                video_u = u
            if acodec != "none" and not audio_u:
                audio_u = u
        if video_u and audio_u:
            return {
                "url": video_u,
                "audio_url": audio_u,
                "headers": headers,
                "title": title,
                "duration": duration,
            }

    stream = info.get("url")
    if stream and "storyboard" not in stream:
        return {
            "url": stream,
            "headers": headers,
            "title": title,
            "duration": duration,
        }

    # Fallback: escoger formato de la lista
    stream = None
    for fmt in reversed(info.get("formats") or []):
        candidate = fmt.get("url")
        if not candidate or "storyboard" in candidate:
            continue
        acodec = fmt.get("acodec") or "none"
        vcodec = fmt.get("vcodec") or "none"
        if audio_only:
            if acodec != "none" and vcodec == "none":
                stream = candidate
                break
        elif vcodec != "none" and acodec != "none":
            stream = candidate
            break
        elif vcodec != "none" or acodec != "none":
            stream = stream or candidate

    if not stream:
        raise PlaybackError("sin URL de stream")

    return {
        "url": stream,
        "headers": headers,
        "title": title,
        "duration": duration,
    }


def get_stream_url(video_id: str) -> str | None:
    """Compat: solo la URL de stream."""
    try:
        return extract_playback(video_id)["url"]
    except PlaybackError:
        return None
