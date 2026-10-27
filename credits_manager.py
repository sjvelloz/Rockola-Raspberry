"""
Hardware GPIO: monedero + botones de servicio (Raspberry Pi 4).

Pines BCM (botón/opto a GND, pull-up interno, debounce):
  17  monedero CH-926 (PC817)
  27  +1 crédito (personal / compensación de ficha)
  22  saltar canción actual
  23  reiniciar la Pi (mantener pulsado REBOOT_HOLD_SECONDS)
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
        self._reboot_watch: threading.Thread | None = None
        self._reboot_cancel = threading.Event()

    def start(self) -> None:
        if self._started:
            return

        if not GPIO_AVAILABLE:
            logger.warning("GPIO omitido: hardware no presente en este entorno.")
            self._started = True
            return

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        for pin in (self.coin_pin, self.credit_pin, self.skip_pin, self.reboot_pin):
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(
            self.coin_pin, GPIO.FALLING, callback=self._on_coin, bouncetime=self.debounce_ms
        )
        GPIO.add_event_detect(
            self.credit_pin,
            GPIO.FALLING,
            callback=self._on_credit,
            bouncetime=self.debounce_ms,
        )
        GPIO.add_event_detect(
            self.skip_pin, GPIO.FALLING, callback=self._on_skip, bouncetime=max(self.debounce_ms, 200)
        )
        GPIO.add_event_detect(
            self.reboot_pin,
            GPIO.FALLING,
            callback=self._on_reboot_press,
            bouncetime=self.debounce_ms,
        )

        self._started = True
        logger.info(
            "GPIO activo: coin=%d credit=%d skip=%d reboot=%d (hold=%.1fs)",
            self.coin_pin,
            self.credit_pin,
            self.skip_pin,
            self.reboot_pin,
            self.reboot_hold_seconds,
        )

    def stop(self) -> None:
        if not self._started:
            return
        self._reboot_cancel.set()
        if GPIO_AVAILABLE:
            pins = [self.coin_pin, self.credit_pin, self.skip_pin, self.reboot_pin]
            for pin in pins:
                try:
                    GPIO.remove_event_detect(pin)
                except RuntimeError:
                    pass
            GPIO.cleanup(pins)
        self._started = False
        logger.info("GPIO detenido.")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _debounce_ok(self, attr: str, min_ms: float | None = None) -> bool:
        need = self.debounce_ms if min_ms is None else min_ms
        now = time.monotonic()
        with self._lock:
            last = getattr(self, attr)
            if (now - last) * 1000.0 < need:
                return False
            setattr(self, attr, now)
            return True

    def _on_coin(self, channel: int) -> None:
        if channel != self.coin_pin or not self._debounce_ok("_last_coin_ts"):
            return
        self.add_credit(1)

    def _on_credit(self, channel: int) -> None:
        if channel != self.credit_pin or not self._debounce_ok("_last_credit_ts", 300):
            return
        logger.info("Botón crédito (GPIO %d): +1", channel)
        self.add_credit(1)

    def _on_skip(self, channel: int) -> None:
        if channel != self.skip_pin or not self._debounce_ok("_last_skip_ts", 400):
            return
        logger.info("Botón skip (GPIO %d)", channel)
        if self.on_skip:
            try:
                self.on_skip()
            except Exception:
                logger.exception("Error en on_skip")

    def _on_reboot_press(self, channel: int) -> None:
        if channel != self.reboot_pin:
            return
        if self._reboot_watch and self._reboot_watch.is_alive():
            return
        self._reboot_cancel.clear()
        self._reboot_watch = threading.Thread(
            target=self._watch_reboot_hold,
            name="reboot-hold",
            daemon=True,
        )
        self._reboot_watch.start()

    def _watch_reboot_hold(self) -> None:
        """Reinicio solo si se mantiene pulsado el tiempo configurado."""
        if not GPIO_AVAILABLE:
            return
        logger.info(
            "Botón reboot: mantén %.1fs para reiniciar…",
            self.reboot_hold_seconds,
        )
        deadline = time.monotonic() + self.reboot_hold_seconds
        while time.monotonic() < deadline:
            if self._reboot_cancel.is_set():
                return
            if GPIO.input(self.reboot_pin) != GPIO.LOW:
                logger.info("Reboot cancelado (soltó el botón).")
                return
            time.sleep(0.05)

        if GPIO.input(self.reboot_pin) == GPIO.LOW:
            logger.warning("Reiniciando Raspberry Pi…")
            try:
                self.on_reboot()
            except Exception:
                logger.exception("Error en on_reboot")

    @staticmethod
    def _default_reboot() -> None:
        subprocess.Popen(["sudo", "-n", "reboot"], start_new_session=True)

    # ------------------------------------------------------------------
    # Créditos
    # ------------------------------------------------------------------

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
