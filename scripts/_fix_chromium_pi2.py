"""Start rockola session/chromium on Pi2 and verify."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = os.environ.get("ROCKOLA_PI_HOST", "192.168.1.245")
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> str:
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
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    print("=== before ===")
    print(run(c, "pgrep -af chromium || echo NO_CHROMIUM; ls -la /tmp/rockola-session*.log 2>/dev/null; tail -40 /tmp/rockola-session.log 2>/dev/null || true"))

    # Kill stale kiosk attempts, reconfigure displays, relaunch session in graphical env
    script = r"""
set -e
pkill -f '/usr/lib/chromium/chromium' 2>/dev/null || true
pkill -f 'rockola-session.sh' 2>/dev/null || true
sleep 1
cd /home/saskweise/Rockola-Raspberry
# ensure autostart still points to session
mkdir -p /home/saskweise/.config/labwc /home/saskweise/.config/autostart
printf '%s\n' '/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh &' > /home/saskweise/.config/labwc/autostart
chmod +x /home/saskweise/.config/labwc/autostart
cat > /home/saskweise/.config/autostart/rockola-kiosk.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Rockola Kiosk
Exec=/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh
X-GNOME-Autostart-enabled=true
Terminal=false
EOF
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh scripts/configure-displays.sh 2>/dev/null || true

# Launch under the existing graphical user session
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
nohup bash scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
echo launched_pid=$!
sleep 6
pgrep -af chromium || echo NO_CHROMIUM
echo '--- log ---'
tail -60 /tmp/rockola-session.log || true
WAYLAND_DISPLAY=wayland-0 wlr-randr 2>/dev/null | head -40 || true
"""
    print("=== launch ===")
    print(run(c, script, timeout=90))
    time.sleep(2)
    print("=== after ===")
    print(run(c, "pgrep -af 'chromium|rockola-session' || echo still_down; curl -s --max-time 3 http://127.0.0.1:8000/api/credits"))
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
