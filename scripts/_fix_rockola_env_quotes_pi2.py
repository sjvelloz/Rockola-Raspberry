"""Quote ROCKOLA_TOUCH_DEVICE in rockola.env on Pi2 and relaunch session properly."""
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
        r"""
cd ~/Rockola-Raspberry
python3 - <<'PY'
from pathlib import Path
p = Path('rockola.env')
if not p.exists():
    print('no rockola.env')
    raise SystemExit(0)
lines = []
for line in p.read_text(encoding='utf-8').splitlines():
    if line.startswith('ROCKOLA_TOUCH_DEVICE=') and not line.startswith('ROCKOLA_TOUCH_DEVICE="'):
        val = line.split('=', 1)[1]
        line = f'ROCKOLA_TOUCH_DEVICE="{val}"'
    lines.append(line)
p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(p.read_text(encoding='utf-8'))
PY
""",
    )

    # Safer launcher using rockola-session.sh (parses env safely)
    launcher = r"""#!/bin/bash
exec >>/tmp/kiosk-hard.log 2>&1
echo "=== $(date -Iseconds) session ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do kill -9 "$pid" 2>/dev/null || true; done
sleep 1
rm -f /home/saskweise/.config/rockola-chromium/SingletonLock \
      /home/saskweise/.config/rockola-chromium/SingletonSocket \
      /home/saskweise/.config/rockola-chromium/SingletonCookie
wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1 || true
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1 || true
cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh
exec bash scripts/rockola-session.sh
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/kiosk-hard.sh", "w") as f:
        f.write(launcher.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/kiosk-hard.sh", 0o755)
    sftp.close()

    run(c, "nohup /home/saskweise/kiosk-hard.sh >/dev/null 2>&1 & echo relaunched")
    time.sleep(9)
    run(
        c,
        "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
        "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
        "tail -25 /tmp/kiosk-hard.log",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
