"""
Modo karaoke on/off.

OFF (default): sin loopback del mic → música limpia.
ON: pw-loopback mic→HyperX a quantum 1024.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "karaoke-mic-loopback.sh"
STATE_FILE = Path(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp")
) / "rockola-karaoke-enabled"


class KaraokeManager:
    def __init__(
        self,
        on_changed: Callable[[bool], None] | None = None,
    ) -> None:
        self._enabled = False
        self._lock = threading.Lock()
        self.on_changed = on_changed
        # Arranque siempre OFF (música limpia)
        self._disable_unlocked(notify=False)

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "enabled": self._enabled,
                "quantum": 1024 if self._enabled else None,
            }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            if enabled == self._enabled:
                return {
                    "ok": True,
                    "enabled": self._enabled,
                    "quantum": 1024 if self._enabled else None,
                }
            if enabled:
                ok = self._enable_unlocked()
                self._enabled = bool(ok)
            else:
                self._disable_unlocked(notify=False)
                self._enabled = False
                ok = True
            enabled_now = self._enabled
        if self.on_changed:
            try:
                self.on_changed(enabled_now)
            except Exception:
                logger.exception("on_changed karaoke")
        return {
            "ok": ok,
            "enabled": enabled_now,
            "quantum": 1024 if enabled_now else None,
            "detail": None if ok else "No se pudo activar el micrófono karaoke",
        }

    def toggle(self) -> dict[str, Any]:
        return self.set_enabled(not self.enabled)

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
        env.setdefault(
            "DBUS_SESSION_BUS_ADDRESS",
            f"unix:path={env['XDG_RUNTIME_DIR']}/bus",
        )
        env["ROCKOLA_KARAOKE_QUANTUM"] = "1024"
        return env

    def _run(self, cmd: list[str], timeout: float = 20) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            env=self._env(),
            timeout=timeout,
            check=False,
            capture_output=True,
            text=True,
        )

    def _enable_unlocked(self) -> bool:
        if not SCRIPT.is_file():
            logger.error("Falta %s", SCRIPT)
            return False
        try:
            SCRIPT.chmod(SCRIPT.stat().st_mode | 0o111)
        except OSError:
            pass
        # Música con margen; mic a 1024
        self._run(
            ["pw-metadata", "-n", "settings", "0", "clock.force-quantum", "0"],
            timeout=5,
        )
        self._run(
            ["pw-metadata", "-n", "settings", "0", "clock.quantum", "2048"],
            timeout=5,
        )
        # Forzar reinicio del loopback
        self._kill_loopback()
        proc = self._run(["bash", str(SCRIPT)], timeout=25)
        out = (proc.stdout or "") + (proc.stderr or "")
        logger.info("Karaoke ON: %s", out.strip()[:300])
        try:
            STATE_FILE.write_text("1", encoding="utf-8")
        except OSError:
            pass
        return proc.returncode == 0 or "karaoke:" in out

    def _disable_unlocked(self, *, notify: bool) -> bool:
        self._kill_loopback()
        self._unlink_direct()
        # Restaurar buffer cómodo para música sola
        self._run(
            ["pw-metadata", "-n", "settings", "0", "clock.force-quantum", "0"],
            timeout=5,
        )
        self._run(
            ["pw-metadata", "-n", "settings", "0", "clock.quantum", "2048"],
            timeout=5,
        )
        # HyperX PCM ~0 dB
        self._run(["amixer", "-c", "3", "sset", "PCM", "70", "unmute"], timeout=5)
        try:
            STATE_FILE.write_text("0", encoding="utf-8")
        except OSError:
            pass
        # Borrar pid del script
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"))
        try:
            (runtime / "rockola-karaoke-loopback.pid").unlink(missing_ok=True)
        except OSError:
            pass
        logger.info("Karaoke OFF (música limpia)")
        if notify and self.on_changed:
            try:
                self.on_changed(False)
            except Exception:
                logger.exception("on_changed karaoke off")
        return True

    def _kill_loopback(self) -> None:
        self._run(["pkill", "-f", "pw-loopback.*rockola-karaoke"], timeout=5)

    def _unlink_direct(self) -> None:
        """Quita enlaces directos mic→HyperX si quedaron."""
        # Mejor esfuerzo: listar y desconectar no es trivial; pkill basta
        # para el loopback. Enlaces huérfanos se van al reiniciar pipewire.
        pass
