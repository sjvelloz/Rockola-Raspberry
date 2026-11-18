"""Pull origin/main on both Pis and restart jukebox (+ relaunch Chromium if down)."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
USER = "saskweise"
HOSTS = ["192.168.1.244", "192.168.1.245"]


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return out + (("\n[stderr]\n" + err) if err.strip() else "")


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    for host in HOSTS:
        print(f"=== {host} ===")
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(host, username=USER, password=PASSWORD, timeout=15)
        except Exception as exc:
            print(f"connect failed: {exc}")
            continue
        print(
            run(
                c,
                "cd ~/Rockola-Raspberry && git fetch origin && "
                "git reset --hard origin/main && git log -1 --oneline && "
                "chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh "
                "scripts/configure-displays.sh",
            )
        )
        print(
            run(
                c,
                f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
                "sleep 3; systemctl is-active jukebox; "
                "journalctl -u jukebox -n 15 --no-pager | tail -15",
            )
        )
        # Ensure Chromium if graphical session exists
        print(
            run(
                c,
                "if [ -S /run/user/1000/wayland-0 ]; then "
                "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null || "
                "(export XDG_RUNTIME_DIR=/run/user/1000 "
                "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
                "WAYLAND_DISPLAY=wayland-0 DISPLAY=:0; "
                "nohup bash ~/Rockola-Raspberry/scripts/rockola-session.sh "
                ">/tmp/rockola-session.log 2>&1 &); "
                "sleep 5; "
                "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
                "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
                "else echo NO_GRAPHICAL_SESSION; fi",
                timeout=60,
            )
        )
        c.close()
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
