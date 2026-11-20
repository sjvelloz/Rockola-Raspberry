"""Relaunch Chromium on Pi2; capture failures."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return out + (("\n[stderr]\n" + err) if err.strip() else "")


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    print(run(c, "ls -la /tmp/rockola-session.log 2>&1; wc -l /tmp/rockola-session.log 2>&1; tail -80 /tmp/rockola-session.log 2>&1"))

    # Get graphical session env from labwc process
    print("--- env from labwc ---")
    print(
        run(
            c,
            "pid=$(pgrep -n labwc); echo labwc_pid=$pid; "
            "tr '\\0' '\\n' < /proc/$pid/environ | grep -E '^(WAYLAND|DISPLAY|XDG_RUNTIME|DBUS_SESSION)' || true",
        )
    )

    launch = r"""
pkill -f '/usr/lib/chromium/chromium' >/dev/null 2>&1 || true
sleep 1
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
cd /home/saskweise/Rockola-Raspberry
rm -f /tmp/rockola-session.log
nohup /home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh >/tmp/rockola-session-outer.log 2>&1 &
echo outer_pid=$!
sleep 8
echo '--- pgrep ---'
pgrep -af chromium || echo NO_CHROMIUM
echo '--- session log ---'
tail -100 /tmp/rockola-session.log 2>&1 || true
echo '--- outer log ---'
cat /tmp/rockola-session-outer.log 2>&1 || true
echo '--- start-kiosk exists ---'
ls -la scripts/start-kiosk.sh scripts/rockola-session.sh
"""
    print("--- launch ---")
    print(run(c, launch, timeout=120))
    time.sleep(3)
    print("--- final ---")
    print(run(c, "pgrep -af chromium || echo NO_CHROMIUM; WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 wlr-randr | head -25"))
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
