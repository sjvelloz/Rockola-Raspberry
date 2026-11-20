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
    c.connect("192.168.1.245", username="saskweise", password=PASSWORD, timeout=15)
    cmd = (
        "chmod +x ~/Rockola-Raspberry/scripts/rockola-session.sh "
        "~/Rockola-Raspberry/scripts/start-kiosk.sh "
        "~/Rockola-Raspberry/scripts/configure-displays.sh; "
        "ls -la ~/Rockola-Raspberry/scripts/rockola-session.sh "
        "~/Rockola-Raspberry/scripts/start-kiosk.sh; "
        "pgrep -af '/usr/lib/chromium/chromium --kiosk' | head -1 || echo NO_CHROMIUM"
    )
    _, o, e = c.exec_command(cmd, timeout=30)
    print(o.read().decode(errors="replace") + e.read().decode(errors="replace"))
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
