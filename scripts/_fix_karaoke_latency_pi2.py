"""Deploy low-latency karaoke settings to Pi2."""
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
        "chmod +x scripts/karaoke-mic-loopback.sh && "
        "mkdir -p ~/.config/pipewire/pipewire.conf.d && "
        "cp -f scripts/pipewire-rockola-lowlatency.conf "
        "~/.config/pipewire/pipewire.conf.d/99-rockola-lowlatency.conf && "
        "ls -la ~/.config/pipewire/pipewire.conf.d/",
    )
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

# Reiniciar pipewire user services para aplicar conf (cuidado: corta audio un momento)
systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true
sleep 2

# Forzar quantum ya
pw-metadata -n settings 0 clock.force-quantum 256 || true
pw-metadata -n settings 0 clock.rate 48000 || true

# Rehacer karaoke
pkill -f 'pw-loopback.*rockola-karaoke' 2>/dev/null || true
rm -f /run/user/1000/rockola-karaoke-loopback.pid
sleep 0.3
bash /home/saskweise/Rockola-Raspberry/scripts/karaoke-mic-loopback.sh

echo '=== settings ==='
pw-metadata -n settings | grep -E 'quantum|rate'
echo '=== loopback cmdline ==='
pgrep -af 'pw-loopback.*rockola'
echo '=== links (no direct mic->hx preferred) ==='
pw-link -l | grep -E 'Logitech|rockola-karaoke|HyperX Virtual' | head -40
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
