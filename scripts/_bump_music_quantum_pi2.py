"""Raise music PipeWire quantum to 2048; karaoke loopback at 512."""
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
        "~/.config/pipewire/pipewire.conf.d/99-rockola-lowlatency.conf",
    )
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

pw-metadata -n settings 0 clock.force-quantum 0 2>/dev/null || true
systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true
sleep 3
pw-metadata -n settings 0 clock.force-quantum 0 2>/dev/null || true
# Empujar quantum por defecto de la sesión
pw-metadata -n settings 0 clock.quantum 2048 2>/dev/null || true

pkill -f 'pw-loopback.*rockola-karaoke' 2>/dev/null || true
rm -f /run/user/1000/rockola-karaoke-loopback.pid
bash /home/saskweise/Rockola-Raspberry/scripts/karaoke-mic-loopback.sh
amixer -c 3 sset PCM 70 unmute 2>/dev/null || true

SINKS="$(wpctl status | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
HX="$(printf '%s\n' "$SINKS" | grep vol: | grep -iE 'HyperX|Kingston' | head -1 | grep -oE '[0-9]+' | head -1)"
[ -n "$HX" ] && wpctl set-default "$HX" && wpctl set-volume "$HX" 1.0

echo '=== clock ==='
pw-metadata -n settings | grep -E 'quantum|rate' || true
echo '=== loopback ==='
pgrep -af 'pw-loopback.*rockola' || true
""",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
