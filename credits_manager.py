"""
Hardware GPIO: monedero + botones de servicio (Raspberry Pi 4).

Pines BCM (botón/opto a GND, pull-up interno, debounce):
  17  monedero CH-926 (PC817)
  27  +1 crédito (personal / compensación de ficha)
  22  saltar canción actual
  23  reiniciar la Pi (mantener pulsado REBOOT_HOLD_SECONDS)

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
    PIN_COIN,
    PIN_CREDIT,
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
    """Créditos + botones de servicio (skip / reboot)."""

    def __init__(
        self,
        on_credits_changed: Callable[[int], None] | None = None,
        on_skip: Callable[[], None] | None = None,
        on_reboot: Callable[[], None] | None = None,
        coin_pin: int = PIN_COIN,
        credit_pin: int = PIN_CREDIT,
        skip_pin: int = PIN_SKIP,
        reboot_pin: int = PIN_REBOOT,
        debounce_ms: int = DEBOUNCE_MS,
        reboot_hold_seconds: float = REBOOT_HOLD_SECONDS,
    ) -> None:
        self._lock = threading.Lock()
        self.creditos_disponibles: int = 0
        self.on_credits_changed = on_credits_changed
        self.on_skip = on_skip
        self.on_reboot = on_reboot or self._default_reboot

        self.coin_pin = coin_pin
        self.credit_pin = credit_pin
        self.skip_pin = skip_pin
        self.reboot_pin = reboot_pin
        self.debounce_ms = debounce_ms
        self.reboot_hold_seconds = reboot_hold_seconds

        self._last_coin_ts = 0.0
        self._last_credit_ts = 0.0
        self._last_skip_ts = 0.0
        self._started = False
        self._stop_poll = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._prev_levels: dict[int, int] = {}
        self._reboot_low_since: float | None = None

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
            for pin in (self.coin_pin, self.credit_pin, self.skip_pin, self.reboot_pin):
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                self._prev_levels[pin] = GPIO.input(pin)
        except Exception:
            logger.exception(
                "No se pudo inicializar GPIO. El servidor arranca sin botones/monedero."
            )
            self._started = True
            return

        # Bookworm: add_event_detect suele fallar → polling
        self._stop_poll.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="gpio-poll",
            daemon=True,
        )
        self._poll_thread.start()

        self._started = True
        logger.info(
            "GPIO por sondeo: coin=%d credit=%d skip=%d reboot=%d (hold=%.1fs)",
            self.coin_pin,
            self.credit_pin,
            self.skip_pin,
            self.reboot_pin,
            self.reboot_hold_seconds,
        )

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_poll.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2)
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup(
                    [self.coin_pin, self.credit_pin, self.skip_pin, self.reboot_pin]
                )
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

    def _poll_once(self) -> None:
        assert GPIO is not None
        now = time.monotonic()

        for pin, handler in (
            (self.coin_pin, self._fire_coin),
            (self.credit_pin, self._fire_credit),
            (self.skip_pin, self._fire_skip),
        ):
            level = GPIO.input(pin)
            prev = self._prev_levels.get(pin, GPIO.HIGH)
            if prev == GPIO.HIGH and level == GPIO.LOW:
                handler()
            self._prev_levels[pin] = level

        reboot_level = GPIO.input(self.reboot_pin)
        if reboot_level == GPIO.LOW:
            if self._reboot_low_since is None:
                self._reboot_low_since = now
                logger.info(
                    "Botón reboot pulsado: mantén %.1fs…",
                    self.reboot_hold_seconds,
                )
            elif now - self._reboot_low_since >= self.reboot_hold_seconds:
                self._reboot_low_since = None
                logger.warning("Reiniciando Raspberry Pi…")
                try:
                    self.on_reboot()
                except Exception:
                    logger.exception("Error en on_reboot")
        else:
            if self._reboot_low_since is not None:
                logger.info("Reboot cancelado (soltó el botón).")
            self._reboot_low_since = None
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
        logger.debug("Pulso monedero (GPIO %d)", self.coin_pin)
        self.add_credit(1)

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
