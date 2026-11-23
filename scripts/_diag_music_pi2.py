"""Deep diagnosis of bad music quality on Pi2 HyperX."""
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
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

echo '=== clock ==='
pw-metadata -n settings | grep -E 'quantum|rate|force'

echo '=== wpctl audio ==='
wpctl status | sed -n '/Audio/,/Video/p'

echo '=== hyperx inspect ==='
HX=$(wpctl status | sed -n '/Sinks:/,/Sources:/p' | grep -i hyperx | head -1 | grep -oE '[0-9]+' | head -1)
echo HX=$HX
wpctl inspect "$HX" 2>/dev/null | grep -iE 'node.name|api.alsa|format|rate|channel|period|latency|route|profile|device.profile' | head -40

echo '=== alsa hyperx card ==='
cat /proc/asound/cards
for c in 3 4; do
  echo "-- card $c $(cat /proc/asound/card$c/id 2>/dev/null) --"
  amixer -c $c scontents 2>/dev/null | head -50
  cat /proc/asound/card$c/stream0 2>/dev/null | head -40
done

echo '=== mpv cmdline / log tail ==='
pgrep -af 'mpv ' | head -3
tail -40 /home/saskweise/Rockola-Raspberry/logs/mpv-user.log 2>/dev/null || true
tail -20 /home/saskweise/Rockola-Raspberry/logs/mpv-ambient.log 2>/dev/null || true

echo '=== pw-top snapshot ==='
timeout 3 pw-top -b -n 2 2>/dev/null | head -40 || true

echo '=== links involving hyperx ==='
pw-link -l | grep -iE 'HyperX|rockola|mpv|Logitech' | head -50

echo '=== journal pipewire xruns ==='
journalctl --user -u pipewire -u wireplumber --since '10 min ago' --no-pager 2>/dev/null | grep -iE 'xrun|underrun|error|latency|alsa' | tail -30 || true
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
