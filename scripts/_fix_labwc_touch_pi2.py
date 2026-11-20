"""Write working labwc rc.xml and reconfigure with LABWC_PID."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> str:
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

    script = r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0

mkdir -p ~/.config/labwc
# Formato openbox_config (el que usábamos cuando iba bien) SOLO touch, sin windowRules
cat > ~/.config/labwc/rc.xml <<'EOF'
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="QDtech MPI1001 (USB 1-1.2)" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.3)" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.4)" mapToOutput="HDMI-A-2" mouseEmulation="yes"/>
</openbox_config>
EOF
# Also update rockola-session generator to match (already in git)

export LABWC_PID="$(pgrep -n labwc)"
echo "LABWC_PID=$LABWC_PID"
if [ -n "$LABWC_PID" ]; then
  labwc --reconfigure
  echo "reconfigure_exit=$?"
else
  echo "no labwc pid"
fi

# Confirm outputs
wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1

# Restart chromium onto 0,0
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do kill -9 "$pid" 2>/dev/null || true; done
sleep 1
rm -f ~/.config/rockola-chromium/SingletonLock ~/.config/rockola-chromium/SingletonSocket ~/.config/rockola-chromium/SingletonCookie
cd ~/Rockola-Raspberry
nohup bash scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
sleep 8
pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null && echo CHROMIUM_UP || echo CHROMIUM_DOWN
tail -25 /tmp/rockola-session.log
cat ~/.config/labwc/rc.xml
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/fix-labwc-touch.sh", "w") as f:
        f.write(script.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/fix-labwc-touch.sh", 0o755)
    sftp.close()
    run(c, "bash /home/saskweise/fix-labwc-touch.sh", timeout=90)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
