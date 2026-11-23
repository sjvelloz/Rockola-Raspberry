"""Lower only karaoke loopback latency; leave music quantum alone."""
from __future__ import annotations

import os
import sys

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

    run(
        c,
        "cd ~/Rockola-Raspberry && git fetch origin && git reset --hard origin/main && "
        "chmod +x scripts/karaoke-mic-loopback.sh",
    )
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

# Asegurar que NO hay force global
pw-metadata -n settings 0 clock.force-quantum 0 2>/dev/null || true

# Reiniciar solo el loopback del mic (mpv/música no se tocan)
pkill -f 'pw-loopback.*rockola-karaoke' 2>/dev/null || true
rm -f /run/user/1000/rockola-karaoke-loopback.pid
sleep 0.3
bash /home/saskweise/Rockola-Raspberry/scripts/karaoke-mic-loopback.sh

# HyperX PCM estable ~0 dB
amixer -c 3 sset PCM 70 unmute 2>/dev/null || true

echo '=== clock (debe force=0, quantum~1024) ==='
pw-metadata -n settings | grep -E 'quantum|rate' || true
echo '=== loopback ==='
pgrep -af 'pw-loopback.*rockola' || true
echo '=== mpv sigue ==='
pgrep -af 'mpv ' | head -2 || true
timeout 2 pw-top -b -n 1 2>/dev/null | grep -E 'mpv|karaoke|Logitech|HyperX|ERR FORMAT|ERR ' | head -20 || true
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
