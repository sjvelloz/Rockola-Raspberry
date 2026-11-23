"""Deploy HyperX output + karaoke loopback + no-duplicate queue to Pi2."""
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
        "cd ~/Rockola-Raspberry && git fetch origin && "
        "git reset --hard origin/main && git log -1 --oneline",
    )
    run(
        c,
        "touch ~/Rockola-Raspberry/rockola.env; "
        "if grep -q '^ROCKOLA_AUDIO_SINK=' ~/Rockola-Raspberry/rockola.env; then "
        "sed -i 's/^ROCKOLA_AUDIO_SINK=.*/ROCKOLA_AUDIO_SINK=hyperx/' "
        "~/Rockola-Raspberry/rockola.env; "
        "else echo 'ROCKOLA_AUDIO_SINK=hyperx' >> ~/Rockola-Raspberry/rockola.env; fi; "
        "grep -E 'AUDIO|SINK|MIC' ~/Rockola-Raspberry/rockola.env",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox",
    )

    script = r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
cd /home/saskweise/Rockola-Raspberry
chmod +x scripts/karaoke-mic-loopback.sh scripts/rockola-session.sh scripts/start-kiosk.sh

# Forzar HyperX ya
SINKS="$(wpctl status | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
HID="$(printf '%s\n' "$SINKS" | grep vol: | grep -iE 'HyperX|Kingston' | head -1 | grep -oE '[0-9]+' | head -1)"
if [ -n "$HID" ]; then
  wpctl set-default "$HID"
  wpctl set-volume "$HID" 1.0
  echo "hyperx_sink=$HID"
fi
bash scripts/karaoke-mic-loopback.sh || true

# Soft reload UI: kill chromium + relaunch session (keeps labwc)
for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 1
PROFILE=/home/saskweise/.config/rockola-chromium
rm -f "$PROFILE"/SingletonLock "$PROFILE"/SingletonSocket "$PROFILE"/SingletonCookie
rm -rf "$PROFILE/Default/Cache" "$PROFILE/Default/Code Cache" "$PROFILE/Default/GPUCache"
nohup bash scripts/rockola-session.sh >/tmp/rockola-session.log 2>&1 &
sleep 8
wpctl status | sed -n '/Sinks:/,/Sources:/p'
wpctl status | sed -n '/Sources:/,/Filters:/p' | head -20
pgrep -af 'pw-loopback|rockola-karaoke' | head -5 || echo no-loopback
pgrep -af '/usr/lib/chromium/chromium .*--app=http' | head -1 || echo no-chromium
tail -25 /tmp/rockola-session.log
"""
    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/deploy-hyperx.sh", "w") as f:
        f.write(script.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/deploy-hyperx.sh", 0o755)
    sftp.close()
    run(c, "bash /home/saskweise/deploy-hyperx.sh", timeout=120)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
