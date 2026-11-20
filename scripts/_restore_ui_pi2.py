"""Restore old UI on Pi2, clean Chromium crash banner, relaunch kiosk."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
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
        "git reset --hard origin/main && git log -1 --oneline",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox",
    )

    launcher = r"""#!/bin/bash
exec >>/tmp/kiosk-restore.log 2>&1
echo "=== $(date -Iseconds) ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0

for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 2

PROFILE=/home/saskweise/.config/rockola-chromium
rm -f "$PROFILE"/SingletonLock "$PROFILE"/SingletonSocket "$PROFILE"/SingletonCookie
# Quitar banner rojo de errores / crashed session
if [ -f "$PROFILE/Default/Preferences" ]; then
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/g' "$PROFILE/Default/Preferences" || true
  sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/g' "$PROFILE/Default/Preferences" || true
fi
rm -rf "$PROFILE/Default/Session Storage" \
       "$PROFILE/Default/Sessions" \
       "$PROFILE/Crash Reports" 2>/dev/null || true

# Quote touch device if needed
python3 - <<'PY'
from pathlib import Path
p = Path('/home/saskweise/Rockola-Raspberry/rockola.env')
if p.exists():
    lines=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.startswith('ROCKOLA_TOUCH_DEVICE=') and not line.startswith('ROCKOLA_TOUCH_DEVICE="'):
            val=line.split('=',1)[1]
            line=f'ROCKOLA_TOUCH_DEVICE="{val}"'
        lines.append(line)
    p.write_text('\n'.join(lines)+'\n', encoding='utf-8')
PY

wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1 || true
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1 || true

cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh
mkdir -p /home/saskweise/.config/labwc
printf '%s\n' '/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh &' > /home/saskweise/.config/labwc/autostart
chmod +x /home/saskweise/.config/labwc/autostart
exec bash scripts/rockola-session.sh
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/kiosk-restore.sh", "w") as f:
        f.write(launcher.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/kiosk-restore.sh", 0o755)
    sftp.close()

    run(c, "nohup /home/saskweise/kiosk-restore.sh >/dev/null 2>&1 & echo launched")
    time.sleep(10)
    run(
        c,
        "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
        "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
        "tail -30 /tmp/kiosk-restore.log; "
        "tail -15 /tmp/rockola-session.log",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
