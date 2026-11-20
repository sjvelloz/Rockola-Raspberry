from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.1.244", username="saskweise", password=PASSWORD, timeout=15)
    _, o, e = c.exec_command(
        "hostname; git -C ~/Rockola-Raspberry log -1 --oneline; "
        "systemctl is-active jukebox; "
        "grep BUTTON_ACTIVE_HIGH ~/Rockola-Raspberry/config.py; "
        "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
        "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
        "tail -30 /tmp/rockola-session.log 2>/dev/null || echo no_log; "
        "tail -20 /tmp/rockola-launch-debug.log 2>/dev/null || true",
        timeout=30,
    )
    print(o.read().decode(errors="replace") + e.read().decode(errors="replace"))
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
