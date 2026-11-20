"""Diagnose Chromium / kiosk on rockola-raspberry-2."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = os.environ.get("ROCKOLA_PI_HOST", "192.168.1.245")
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 30) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors="replace") + stderr.read().decode(
        errors="replace"
    )


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    cmds = [
        "hostname; date",
        "systemctl is-active jukebox; curl -s --max-time 3 http://127.0.0.1:8000/api/credits || echo api_fail",
        "echo '=== chromium ==='; pgrep -af chromium || echo NO_CHROMIUM",
        "echo '=== session ==='; echo WAYLAND=$WAYLAND_DISPLAY DISPLAY=$DISPLAY; loginctl list-sessions --no-legend; ps -u saskweise -o pid,cmd | head -40",
        "echo '=== autostart ==='; ls -la ~/.config/labwc/autostart ~/.config/autostart/ 2>/dev/null; echo '--- labwc ---'; cat ~/.config/labwc/autostart 2>/dev/null; echo '--- desktop ---'; cat ~/.config/autostart/*.desktop 2>/dev/null",
        "echo '=== outputs ==='; WAYLAND_DISPLAY=wayland-0 wlr-randr 2>/dev/null || true; DISPLAY=:0 xrandr --query 2>/dev/null | head -30 || true",
        "echo '=== rockola.env ==='; cat ~/Rockola-Raspberry/rockola.env 2>/dev/null || cat ~/Rockola-Raspberry/scripts/rockola.env 2>/dev/null || echo no_env",
        "echo '=== recent journal ==='; journalctl -u jukebox -n 15 --no-pager; journalctl --user -n 20 --no-pager 2>/dev/null | tail -20",
    ]
    for cmd in cmds:
        print(run(c, cmd))
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
