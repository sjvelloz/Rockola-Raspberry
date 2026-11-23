"""Push karaoke loopback fix and verify links on Pi2."""
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
        "git reset --hard origin/main && "
        "chmod +x scripts/karaoke-mic-loopback.sh",
    )
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export PULSE_SERVER=unix:/run/user/1000/pulse/native

# ALSA capture gain for Logitech mic card
amixer -c 4 scontents 2>/dev/null | head -40 || true
amixer -c 4 sset Mic 100% unmute 2>/dev/null || true
amixer -c 4 sset Capture 100% unmute 2>/dev/null || true
amixer -c 4 sset 'Mic Capture' 100% unmute 2>/dev/null || true

# HyperX PCM unmute
amixer -c 3 scontents 2>/dev/null | head -40 || true
amixer -c 3 sset PCM 100% unmute 2>/dev/null || true
amixer -c 3 sset Speaker 100% unmute 2>/dev/null || true

bash /home/saskweise/Rockola-Raspberry/scripts/karaoke-mic-loopback.sh
sleep 1
echo '=== modules ==='
pactl list short modules 2>/dev/null | grep loopback || echo no-pactl-loopback
echo '=== links ==='
pw-link -l 2>/dev/null | grep -iE 'Logitech|HyperX|loopback|karaoke|Rockola' | head -50
echo '=== sink-inputs / source-outputs ==='
pactl list short sink-inputs 2>/dev/null || true
pactl list short source-outputs 2>/dev/null || true
wpctl status | sed -n '/Audio/,/Video/p' | head -55
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
