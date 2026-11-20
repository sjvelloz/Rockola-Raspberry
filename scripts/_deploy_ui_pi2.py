"""Deploy UI fixes to rockola-2 and reload Chromium."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
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
    print(
        run(
            c,
            "cd ~/Rockola-Raspberry && git fetch origin && "
            "git reset --hard origin/main && git log -1 --oneline",
        )
    )
    print(
        run(
            c,
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
            "sleep 2; systemctl is-active jukebox",
        )
    )
    # Reload kiosk so Chromium drops cached CSS/JS
    print(
        run(
            c,
            r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
pkill -f '/usr/lib/chromium/chromium' >/dev/null 2>&1 || true
sleep 1
nohup bash ~/Rockola-Raspberry/scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
sleep 6
pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null && echo CHROMIUM_UP || echo CHROMIUM_DOWN
""",
            timeout=60,
        )
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
