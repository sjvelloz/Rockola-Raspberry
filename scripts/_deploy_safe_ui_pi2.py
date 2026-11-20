"""Deploy safe UI tweaks to Pi2 and reload Chromium without wiping profile layout."""
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
    text = stdout.read().decode(errors="replace") + stderr.read().decode(
        errors="replace"
    )
    print(text)
    return text


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    run(
        c,
        "cd ~/Rockola-Raspberry && git fetch origin && "
        "git reset --hard origin/main && git log -1 --oneline && "
        "grep -n 'height<=720' youtube_service.py && "
        "grep -n clear-search-btn static/index.html && "
        "grep -n enableTouchScroll static/js/app.js | head -2",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox",
    )

    script = r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
export LABWC_PID="$(pgrep -n labwc)"

for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 1
rm -f /home/saskweise/.config/rockola-chromium/SingletonLock \
      /home/saskweise/.config/rockola-chromium/SingletonSocket \
      /home/saskweise/.config/rockola-chromium/SingletonCookie

cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh
nohup bash scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
sleep 8
pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null && echo CHROMIUM_UP || echo CHROMIUM_DOWN
tail -20 /tmp/rockola-session.log
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/deploy-safe-ui.sh", "w") as f:
        f.write(script.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/deploy-safe-ui.sh", 0o755)
    sftp.close()
    run(c, "bash /home/saskweise/deploy-safe-ui.sh", timeout=90)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
