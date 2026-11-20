"""Step-by-step Chromium fix on Pi2."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> str:
    print(f"$ {cmd[:120]}{'...' if len(cmd) > 120 else ''}")
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

    run(c, "ls -la /run/user/1000/wayland* /run/user/1000/wlr* 2>&1; ls /run/user/1000 | head")
    run(
        c,
        "tr '\\0' '\\n' < /proc/$(pgrep -n labwc)/environ | sort | grep -Ei 'wayland|display|xdg|dbus' || true",
    )
    run(c, "test -x /home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh; echo exit=$?; head -5 /home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh | od -c | head -5")
    run(c, "bash -n /home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh && echo syntax_ok")
    run(c, "bash -n /home/saskweise/Rockola-Raspberry/scripts/start-kiosk.sh && echo kiosk_syntax_ok; head -30 /home/saskweise/Rockola-Raspberry/scripts/start-kiosk.sh")

    # Write a small launcher on the Pi and run it
    launcher = r"""#!/bin/bash
exec >>/tmp/rockola-launch-debug.log 2>&1
echo "=== $(date -Iseconds) ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
# Discover wayland socket
for s in wayland-0 wayland-1; do
  if [ -S "/run/user/1000/$s" ]; then
    export WAYLAND_DISPLAY=$s
    break
  fi
done
export DISPLAY=:0
echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY DISPLAY=$DISPLAY"
ls -la /run/user/1000/wayland* || true
cd /home/saskweise/Rockola-Raspberry
# Fix CRLF if any
sed -i 's/\r$//' scripts/rockola-session.sh scripts/start-kiosk.sh || true
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh
# Layout quickly
wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1 || true
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1 || true
# Start session (blocks on exec chromium)
bash scripts/rockola-session.sh
echo "session exited code=$?"
"""
    # Upload via sftp
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/launch-rockola.sh", "w") as f:
        f.write(launcher.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/launch-rockola.sh", 0o755)
    sftp.close()

    run(c, "pkill -f '/usr/lib/chromium/chromium' || true; pkill -f rockola-session.sh || true; sleep 1; echo cleaned")
    run(
        c,
        "nohup /home/saskweise/launch-rockola.sh >/dev/null 2>&1 & echo started; sleep 10; "
        "pgrep -af chromium || echo NO_CHROMIUM; "
        "tail -80 /tmp/rockola-launch-debug.log; echo '---'; tail -80 /tmp/rockola-session.log 2>/dev/null || echo no_session_log",
        timeout=90,
    )
    time.sleep(2)
    run(c, "pgrep -af chromium || echo NO_CHROMIUM; XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 wlr-randr 2>/dev/null | grep -E 'HDMI|Position'")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
