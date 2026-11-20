from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, o, e = c.exec_command(cmd, timeout=timeout)
    text = o.read().decode(errors="replace") + e.read().decode(errors="replace")
    print(text)
    return text


def main() -> int:
    if not PASSWORD:
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.1.245", username="saskweise", password=PASSWORD, timeout=15)
    run(
        c,
        "cd ~/Rockola-Raspberry && git fetch origin && git reset --hard origin/main && "
        "git log -1 --oneline && chmod +x scripts/*.sh",
    )
    script = r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
export LABWC_PID="$(pgrep -n labwc)"

# Kill browser first so session can rewrite cleanly
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do kill -9 "$pid" 2>/dev/null || true; done
sleep 1

cd ~/Rockola-Raspberry
# Force write good rc now
bash -c '
UI_OUT=HDMI-A-2
TOUCH_DEV="QDtech MPI1001 (USB 1-1.2)"
mkdir -p ~/.config/labwc
cat > ~/.config/labwc/rc.xml <<EOF
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="${TOUCH_DEV}" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.2)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.3)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.4)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
</openbox_config>
EOF
'
export LABWC_PID="$(pgrep -n labwc)"
labwc --reconfigure
echo reconfigure=$?
echo '--- rc.xml ---'
cat ~/.config/labwc/rc.xml

wlr-randr --output HDMI-A-2 --on --pos 0,0 --transform normal --scale 1
wlr-randr --output HDMI-A-1 --on --pos 1920,0 --transform normal --scale 1

rm -f ~/.config/rockola-chromium/Singleton*
nohup bash scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
sleep 8
pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null && echo CHROMIUM_UP || echo CHROMIUM_DOWN
echo '--- session log ---'
tail -30 /tmp/rockola-session.log
echo '--- rc after session ---'
head -20 ~/.config/labwc/rc.xml
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/fix-labwc-final.sh", "w") as f:
        f.write(script.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/fix-labwc-final.sh", 0o755)
    sftp.close()
    run(c, "bash /home/saskweise/fix-labwc-final.sh", timeout=90)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
