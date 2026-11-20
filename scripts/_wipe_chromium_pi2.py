"""Wipe Chromium kiosk profile on Pi2 and relaunch without crash-restore bar."""
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

    # Patch start-kiosk with stronger anti-restore flags if not present
    run(
        c,
        "cd ~/Rockola-Raspberry && git fetch origin && git reset --hard origin/main && "
        "git log -1 --oneline",
    )

    launcher = r"""#!/bin/bash
exec >>/tmp/kiosk-wipe.log 2>&1
echo "=== $(date -Iseconds) wipe ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0

# Kill browser hard
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 2

PROFILE=/home/saskweise/.config/rockola-chromium
echo "Removing profile $PROFILE"
rm -rf "$PROFILE"
mkdir -p "$PROFILE"

# Also clear default chromium crash junk if any
rm -rf /home/saskweise/.config/chromium/Crash\ Reports 2>/dev/null || true

wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1 || true
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1 || true

cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/start-kiosk.sh scripts/rockola-session.sh

# Quote touch device in env
python3 - <<'PY'
from pathlib import Path
p = Path('rockola.env')
if p.exists():
    out=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.startswith('ROCKOLA_TOUCH_DEVICE=') and not line.startswith('ROCKOLA_TOUCH_DEVICE="'):
            val=line.split('=',1)[1]
            line=f'ROCKOLA_TOUCH_DEVICE="{val}"'
        out.append(line)
    p.write_text('\n'.join(out)+'\n', encoding='utf-8')
PY

export ROCKOLA_UI_POSITION=0,0
# Start kiosk directly with extra flags (bypass session env quirks)
URL=http://127.0.0.1:8000/
for _ in $(seq 1 30); do
  curl -sf "$URL" >/dev/null 2>&1 && break
  sleep 1
done

CHROME=chromium
command -v chromium >/dev/null || CHROME=chromium-browser

echo "Launching fresh chromium"
exec "$CHROME" \
  --kiosk \
  --start-fullscreen \
  --window-position=0,0 \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --hide-crash-restore-bubble \
  --disable-restore-session-state \
  --no-first-run \
  --no-default-browser-check \
  --disable-translate \
  --disable-features=TranslateUI,InfiniteSessionRestore,IsolateOrigins,site-per-process \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  --force-device-scale-factor=1 \
  --high-dpi-support=1 \
  --enable-gpu-rasterization \
  --ignore-gpu-blocklist \
  --num-raster-threads=2 \
  --user-data-dir="$PROFILE" \
  --app="$URL"
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/kiosk-wipe.sh", "w") as f:
        f.write(launcher.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/kiosk-wipe.sh", 0o755)
    sftp.close()

    run(c, "nohup /home/saskweise/kiosk-wipe.sh >/dev/null 2>&1 & echo launched")
    time.sleep(10)
    run(
        c,
        "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
        "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
        "ls -la /home/saskweise/.config/rockola-chromium | head -15; "
        "tail -30 /tmp/kiosk-wipe.log",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
