"""Inspect Bluetooth / mic sources on Pi2."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 45) -> str:
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
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
echo '=== lsusb ==='
lsusb 2>/dev/null || true
echo '=== bluetoothctl ==='
bluetoothctl show 2>/dev/null | head -30 || true
bluetoothctl devices 2>/dev/null || true
bluetoothctl info 2>/dev/null | head -5 || true
echo '=== paired/connected ==='
bluetoothctl devices Paired 2>/dev/null || true
bluetoothctl devices Connected 2>/dev/null || true
echo '=== arecord / cards ==='
arecord -l 2>/dev/null || true
cat /proc/asound/cards 2>/dev/null || true
echo '=== wpctl sources ==='
wpctl status 2>/dev/null | sed -n '/Sources:/,/Filters:/p' | head -40
echo '=== pactl sources ==='
pactl list sources short 2>/dev/null || true
pactl list sources 2>/dev/null | grep -E 'Name:|Description:|Mute:|State:|bluez|mic|Mic' | head -60
echo '=== dmesg bt/mic recent ==='
dmesg -T 2>/dev/null | grep -iE 'bluetooth|bluez|mic|headset|sco' | tail -30 || true
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
