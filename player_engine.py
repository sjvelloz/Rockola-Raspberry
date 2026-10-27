"""
Motor de reproducción y gestor de cola (mpv + yt-dlp).

Estados (REQUISITOS.md):
  IDLE       -> música de ambiente (cola vacía)
  TRANSITION -> fade-out ambiente + restar 1 crédito (pago)
  PLAYING    -> YouTube vía mpv (--fullscreen/--force-window, --no-osd, --length=600)
                y registro de estadísticas en SQLite

En Windows (pruebas en PC) abre ventana con vídeo; en Linux/Pi usa fullscreen.
"""

from __future__ import annotations

import enum
import logging
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import random

from config import AMBIENT_DIR, AMBIENT_VOLUME, get_ambient_playlist_url
from database import registrar_reproduccion
from youtube_service import MAX_DURATION_SECONDS, get_stream_url, list_playlist_video_ids

if TYPE_CHECKING:
    from credits_manager import CreditsManager

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_AMBIENT_DIR = AMBIENT_DIR

USER_VOLUME = 100
FADE_STEPS = 8
FADE_STEP_MS = 80


class PlayerState(enum.Enum):
    IDLE = "idle"
    TRANSITION = "transition"
    PLAYING = "playing"


@dataclass
class QueueItem:
    id_youtube: str
    titulo: str
    miniatura: str
    duration_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _find_mpv() -> str | None:
    """Localiza el binario mpv (rutas de instalación primero, luego PATH)."""
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local_app = Path(os.environ.get("LOCALAPPDATA", ""))

    # Preferir .exe del instalador winget (shinchiro → "MPV Player")
    candidates = [
        program_files / "MPV Player" / "mpv.exe",
        program_files_x86 / "MPV Player" / "mpv.exe",
        local_app / "Microsoft" / "WinGet" / "Links" / "mpv.exe",
        local_app / "mpv" / "mpv.exe",
        program_files / "mpv" / "mpv.exe",
        program_files_x86 / "mpv" / "mpv.exe",
        Path(r"C:\mpv\mpv.exe"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)

    found = shutil.which("mpv")
    if found:
        # En Windows which puede devolver mpv.com; preferir .exe hermano
        found_path = Path(found)
        exe_sibling = found_path.with_suffix(".exe")
        if exe_sibling.is_file():
            return str(exe_sibling)
        return found
    return None


def _find_ytdlp() -> str | None:
    """yt-dlp del venv actual (mpv lo usa para abrir URLs de YouTube)."""
    scripts = Path(sys.executable).resolve().parent
    for name in ("yt-dlp.exe", "yt-dlp", "yt_dlp.exe"):
        candidate = scripts / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("yt-dlp")


def _guess_hdmi_screen_index() -> str:
    """
    Elige el índice de pantalla HDMI para mpv (tele).
    Si hay 2+ monitores, suele ser el último; si no, 0.
    """
    try:
        # wlr-randr: nombres en la 1ª columna de líneas no indentadas
        proc = subprocess.run(
            ["wlr-randr"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            names = [
                ln.split()[0]
                for ln in proc.stdout.splitlines()
                if ln.strip() and not ln.startswith(" ") and not ln.startswith("\t")
            ]
            for idx, name in enumerate(names):
                up = name.upper()
                if "HDMI" in up or up.startswith("DP-"):
                    logger.info("Pantalla HDMI detectada: %s (índice %s)", name, idx)
                    return str(idx)
            if len(names) >= 2:
                return str(len(names) - 1)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "1"  # valor habitual con DSI=0 + HDMI=1


class PlayerEngine:
    """Gestiona cola, estados IDLE / TRANSITION / PLAYING e integración con mpv."""

    def __init__(
        self,
        credits_manager: CreditsManager | None = None,
        ambient_dir: Path | str = DEFAULT_AMBIENT_DIR,
        on_state_changed: Callable[[PlayerState], None] | None = None,
        on_queue_changed: Callable[[list[QueueItem]], None] | None = None,
        on_track_changed: Callable[[QueueItem | None], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.credits = credits_manager
        self.ambient_dir = Path(ambient_dir)
        self.cola_canciones: queue.Queue[QueueItem] = queue.Queue()
        self.state = PlayerState.IDLE
        self.current_track: QueueItem | None = None
        self.last_error: str | None = None

        self.on_state_changed = on_state_changed
        self.on_queue_changed = on_queue_changed
        self.on_track_changed = on_track_changed
        self.on_error = on_error

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake = threading.Event()
        self._mpv_proc: subprocess.Popen[bytes] | None = None
        self._mpv_role: str | None = None  # "ambient" | "user"
        self._mpv_lock = threading.Lock()
        self._ambient_index = 0
        self._ambient_playlist_ids: list[str] = []
        self._ambient_playlist_loaded = False
        self._mpv_bin = _find_mpv()
        self._ytdlp_bin = _find_ytdlp()
        # PC (Windows): ventana. Raspberry Pi / Linux: fullscreen en la tele/HDMI.
        env_windowed = os.environ.get("ROCKOLA_WINDOWED", "").strip() in {"1", "true", "yes"}
        env_fs = os.environ.get("ROCKOLA_FULLSCREEN", "").strip() in {"1", "true", "yes"}
        self._windowed = env_windowed or (platform.system() == "Windows" and not env_fs)
        # Pantalla de vídeo (tele / HDMI). Ver scripts/configure-displays.sh
        self._fs_screen = os.environ.get("ROCKOLA_MPV_FS_SCREEN", "").strip()
        self._drm_connector = os.environ.get("ROCKOLA_MPV_DRM_CONNECTOR", "").strip()
        self._log_dir = ROOT_DIR / "logs"
        if not self._fs_screen and not self._windowed:
            self._fs_screen = self._guess_hdmi_screen_index()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._mpv_bin = _find_mpv()
        self._ytdlp_bin = _find_ytdlp()
        if not self._mpv_bin:
            logger.error(
                "mpv NO encontrado. Sin mpv no hay vídeo/audio. "
                "Instala con: winget install shinchiro.mpv "
                "y reinicia el servidor."
            )
        else:
            logger.info(
                "mpv: %s (windowed=%s fs_screen=%r drm=%r)",
                self._mpv_bin,
                self._windowed,
                self._fs_screen or None,
                self._drm_connector or None,
            )
        if self._ytdlp_bin:
            logger.info("yt-dlp para mpv: %s", self._ytdlp_bin)

        self.ambient_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="player-engine",
            daemon=True,
        )
        self._thread.start()
        logger.info("PlayerEngine arrancado (ambient=%s)", self.ambient_dir)

    def stop(self) -> None:
        self._stop_event.set()
        self._wake.set()
        self._kill_mpv()
        if self._thread:
            self._thread.join(timeout=8)
            self._thread = None
        self.current_track = None
        logger.info("PlayerEngine detenido.")

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def request_play(self, item: QueueItem) -> dict[str, Any]:
        if item.duration_seconds is None or item.duration_seconds > MAX_DURATION_SECONDS:
            return {
                "ok": False,
                "error": "not_eligible",
                "detail": "La canción supera los 10 minutos.",
            }

        if self.credits is None:
            return {
                "ok": False,
                "error": "no_credits_manager",
                "detail": "Gestor de créditos no configurado.",
            }

        if not self._mpv_bin:
            return {
                "ok": False,
                "error": "no_mpv",
                "detail": "Instala mpv para reproducir vídeo (winget install shinchiro.mpv) y reinicia el servidor.",
                "creditos_disponibles": self.credits.get_credits(),
            }

        self._set_state(PlayerState.TRANSITION)
        self._fade_out_ambient()

        if not self.credits.consume_credit():
            if self.cola_canciones.empty():
                self._set_state(PlayerState.IDLE)
            else:
                self._set_state(PlayerState.PLAYING)
            return {
                "ok": False,
                "error": "no_credits",
                "detail": "No hay fichas disponibles.",
                "creditos_disponibles": self.credits.get_credits(),
            }

        snapshot = self.enqueue(item)
        return {
            "ok": True,
            "creditos_disponibles": self.credits.get_credits(),
            "state": self.state.value,
            "queue": [q.to_dict() for q in snapshot],
        }

    def enqueue(self, item: QueueItem) -> list[QueueItem]:
        self.cola_canciones.put(item)
        snapshot = self.get_queue_snapshot()
        self._emit_queue(snapshot)
        self._wake.set()
        return snapshot

    def get_queue_snapshot(self) -> list[QueueItem]:
        with self.cola_canciones.mutex:
            return list(self.cola_canciones.queue)

    def skip_current(self) -> bool:
        """
        Salta la reproducción actual (canción de usuario o ambiente).
        Si hay cola de usuario, pasa a la siguiente; si no, vuelve a IDLE/ambiente.
        """
        logger.info("Skip solicitado (estado=%s role=%s)", self.state.value, self._mpv_role)
        self._wake.set()
        self._kill_mpv()
        return True

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "current": self.current_track.to_dict() if self.current_track else None,
            "queue": [q.to_dict() for q in self.get_queue_snapshot()],
            "mpv_available": bool(self._mpv_bin),
            "windowed": self._windowed,
            "last_error": self.last_error,
        }

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if self.cola_canciones.empty():
                self._set_current(None)
                self._set_state(PlayerState.IDLE)
                self._play_ambient()
            else:
                item = self.cola_canciones.get()
                self._emit_queue(self.get_queue_snapshot())
                self._set_state(PlayerState.PLAYING)
                self._set_current(item)
                self._play_user_track(item)

    def _play_ambient(self) -> None:
        """
        Música de ambiente mientras la cola de usuarios esté vacía.
        Prioridad: playlist YouTube (aleatoria) → MP3 locales → espera.
        Al terminar lo que puso la gente, el bucle vuelve aquí solo.
        """
        while not self._stop_event.is_set() and self.cola_canciones.empty():
            media = self._next_ambient_media()
            if not media:
                self._wait_while_idle()
                return

            logger.info("IDLE ambiente: %s", media)
            self._set_current(None)
            self._run_mpv(
                [media],
                volume=AMBIENT_VOLUME,
                user_track=False,
                interruptible=True,
            )
            if not self.cola_canciones.empty() or self._stop_event.is_set():
                break

    def _ensure_ambient_playlist(self) -> None:
        if self._ambient_playlist_loaded:
            return
        self._ambient_playlist_loaded = True
        url = get_ambient_playlist_url()
        if not url:
            logger.info(
                "Sin playlist de ambiente: usa media/ambient/playlist.url "
                "o ROCKOLA_AMBIENT_PLAYLIST"
            )
            return
        logger.info("Cargando playlist de ambiente: %s", url)
        self._ambient_playlist_ids = list_playlist_video_ids(url)
        logger.info("Playlist ambiente: %d temas", len(self._ambient_playlist_ids))

    def _next_ambient_media(self) -> str | None:
        """Devuelve URL de YouTube aleatoria o ruta a un MP3 local."""
        self._ensure_ambient_playlist()
        if self._ambient_playlist_ids:
            vid = random.choice(self._ambient_playlist_ids)
            return f"https://www.youtube.com/watch?v={vid}"

        tracks = self._list_ambient_tracks()
        if not tracks:
            return None
        path = tracks[self._ambient_index % len(tracks)]
        self._ambient_index += 1
        return str(path)

    def _wait_while_idle(self) -> None:
        while not self._stop_event.is_set() and self.cola_canciones.empty():
            if self._wake.wait(timeout=1.0):
                self._wake.clear()
                if not self.cola_canciones.empty():
                    break

    def _play_user_track(self, item: QueueItem) -> None:
        """Reproduce el vídeo con mpv (YouTube vía yt-dlp). Reembolsa si falla."""
        logger.info("PLAYING: %s (%s)", item.titulo, item.id_youtube)
        self.last_error = None

        if not self._mpv_bin:
            self._fail_play("mpv no instalado — no se puede reproducir.", refund=True)
            return

        youtube_url = f"https://www.youtube.com/watch?v={item.id_youtube}"

        try:
            registrar_reproduccion(
                id_youtube=item.id_youtube,
                titulo=item.titulo,
                miniatura=item.miniatura,
            )
        except Exception:
            logger.exception("Error registrando reproducción de %s", item.id_youtube)

        # 1) Preferir URL de YouTube: mpv + yt-dlp (vídeo + audio estables)
        ok = self._run_mpv(
            [youtube_url],
            volume=USER_VOLUME,
            user_track=True,
            interruptible=False,
        )

        # 2) Fallback: stream URL directa de yt-dlp
        if not ok and not self._stop_event.is_set():
            logger.warning("mpv/ytdl falló; intentando stream directo…")
            stream_url = get_stream_url(item.id_youtube)
            if stream_url:
                ok = self._run_mpv(
                    [stream_url],
                    volume=USER_VOLUME,
                    user_track=True,
                    interruptible=False,
                )

        if not ok and not self._stop_event.is_set():
            self._fail_play(
                "No se pudo reproducir el vídeo. Revisa mpv/yt-dlp y la red.",
                refund=True,
            )

    def _fail_play(self, message: str, *, refund: bool) -> None:
        logger.error(message)
        self.last_error = message
        if self.on_error:
            try:
                self.on_error(message)
            except Exception:
                logger.exception("Error en on_error")
        if refund and self.credits:
            self.credits.refund_credit()

    # ------------------------------------------------------------------
    # mpv
    # ------------------------------------------------------------------

    def _mpv_cmd(self, media: list[str], *, volume: int, user_track: bool) -> list[str]:
        assert self._mpv_bin
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._log_dir / ("mpv-user.log" if user_track else "mpv-ambient.log")

        cmd = [
            self._mpv_bin,
            "--no-terminal",
            f"--volume={volume}",
            # shinchiro/mpv reciente: --no-osd ya no existe
            "--osd-level=0",
            f"--log-file={log_file}",
        ]

        is_youtube = any("youtube.com" in m or "youtu.be" in m for m in media)
        if is_youtube:
            cmd.append("--ytdl=yes")
            if self._ytdlp_bin:
                ytdlp = self._ytdlp_bin.replace("\\", "/")
                cmd.append(f"--script-opts=ytdl_hook-ytdl_path={ytdlp}")

        if user_track:
            cmd.append("--length=600")
            # Kiosk: solo reproducir (sin seek, menús, teclado ni ratón)
            cmd.extend(
                [
                    "--osc=no",
                    "--input-default-bindings=no",
                    "--input-vo-keyboard=no",
                    "--input-cursor=no",
                    "--input-media-keys=no",
                    "--window-dragging=no",
                    "--cursor-autohide=always",
                ]
            )
            if self._windowed:
                cmd.extend(
                    [
                        "--force-window=yes",
                        "--geometry=960x540+40+40",
                        "--ontop",
                    ]
                )
            else:
                cmd.append("--fullscreen")
                cmd.append("--hwdec=auto-safe")
                # Forzar salida a la tele (índice de pantalla / conector DRM)
                if self._fs_screen != "":
                    cmd.append(f"--fs-screen={self._fs_screen}")
                    cmd.append(f"--screen={self._fs_screen}")
                if self._drm_connector:
                    cmd.append(f"--drm-connector={self._drm_connector}")
                logger.info(
                    "mpv vídeo → fs-screen=%r drm=%r",
                    self._fs_screen or None,
                    self._drm_connector or None,
                )
        else:
            # Ambiente: solo audio (no tapa la UI / tele de cola)
            cmd.append("--no-video")

        cmd.extend(media)
        return cmd

    def _run_mpv(
        self,
        media: list[str],
        *,
        volume: int,
        user_track: bool,
        interruptible: bool,
    ) -> bool:
        if not self._mpv_bin:
            return False

        role = "user" if user_track else "ambient"
        cmd = self._mpv_cmd(media, volume=volume, user_track=user_track)
        logger.info("Lanzando mpv (%s): %s", role, " ".join(cmd))

        env = os.environ.copy()
        scripts_dir = str(Path(sys.executable).resolve().parent)
        env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")

        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "env": env,
            "cwd": str(ROOT_DIR),
        }
        # En Windows, no ocultar la ventana de vídeo
        if platform.system() == "Windows":
            # 0 = heredar consola; evitar CREATE_NO_WINDOW
            popen_kwargs["creationflags"] = 0

        try:
            with self._mpv_lock:
                # Si había ambiente y vamos a usuario, cortar solo ambiente
                if user_track and self._mpv_role == "ambient" and self._mpv_proc:
                    self._terminate_proc(self._mpv_proc)
                    self._mpv_proc = None
                    self._mpv_role = None

                self._mpv_proc = subprocess.Popen(cmd, **popen_kwargs)
                self._mpv_role = role
                proc = self._mpv_proc
        except OSError:
            logger.exception("No se pudo lanzar mpv")
            return False

        assert proc is not None
        started = time.monotonic()
        try:
            while proc.poll() is None:
                if self._stop_event.is_set():
                    self._kill_mpv(role=role)
                    break
                if interruptible and (
                    not self.cola_canciones.empty() or self._wake.is_set()
                ):
                    self._wake.clear()
                    self._fade_out_ambient()
                    break
                time.sleep(0.2)

            elapsed = time.monotonic() - started
            code = proc.returncode
            # yt-dlp tarda ~3-5 s: solo es fallo si muere muy pronto
            if user_track and code not in (0, None) and elapsed < 8.0:
                self._log_mpv_tail()
                logger.error("mpv salió en %.1fs con código %s", elapsed, code)
                return False
            logger.info("mpv (%s) terminó code=%s elapsed=%.1fs", role, code, elapsed)
            return True
        finally:
            with self._mpv_lock:
                if self._mpv_proc is proc:
                    self._mpv_proc = None
                    self._mpv_role = None

    def _fade_out_ambient(self) -> None:
        """Corta solo la música de ambiente; nunca el vídeo de usuario."""
        with self._mpv_lock:
            if self._mpv_role != "ambient":
                return
            proc = self._mpv_proc
            self._mpv_proc = None
            self._mpv_role = None
        if proc is None:
            return
        time.sleep((FADE_STEPS * FADE_STEP_MS) / 1000.0)
        self._terminate_proc(proc)

    def _kill_mpv(self, role: str | None = None) -> None:
        with self._mpv_lock:
            if role is not None and self._mpv_role not in (None, role):
                return
            proc = self._mpv_proc
            self._mpv_proc = None
            self._mpv_role = None
        self._terminate_proc(proc)

    @staticmethod
    def _terminate_proc(proc: subprocess.Popen[bytes] | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        except OSError:
            logger.exception("Error deteniendo mpv")

    def _log_mpv_tail(self) -> None:
        log_file = self._log_dir / "mpv-user.log"
        if not log_file.is_file():
            return
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            interesting = [
                ln
                for ln in lines[-40:]
                if any(
                    k in ln.lower()
                    for k in ("error", "fatal", "failed", "exiting", "ytdl")
                )
            ]
            for ln in interesting[-15:]:
                logger.error("mpv-log: %s", ln[:240])
        except OSError:
            pass

    def _list_ambient_tracks(self) -> list[Path]:
        if not self.ambient_dir.is_dir():
            return []
        patterns = ("*.mp3", "*.flac", "*.ogg", "*.m4a", "*.wav")
        files: list[Path] = []
        for pattern in patterns:
            files.extend(sorted(self.ambient_dir.glob(pattern)))
        return files

    # ------------------------------------------------------------------
    # Notificaciones
    # ------------------------------------------------------------------

    def _set_state(self, state: PlayerState) -> None:
        if self.state == state:
            return
        self.state = state
        logger.debug("Estado → %s", state.value)
        if self.on_state_changed:
            try:
                self.on_state_changed(state)
            except Exception:
                logger.exception("Error en on_state_changed")

    def _set_current(self, item: QueueItem | None) -> None:
        self.current_track = item
        if self.on_track_changed:
            try:
                self.on_track_changed(item)
            except Exception:
                logger.exception("Error en on_track_changed")

    def _emit_queue(self, snapshot: list[QueueItem]) -> None:
        if self.on_queue_changed:
            try:
                self.on_queue_changed(snapshot)
            except Exception:
                logger.exception("Error en on_queue_changed")
