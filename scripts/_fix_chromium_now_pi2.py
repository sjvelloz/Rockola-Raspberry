"""Diagnose and force-restart Chromium kiosk on Pi2."""
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

    print("=== before ===")
    print(
        run(
            c,
            "hostname; systemctl is-active jukebox; "
            "pgrep -af chromium | head -3 || echo NO_CHROMIUM; "
            "ls -la /run/user/1000/wayland* 2>&1; "
            "tail -40 /tmp/rockola-session.log 2>/dev/null || echo no_session_log",
        )
    )

    launcher = r"""#!/bin/bash
exec >>/tmp/rockola-launch-debug.log 2>&1
echo "=== $(date -Iseconds) ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
for s in wayland-0 wayland-1; do
  if [ -S "/run/user/1000/$s" ]; then export WAYLAND_DISPLAY=$s; break; fi
done
export DISPLAY=:0
echo "WAYLAND=$WAYLAND_DISPLAY DISPLAY=$DISPLAY"
pkill -f '/usr/lib/chromium/chromium' >/dev/null 2>&1 || true
pkill -f 'rockola-session.sh' >/dev/null 2>&1 || true
sleep 1
cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh
# Ensure autostart
mkdir -p /home/saskweise/.config/labwc /home/saskweise/.config/autostart
printf '%s\n' '/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh &' > /home/saskweise/.config/labwc/autostart
chmod +x /home/saskweise/.config/labwc/autostart
# Layout UI left
wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1 2>/dev/null || true
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1 2>/dev/null || true
bash scripts/rockola-session.sh
echo "session exited=$?"
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/launch-rockola.sh", "w") as f:
        f.write(launcher.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/launch-rockola.sh", 0o755)
    sftp.close()

    print("=== launch ===")
    print(
        run(
            c,
            "nohup /home/saskweise/launch-rockola.sh >/dev/null 2>&1 & echo started; "
            "sleep 8; "
            "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
            "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
            "pgrep -c chromium || true; "
            "tail -50 /tmp/rockola-session.log 2>/dev/null; "
            "tail -30 /tmp/rockola-launch-debug.log 2>/dev/null; "
            "XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 wlr-randr 2>/dev/null | grep -E 'HDMI|Position'",
            timeout=60,
        )
    )
    time.sleep(2)
    print("=== after ===")
    print(
        run(
            c,
            "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
            "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN",
        )
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
