"""Take a Wayland screenshot of the Pi2 kiosk UI if possible."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"
LOCAL = os.path.join(os.path.dirname(__file__), "..", "_pi2_ui.png")


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    cmd = r"""
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
which grim; which gnome-screenshot; which scrot; which wayshot
if command -v grim >/dev/null; then
  grim /tmp/pi2_ui.png && echo GRIM_OK
elif command -v gnome-screenshot >/dev/null; then
  gnome-screenshot -f /tmp/pi2_ui.png && echo GNOME_OK
elif command -v scrot >/dev/null; then
  scrot /tmp/pi2_ui.png && echo SCROT_OK
else
  echo NO_SCREENSHOT_TOOL
fi
ls -la /tmp/pi2_ui.png 2>/dev/null || true
"""
    _, stdout, stderr = c.exec_command(cmd, timeout=30)
    print(stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace"))
    try:
        sftp = c.open_sftp()
        sftp.get("/tmp/pi2_ui.png", os.path.abspath(LOCAL))
        print("SAVED", os.path.abspath(LOCAL))
        sftp.close()
    except Exception as e:
        print("GET_FAIL", e)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
