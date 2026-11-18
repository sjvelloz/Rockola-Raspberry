"""
Configuración de la Rockola (Pi 4 / PC).

Prioridad de la playlist de ambiente:
  1. Variable de entorno ROCKOLA_AMBIENT_PLAYLIST
  2. Archivo media/ambient/playlist.url (una línea con la URL)
  3. MP3 locales en media/ambient/
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AMBIENT_DIR = ROOT / "media" / "ambient"
PLAYLIST_FILE = AMBIENT_DIR / "playlist.url"

# Pines BCM
PIN_COIN = 17          # Monedero CH-926 (PC817 → activo en bajo)
PIN_CREDIT = 27        # +1 crédito (módulo VCC/GND/OUT)
PIN_SKIP = 22          # Saltar canción actual
PIN_REBOOT = 23        # Reiniciar Pi (mantener 2.5 s)
PIN_PAUSE = 24         # Pausar / reanudar reproducción
PIN_BIRTHDAY = 25      # Abrir selector de cumpleaños en pantalla

# Módulos de botón con VCC/GND/OUT: en reposo OUT≈LOW, al pulsar OUT=HIGH.
# El monedero (PC817) sigue activo en bajo.
BUTTON_ACTIVE_HIGH = True

REBOOT_HOLD_SECONDS = 2.5
# Créditos por pulso del monedero CH-926
COIN_CREDITS = int(os.environ.get("ROCKOLA_COIN_CREDITS", "3") or "3")
# Volumen a tope: se modula desde el amplificador externo
AMBIENT_VOLUME = 100
USER_VOLUME = 100

# Canciones de cumpleaños (botón GPIO → picker en UI → delante de la cola, sin ficha)
BIRTHDAY_SONGS: list[dict[str, object]] = [
    {
        "id_youtube": "VaXPXwhOmbA",
        "titulo": "Cumpleaños feliz — opción 1",
        "miniatura": "https://i.ytimg.com/vi/VaXPXwhOmbA/hqdefault.jpg",
        "duration_seconds": 180,
    },
    {
        "id_youtube": "tznBgIGSi98",
        "titulo": "Parchís — Cumpleaños feliz",
        "miniatura": "https://i.ytimg.com/vi/tznBgIGSi98/hqdefault.jpg",
        "duration_seconds": 180,
    },
    {
        "id_youtube": "ixZO0j_LCj4",
        "titulo": "Cumpleaños feliz — opción 3",
        "miniatura": "https://i.ytimg.com/vi/ixZO0j_LCj4/hqdefault.jpg",
        "duration_seconds": 180,
    },
    {
        "id_youtube": "xvVUPGI8Kgo",
        "titulo": "Cumpleaños feliz — opción 4",
        "miniatura": "https://i.ytimg.com/vi/xvVUPGI8Kgo/hqdefault.jpg",
        "duration_seconds": 180,
    },
    {
        "id_youtube": "9uveUnMn9YE",
        "titulo": "Cumpleaños feliz — opción 5",
        "miniatura": "https://i.ytimg.com/vi/9uveUnMn9YE/hqdefault.jpg",
        "duration_seconds": 180,
    },
]


def get_ambient_playlist_url() -> str | None:
    env = (os.environ.get("ROCKOLA_AMBIENT_PLAYLIST") or "").strip()
    if env:
        return env
    if PLAYLIST_FILE.is_file():
        line = PLAYLIST_FILE.read_text(encoding="utf-8").strip().splitlines()
        if line and line[0].strip() and not line[0].strip().startswith("#"):
            return line[0].strip()
    return None
