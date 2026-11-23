"""Deploy karaoke ON/OFF UI toggle to Pi2."""
from __future__ import annotations

import os
import sys

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
        "cd ~/Rockola-Raspberry && git fetch origin && git reset --hard origin/main && "
        "git log -1 --oneline && "
        "mkdir -p ~/.config/pipewire/pipewire.conf.d && "
        "cp -f scripts/pipewire-rockola-lowlatency.conf "
        "~/.config/pipewire/pipewire.conf.d/99-rockola-lowlatency.conf",
    )
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
pkill -f 'pw-loopback.*rockola-karaoke' 2>/dev/null || true
rm -f /run/user/1000/rockola-karaoke-loopback.pid
pw-metadata -n settings 0 clock.force-quantum 0 2>/dev/null || true
pw-metadata -n settings 0 clock.quantum 2048 2>/dev/null || true
amixer -c 3 sset PCM 70 unmute 2>/dev/null || true
""",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox; "
        "curl -s http://127.0.0.1:8000/api/karaoke; echo; "
        "curl -s http://127.0.0.1:8000/ | grep -n karaoke-btn",
    )

    script = r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do kill -9 "$pid" 2>/dev/null || true; done
sleep 1
PROFILE=/home/saskweise/.config/rockola-chromium
rm -f "$PROFILE"/SingletonLock "$PROFILE"/SingletonSocket "$PROFILE"/SingletonCookie
rm -rf "$PROFILE/Default/Cache" "$PROFILE/Default/Code Cache" "$PROFILE/Default/GPUCache"
cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh scripts/karaoke-mic-loopback.sh
nohup bash scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
sleep 8
pgrep -af 'pw-loopback.*rockola' || echo 'loopback_off_ok'
curl -s http://127.0.0.1:8000/api/karaoke; echo
pgrep -af '/usr/lib/chromium/chromium .*--app=http' | head -1
tail -15 /tmp/rockola-session.log
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/deploy-karaoke-toggle.sh", "w") as f:
        f.write(script.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/deploy-karaoke-toggle.sh", 0o755)
    sftp.close()
    run(c, "bash /home/saskweise/deploy-karaoke-toggle.sh", timeout=120)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
