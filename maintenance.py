#!/usr/bin/env python3
"""
Mantenimiento de arranque: actualiza yt-dlp (`yt-dlp -U`).

Uso típico (systemd ExecStartPre):
  /home/pi/Rockola-Raspberry/venv/bin/python maintenance.py

No aborta el arranque del jukebox si la actualización falla
(p. ej. sin red): registra el error y sale con código 0.
"""

from __future__ import annotations

import argparse
import logging
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "maintenance.log"

DEFAULT_NETWORK_TIMEOUT = 60
DEFAULT_NETWORK_HOST = "8.8.8.8"
DEFAULT_NETWORK_PORT = 53


def _setup_logging(verbose: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def wait_for_network(
    timeout: int = DEFAULT_NETWORK_TIMEOUT,
    host: str = DEFAULT_NETWORK_HOST,
    port: int = DEFAULT_NETWORK_PORT,
) -> bool:
    """Espera conectividad básica antes de actualizar yt-dlp."""
    deadline = time.monotonic() + max(0, timeout)
    logging.info("Esperando red (timeout=%ss)…", timeout)
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                logging.info("Red disponible.")
                return True
        except OSError:
            time.sleep(2)
    logging.warning("Sin red tras %ss; se intentará la actualización igual.", timeout)
    return False


def update_ytdlp() -> int:
    """Ejecuta `python -m yt_dlp -U` con el intérprete del entorno actual."""
    cmd = [sys.executable, "-m", "yt_dlp", "-U"]
    logging.info("Actualizando yt-dlp: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        logging.error("Timeout al actualizar yt-dlp (>300s).")
        return 1
    except Exception as exc:
        logging.exception("Error lanzando yt-dlp -U: %s", exc)
        return 1

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if out:
        logging.info("yt-dlp stdout:\n%s", out)
    if err:
        logging.warning("yt-dlp stderr:\n%s", err)

    if result.returncode == 0:
        logging.info("yt-dlp actualizado correctamente.")
    else:
        logging.error("yt-dlp -U terminó con código %s", result.returncode)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Actualización automática de yt-dlp en el arranque."
    )
    parser.add_argument(
        "--skip-network-wait",
        action="store_true",
        help="No esperar a que haya red antes de actualizar.",
    )
    parser.add_argument(
        "--network-timeout",
        type=int,
        default=DEFAULT_NETWORK_TIMEOUT,
        help=f"Segundos máximos esperando red (default {DEFAULT_NETWORK_TIMEOUT}).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Devuelve el código de error de yt-dlp (por defecto siempre 0).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(verbose=args.verbose)
    logging.info("=== maintenance.py %s ===", datetime.now().isoformat(timespec="seconds"))

    if not args.skip_network_wait:
        wait_for_network(timeout=args.network_timeout)

    code = update_ytdlp()
    if args.strict:
        return code

    # Arranque resiliente: no bloquear jukebox.service si falla la update
    if code != 0:
        logging.warning(
            "Actualización fallida (código %s); el jukebox continuará con la versión instalada.",
            code,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
