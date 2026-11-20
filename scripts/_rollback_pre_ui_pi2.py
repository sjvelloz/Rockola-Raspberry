"""Full rollback to pre-UI-request behavior on Pi2 + fix labwc/touch."""
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
        "git reset --hard origin/main && git log -1 --oneline && "
        "grep -n 'height<=' youtube_service.py | head -1 && "
        "chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox",
    )

    # Fix env + kanshi + labwc rc, then relaunch
    remote = r"""
set +e
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0

cd /home/saskweise/Rockola-Raspberry

# Normalize rockola.env (quoted touch, keep aux)
python3 - <<'PY'
from pathlib import Path
p = Path('rockola.env')
data = {
  'ROCKOLA_UI_OUTPUT': 'HDMI-A-2',
  'ROCKOLA_VIDEO_OUTPUT': 'HDMI-A-1',
  'ROCKOLA_VIDEO_GEOMETRY': '1920x1080+1920+0',
  'ROCKOLA_X11_SCREEN': '1',
  'ROCKOLA_MPV_VO': 'x11',
  'ROCKOLA_MPV_FS_SCREEN': '1',
  'ROCKOLA_BLANK_TV_WHEN_IDLE': 'soft',
  'ROCKOLA_AUDIO_SINK': 'aux',
  'ROCKOLA_TOUCH_DEVICE': 'QDtech MPI1001 (USB 1-1.2)',
  'ROCKOLA_COIN_CREDITS': '3',
}
# Preserve unknown keys if present
existing = {}
if p.exists():
    for line in p.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k,v=line.split('=',1)
        v=v.strip().strip('"').strip("'")
        existing[k]=v
existing.update(data)
lines=[]
for k,v in existing.items():
    if any(ch in v for ch in ' ()/'):
        lines.append(f'{k}="{v}"')
    else:
        lines.append(f'{k}={v}')
p.write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(p.read_text(encoding='utf-8'))
PY

# Disable broken kanshi profile that references missing outputs / causes noise
mkdir -p ~/.config/kanshi
cat > ~/.config/kanshi/config <<'EOF'
profile {
    output HDMI-A-2 enable mode 1920x1080 position 0,0
    output HDMI-A-1 enable mode 1920x1080 position 1920,0
}
EOF

# Write known-good labwc rc (no invalid windowRules)
mkdir -p ~/.config/labwc
cat > ~/.config/labwc/rc.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<labwc_config>
	<touch deviceName="QDtech MPI1001 (USB 1-1.2)" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
</labwc_config>
EOF
labwc --reconfigure
echo "labwc reconfigure exit=$?"

# Kill chromium cleanly
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do kill -9 "$pid" 2>/dev/null || true; done
sleep 1
rm -rf /home/saskweise/.config/rockola-chromium
mkdir -p /home/saskweise/.config/rockola-chromium

wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1
wlr-randr | grep -E 'HDMI|Position|Enabled'

# Autostart
printf '%s\n' '/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh &' > ~/.config/labwc/autostart
chmod +x ~/.config/labwc/autostart scripts/rockola-session.sh scripts/start-kiosk.sh

nohup bash scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
echo launched
sleep 8
pgrep -af '/usr/lib/chromium/chromium' | head -2 || echo NO_CHROMIUM
tail -40 /tmp/rockola-session.log
"""
    # Upload and run to avoid shell quoting hell
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/rollback-pre-ui.sh", "w") as f:
        f.write(remote.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/rollback-pre-ui.sh", 0o755)
    sftp.close()
    run(c, "bash /home/saskweise/rollback-pre-ui.sh", timeout=90)
    time.sleep(2)
    run(
        c,
        "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
        "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
