"""Pull latest main on Pi1, fix perms, restart jukebox, launch Chromium session."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
USER = "saskweise"
HOSTS = ["192.168.1.244", "192.168.1.150"]


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return out + (("\n[stderr]\n" + err) if err.strip() else "")


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1

    client = None
    host_used = None
    for host in HOSTS:
        print(f"try {host}")
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(host, username=USER, password=PASSWORD, timeout=12)
            client = c
            host_used = host
            print(f"connected {host}")
            break
        except Exception as exc:
            print(f" fail {type(exc).__name__}: {exc}")
            time.sleep(2)

    if client is None:
        print("Pi1 unreachable on .244/.150", file=sys.stderr)
        return 1

    print(
        run(
            client,
            "hostname; hostname -I; "
            "cd ~/Rockola-Raspberry && git fetch origin && "
            "git reset --hard origin/main && git log -1 --oneline",
        )
    )

    print(
        run(
            client,
            "chmod +x ~/Rockola-Raspberry/scripts/rockola-session.sh "
            "~/Rockola-Raspberry/scripts/start-kiosk.sh "
            "~/Rockola-Raspberry/scripts/configure-displays.sh; "
            "ls -la ~/Rockola-Raspberry/scripts/rockola-session.sh "
            "~/Rockola-Raspberry/scripts/start-kiosk.sh; "
            "grep -n BUTTON_ACTIVE_HIGH ~/Rockola-Raspberry/config.py; "
            "grep ROCKOLA_COIN_CREDITS ~/Rockola-Raspberry/rockola.env 2>/dev/null || true",
        )
    )

    # Autostart → rockola-session
    print(
        run(
            client,
            "mkdir -p ~/.config/labwc ~/.config/autostart; "
            "printf '%s\\n' '/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh &' "
            "> ~/.config/labwc/autostart; chmod +x ~/.config/labwc/autostart; "
            "cat > ~/.config/autostart/rockola-kiosk.desktop <<'EOF'\n"
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Rockola Kiosk\n"
            "Exec=/home/saskweise/Rockola-Raspberry/scripts/rockola-session.sh\n"
            "X-GNOME-Autostart-enabled=true\n"
            "Terminal=false\n"
            "EOF\n"
            "cat ~/.config/labwc/autostart; echo OK_autostart",
        )
    )

    # Restart jukebox
    print(
        run(
            client,
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox.service; "
            "sleep 2; systemctl is-active jukebox",
        )
    )

    # Launch session/chromium under graphical env
    launcher = r"""#!/bin/bash
exec >>/tmp/rockola-launch-debug.log 2>&1
echo "=== $(date -Iseconds) ==="
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
for s in wayland-0 wayland-1; do
  if [ -S "/run/user/1000/$s" ]; then export WAYLAND_DISPLAY=$s; break; fi
done
export DISPLAY=:0
echo "WAYLAND=$WAYLAND_DISPLAY"
pkill -f '/usr/lib/chromium/chromium' >/dev/null 2>&1 || true
sleep 1
cd /home/saskweise/Rockola-Raspberry
sed -i 's/\r$//' scripts/rockola-session.sh scripts/start-kiosk.sh || true
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh
bash scripts/rockola-session.sh
echo "session exited=$?"
"""
    sftp = client.open_sftp()
    with sftp.file("/home/saskweise/launch-rockola.sh", "w") as f:
        f.write(launcher.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/launch-rockola.sh", 0o755)
    sftp.close()

    print(
        run(
            client,
            "nohup /home/saskweise/launch-rockola.sh >/dev/null 2>&1 & echo launched; "
            "sleep 8; "
            "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
            "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
            "pgrep -c chromium || true; "
            "tail -40 /tmp/rockola-session.log 2>/dev/null || true; "
            "tail -20 /tmp/rockola-launch-debug.log 2>/dev/null || true",
            timeout=90,
        )
    )

    print(f"DONE on {host_used}")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
