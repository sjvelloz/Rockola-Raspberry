"""Set HyperX to 100% and mute mic capture while karaoke is off."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.1.245", username="saskweise", password=PASSWORD, timeout=15)
    cmd = r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0
SINKS="$(wpctl status | sed -n '/Sinks:/,/Sources:/p')"
HX="$(printf '%s\n' "$SINKS" | grep -i hyperx | head -1 | grep -oE '[0-9]+' | head -1)"
echo "HX=$HX"
if [ -n "$HX" ]; then
  wpctl set-default "$HX"
  wpctl set-volume "$HX" 1.0
  wpctl set-mute "$HX" 0
fi
amixer -c 3 sset PCM 70 unmute >/dev/null
SRCS="$(wpctl status | sed -n '/Audio/,/Video/p' | awk '/Sources:/{p=1;next} /Filters:/{p=0} p')"
MIC="$(printf '%s\n' "$SRCS" | grep -i Logitech | head -1 | grep -oE '[0-9]+' | head -1)"
echo "MIC=$MIC"
if [ -n "$MIC" ]; then
  wpctl set-mute "$MIC" 1
  wpctl set-volume "$MIC" 0
fi
pw-metadata -n settings 0 clock.force-quantum 0 >/dev/null
pw-metadata -n settings 0 clock.quantum 1024 >/dev/null
echo 'DEFAULT:'
wpctl get-volume @DEFAULT_AUDIO_SINK@
echo 'SINKS:'
wpctl status | sed -n '/Sinks:/,/Sources:/p'
echo 'KARAOKE:'
curl -s http://127.0.0.1:8000/api/karaoke; echo
pgrep -af pw-loopback || echo no-loopback
"""
    _, stdout, stderr = c.exec_command(cmd, timeout=40)
    print(stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace"))
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
