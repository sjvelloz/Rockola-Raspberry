"""
Hardware GPIO: monedero + botones de servicio (Raspberry Pi 4).

Pines BCM (debounce por sondeo):
  17  monedero CH-926 (PC817) — activo en bajo
  27  +1 crédito (módulo VCC/GND/OUT)
  22  saltar canción actual
  23  reiniciar la Pi (mantener pulsado REBOOT_HOLD_SECONDS)
  24  pausar / reanudar
  25  abrir selector de cumpleaños

Módulos de botón VCC/GND/OUT: por defecto activos en alto (BUTTON_ACTIVE_HIGH).
En Raspberry Pi OS Bookworm, RPi.GPIO.add_event_detect suele fallar
("Failed to add edge detection"). Usamos sondeo (polling), más fiable.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Callable

from config import (
    BUTTON_ACTIVE_HIGH,
    COIN_CREDITS,
    PIN_BIRTHDAY,
    PIN_COIN,
    PIN_CREDIT,
    PIN_PAUSE,
    PIN_REBOOT,
    PIN_SKIP,
    REBOOT_HOLD_SECONDS,
)

logger = logging.getLogger(__name__)

DEBOUNCE_MS = 50
POLL_INTERVAL_S = 0.02  # 20 ms

try:
    import RPi.GPIO as GPIO  # type: ignore

    GPIO_AVAILABLE = True
except ImportError:
    GPIO = None  # type: ignore
    GPIO_AVAILABLE = False
    logger.warning(
        "RPi.GPIO no disponible: hardware omitido "
        "(POST /api/credits/add, /api/player/skip en PC)."
    )


class CreditsManager:
    """Créditos + botones de servicio (skip / pause / birthday / reboot)."""

    def __init__(
        self,
        on_credits_changed: Callable[[int], None] | None = None,
        on_skip: Callable[[], None] | None = None,
        on_pause: Callable[[], None] | None = None,
        on_birthday: Callable[[], None] | None = None,
        on_reboot: Callable[[], None] | None = None,
        coin_pin: int = PIN_COIN,
        credit_pin: int = PIN_CREDIT,
        skip_pin: int = PIN_SKIP,
        pause_pin: int = PIN_PAUSE,
        birthday_pin: int = PIN_BIRTHDAY,
        reboot_pin: int = PIN_REBOOT,
        debounce_ms: int = DEBOUNCE_MS,
        reboot_hold_seconds: float = REBOOT_HOLD_SECONDS,
    ) -> None:
        self._lock = threading.Lock()
        self.creditos_disponibles: int = 0
        self.on_credits_changed = on_credits_changed
        self.on_skip = on_skip
        self.on_pause = on_pause
        self.on_birthday = on_birthday
        self.on_reboot = on_reboot or self._default_reboot

        self.coin_pin = coin_pin
        self.credit_pin = credit_pin
        self.skip_pin = skip_pin
        self.pause_pin = pause_pin
        self.birthday_pin = birthday_pin
        self.reboot_pin = reboot_pin
        self.debounce_ms = debounce_ms
        self.reboot_hold_seconds = reboot_hold_seconds

        self._last_coin_ts = 0.0
        self._last_credit_ts = 0.0
        self._last_skip_ts = 0.0
        self._last_pause_ts = 0.0
        self._last_birthday_ts = 0.0
        self._started = False
        self._stop_poll = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._prev_levels: dict[int, int] = {}
        self._reboot_held_since: float | None = None
        self._buttons_active_high = bool(BUTTON_ACTIVE_HIGH)

    def _button_pins(self) -> tuple[int, ...]:
        return (
            self.credit_pin,
            self.skip_pin,
            self.pause_pin,
            self.birthday_pin,
            self.reboot_pin,
        )

    def start(self) -> None:
        if self._started:
            return

        if not GPIO_AVAILABLE:
            logger.warning("GPIO omitido: hardware no presente en este entorno.")
            self._started = True
            return

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            # Monedero: pull-up (PC817 a GND). Botones módulo: pull-down si activo-alto.
            GPIO.setup(self.coin_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            button_pud = GPIO.PUD_DOWN if self._buttons_active_high else GPIO.PUD_UP
            for pin in self._button_pins():
                GPIO.setup(pin, GPIO.IN, pull_up_down=button_pud)
            for pin in (self.coin_pin, *self._button_pins()):
                self._prev_levels[pin] = GPIO.input(pin)
        except Exception:
            logger.exception(
                "No se pudo inicializar GPIO. El servidor arranca sin botones/monedero."
            )
            self._started = True
            return

        self._stop_poll.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="gpio-poll",
            daemon=True,
        )
        self._poll_thread.start()

        self._started = True
        logger.info(
            "GPIO por sondeo: coin=%d credit=%d skip=%d pause=%d birthday=%d "
            "reboot=%d (hold=%.1fs, botones_activo_alto=%s)",
            self.coin_pin,
            self.credit_pin,
            self.skip_pin,
            self.pause_pin,
            self.birthday_pin,
            self.reboot_pin,
            self.reboot_hold_seconds,
            self._buttons_active_high,
        )

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_poll.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2)
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup([self.coin_pin, *self._button_pins()])
            except Exception:
                logger.exception("Error en GPIO.cleanup")
        self._started = False
        logger.info("GPIO detenido.")

    def _poll_loop(self) -> None:
        assert GPIO is not None
        while not self._stop_poll.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("Error en sondeo GPIO")
            time.sleep(POLL_INTERVAL_S)

    def _edge_pressed(self, prev: int, level: int, *, active_high: bool) -> bool:
        if active_high:
            return prev == GPIO.LOW and level == GPIO.HIGH
        return prev == GPIO.HIGH and level == GPIO.LOW

    def _is_held(self, level: int, *, active_high: bool) -> bool:
        if active_high:
            return level == GPIO.HIGH
        return level == GPIO.LOW

    def _poll_once(self) -> None:
        assert GPIO is not None
        now = time.monotonic()

        # Monedero siempre activo en bajo (PC817 a GND).
        coin_level = GPIO.input(self.coin_pin)
        coin_prev = self._prev_levels.get(self.coin_pin, GPIO.HIGH)
        if self._edge_pressed(coin_prev, coin_level, active_high=False):
            self._fire_coin()
        self._prev_levels[self.coin_pin] = coin_level

        for pin, handler in (
            (self.credit_pin, self._fire_credit),
            (self.skip_pin, self._fire_skip),
            (self.pause_pin, self._fire_pause),
            (self.birthday_pin, self._fire_birthday),
        ):
            level = GPIO.input(pin)
            prev = self._prev_levels.get(
                pin, GPIO.LOW if self._buttons_active_high else GPIO.HIGH
            )
            if self._edge_pressed(prev, level, active_high=self._buttons_active_high):
                handler()
            self._prev_levels[pin] = level

        reboot_level = GPIO.input(self.reboot_pin)
        if self._is_held(reboot_level, active_high=self._buttons_active_high):
            if self._reboot_held_since is None:
                self._reboot_held_since = now
                logger.info(
                    "Botón reboot pulsado: mantén %.1fs…",
                    self.reboot_hold_seconds,
                )
            elif now - self._reboot_held_since >= self.reboot_hold_seconds:
                self._reboot_held_since = None
                logger.warning("Reiniciando Raspberry Pi…")
                try:
                    self.on_reboot()
                except Exception:
                    logger.exception("Error en on_reboot")
        else:
            if self._reboot_held_since is not None:
                logger.info("Reboot cancelado (soltó el botón).")
            self._reboot_held_since = None
        self._prev_levels[self.reboot_pin] = reboot_level

    def _debounce_ok(self, attr: str, min_ms: float | None = None) -> bool:
        need = self.debounce_ms if min_ms is None else min_ms
        now = time.monotonic()
        with self._lock:
            last = getattr(self, attr)
            if (now - last) * 1000.0 < need:
                return False
            setattr(self, attr, now)
            return True

    def _fire_coin(self) -> None:
        if not self._debounce_ok("_last_coin_ts"):
            return
        n = max(1, int(COIN_CREDITS))
        logger.info("Pulso monedero (GPIO %d): +%d créditos", self.coin_pin, n)
        self.add_credit(n)

    def _fire_credit(self) -> None:
        if not self._debounce_ok("_last_credit_ts", 300):
            return
        logger.info("Botón crédito (GPIO %d): +1", self.credit_pin)
        self.add_credit(1)

    def _fire_skip(self) -> None:
        if not self._debounce_ok("_last_skip_ts", 400):
            return
        logger.info("Botón skip (GPIO %d)", self.skip_pin)
        if self.on_skip:
            try:
                self.on_skip()
            except Exception:
                logger.exception("Error en on_skip")

    def _fire_pause(self) -> None:
        if not self._debounce_ok("_last_pause_ts", 350):
            return
        logger.info("Botón pause (GPIO %d)", self.pause_pin)
        if self.on_pause:
            try:
                self.on_pause()
            except Exception:
                logger.exception("Error en on_pause")

    def _fire_birthday(self) -> None:
        if not self._debounce_ok("_last_birthday_ts", 500):
            return
        logger.info("Botón cumpleaños (GPIO %d)", self.birthday_pin)
        if self.on_birthday:
            try:
                self.on_birthday()
            except Exception:
                logger.exception("Error en on_birthday")

    @staticmethod
    def _default_reboot() -> None:
        subprocess.Popen(["sudo", "-n", "reboot"], start_new_session=True)

    def add_credit(self, amount: int = 1) -> int:
        if amount < 1:
            return self.get_credits()
        with self._lock:
            self.creditos_disponibles += amount
            current = self.creditos_disponibles
        self._emit_change(current)
        return current

    def consume_credit(self) -> bool:
        with self._lock:
            if self.creditos_disponibles < 1:
                return False
            self.creditos_disponibles -= 1
            current = self.creditos_disponibles
        self._emit_change(current)
        return True

    def refund_credit(self) -> int:
        return self.add_credit(1)

    def get_credits(self) -> int:
        with self._lock:
            return self.creditos_disponibles

    def _emit_change(self, current: int) -> None:
        if not self.on_credits_changed:
            return
        try:
            self.on_credits_changed(current)
        except Exception:
            logger.exception("Error notificando créditos (%s)", current)
