"""Full update rockola-1: git, service unit, jukebox, chromium if needed."""
from __future__ import annotations

import os
import sys
import urllib.request

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.244"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
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
    try:
        c.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    except Exception as exc:
        print(f"connect failed: {exc}", file=sys.stderr)
        return 1

    print(
        run(
            c,
            "hostname; hostname -I; "
            "cd ~/Rockola-Raspberry && git fetch origin && "
            "git reset --hard origin/main && git log -1 --oneline && "
            "chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh "
            "scripts/configure-displays.sh",
        )
    )

    print(
        run(
            c,
            "mkdir -p ~/.config/labwc ~/.config/autostart; "
            "printf '%s\\n' '/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh &' "
            "> ~/.config/labwc/autostart; chmod +x ~/.config/labwc/autostart; "
            "grep -n BUTTON_ACTIVE_HIGH ~/Rockola-Raspberry/config.py; "
            "grep -n '0.0.0.0' ~/Rockola-Raspberry/jukebox.service; "
            "test -f ~/Rockola-Raspberry/main.py && "
            "grep -n system/reboot ~/Rockola-Raspberry/main.py",
        )
    )

    print(
        run(
            c,
            f"printf '%s\\n' {PASSWORD!r} | sudo -S cp "
            "~/Rockola-Raspberry/jukebox.service /etc/systemd/system/jukebox.service; "
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl daemon-reload; "
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
            "sleep 3; systemctl is-active jukebox; "
            "ss -lntp | grep 8000 || true",
        )
    )

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

    for path, method, data in (
        ("/api/credits", "GET", None),
        ("/api/player/pause", "POST", b"{}"),
        ("/api/birthday/open", "POST", b"{}"),
    ):
        url = f"http://{HOST}:8000{path}"
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"} if data else {},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"LAN {method} {path} → {resp.status} {resp.read().decode()[:100]}")
        except Exception as exc:
            print(f"LAN {method} {path} FAIL → {exc}")

    print("DONE Pi1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
