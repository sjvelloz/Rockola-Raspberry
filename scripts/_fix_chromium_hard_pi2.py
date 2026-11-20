"""Hard reset Chromium kiosk on Pi2 without pkill matching this script."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    print(f"$ {cmd[:100]}...")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    text = out + (("\n[stderr]\n" + err) if err.strip() else "")
    print(text)
    return text


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    # Upload a clean launcher (no self-matching pkill -f strings in ssh cmdline)
    launcher = """#!/bin/bash
exec >>/tmp/kiosk-hard.log 2>&1
echo "=== $(date -Iseconds) ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0

# Kill only real browser PIDs (avoid matching this script)
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 1
for pid in $(pgrep -f 'scripts/rockola-session.sh' || true); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 1

rm -f /home/saskweise/.config/rockola-chromium/SingletonLock \
      /home/saskweise/.config/rockola-chromium/SingletonSocket \
      /home/saskweise/.config/rockola-chromium/SingletonCookie

wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1 || true
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1 || true
wlr-randr | grep -E 'HDMI|Position|Enabled' || true

cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/start-kiosk.sh scripts/rockola-session.sh
if [ -f rockola.env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./rockola.env
  set +a
fi
export ROCKOLA_UI_POSITION=0,0
echo "starting start-kiosk"
exec bash scripts/start-kiosk.sh
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/kiosk-hard.sh", "w") as f:
        f.write(launcher.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/kiosk-hard.sh", 0o755)
    sftp.close()

    run(c, "nohup /home/saskweise/kiosk-hard.sh >/dev/null 2>&1 & echo launched")
    time.sleep(9)
    run(
        c,
        "pgrep -af '/usr/lib/chromium/chromium' | head -3 || echo NO_BROWSER; "
        "tail -60 /tmp/kiosk-hard.log; "
        "curl -s -o /dev/null -w 'http=%{http_code}\\n' --max-time 3 http://127.0.0.1:8000/; "
        "XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 wlr-randr | grep -E 'HDMI|Position'",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
