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

# Pines BCM (botones a GND, pull-up interno)
PIN_COIN = 17          # Monedero CH-926
PIN_CREDIT = 27        # +1 crédito (personal / compensación)
PIN_SKIP = 22          # Saltar canción actual (personal)
PIN_REBOOT = 23        # Reiniciar Pi (mantener 2.5 s)

REBOOT_HOLD_SECONDS = 2.5
# Volumen a tope: se modula desde el amplificador externo
AMBIENT_VOLUME = 100
USER_VOLUME = 100


def get_ambient_playlist_url() -> str | None:
    env = (os.environ.get("ROCKOLA_AMBIENT_PLAYLIST") or "").strip()
    if env:
        return env
    if PLAYLIST_FILE.is_file():
        line = PLAYLIST_FILE.read_text(encoding="utf-8").strip().splitlines()
        if line and line[0].strip() and not line[0].strip().startswith("#"):
            return line[0].strip()
    return None
