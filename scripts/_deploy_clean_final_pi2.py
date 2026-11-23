"""Commit-pull deploy: mute mic when karaoke off, restore clean music."""
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

    def run(cmd: str, timeout: int = 90) -> None:
        _, stdout, stderr = c.exec_command(cmd, timeout=timeout)
        print(stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace"))

    run(
        "cd ~/Rockola-Raspberry && git fetch origin && git reset --hard origin/main && "
        "git log -1 --oneline"
    )
    run(
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; sleep 3; "
        "systemctl is-active jukebox"
    )
    run(
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
pkill -f 'pw-loopback.*rockola' 2>/dev/null || true
python3 - <<'PY'
import json, urllib.request
req=urllib.request.Request(
    'http://127.0.0.1:8000/api/karaoke',
    data=json.dumps({'enabled': False}).encode(),
    headers={'Content-Type':'application/json'},
    method='POST',
)
print(urllib.request.urlopen(req, timeout=30).read().decode())
print(urllib.request.urlopen('http://127.0.0.1:8000/api/karaoke').read().decode())
PY
SINKS="$(wpctl status | sed -n '/Sinks:/,/Sources:/p')"
HX="$(printf '%s\n' "$SINKS" | grep -i hyperx | head -1 | grep -oE '[0-9]+' | head -1)"
[ -n "$HX" ] && wpctl set-default "$HX" && wpctl set-volume "$HX" 1.0 && wpctl set-mute "$HX" 0
amixer -c 3 sset PCM 70 unmute >/dev/null
SRCS="$(wpctl status | sed -n '/Audio/,/Video/p' | awk '/Sources:/{p=1;next} /Filters:/{p=0} p')"
MIC="$(printf '%s\n' "$SRCS" | grep -i Logitech | head -1 | grep -oE '[0-9]+' | head -1)"
[ -n "$MIC" ] && wpctl set-mute "$MIC" 1 && wpctl set-volume "$MIC" 0
pw-metadata -n settings 0 clock.force-quantum 0 >/dev/null
pw-metadata -n settings 0 clock.quantum 1024 >/dev/null
echo FINAL
wpctl get-volume @DEFAULT_AUDIO_SINK@
pgrep -af pw-loopback || echo no-loopback
pgrep -af 'mpv ' | head -1
"""
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
