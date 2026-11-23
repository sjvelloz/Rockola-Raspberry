"""Fully restore clean music path on Pi2 (karaoke hard-off)."""
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
        "cd ~/Rockola-Raspberry && git fetch origin && git reset --hard origin/main",
    )

    # Hard clean audio stack
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

echo '=== kill karaoke leftovers ==='
pkill -f 'pw-loopback.*rockola' 2>/dev/null || true
pkill -f 'karaoke-mic-loopback' 2>/dev/null || true
pkill -f 'rockola-karaoke-watch' 2>/dev/null || true
rm -f /run/user/1000/rockola-karaoke-loopback.pid /run/user/1000/rockola-karaoke-enabled

# Conf limpia y estable para música
mkdir -p ~/.config/pipewire/pipewire.conf.d
rm -f ~/.config/pipewire/pipewire.conf.d/99-rockola-lowlatency.conf
cp -f ~/Rockola-Raspberry/scripts/pipewire-rockola-lowlatency.conf \
  ~/.config/pipewire/pipewire.conf.d/99-rockola-music.conf

echo '=== restart pipewire ==='
systemctl --user restart pipewire pipewire-pulse wireplumber
sleep 3

pw-metadata -n settings 0 clock.force-quantum 0 2>/dev/null || true
pw-metadata -n settings 0 clock.force-rate 0 2>/dev/null || true
pw-metadata -n settings 0 clock.quantum 1024 2>/dev/null || true

# HyperX default + PCM 0 dB
SINKS="$(wpctl status | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
HX="$(printf '%s\n' "$SINKS" | grep vol: | grep -iE 'HyperX|Kingston' | head -1 | grep -oE '[0-9]+' | head -1)"
echo "hyperx=$HX"
if [ -n "$HX" ]; then
  wpctl set-default "$HX"
  wpctl set-mute "$HX" 0
  wpctl set-volume "$HX" 1.0
fi
amixer -c 3 sset PCM 70 unmute 2>/dev/null || true

# Desconectar mic de cualquier sink (best effort)
MIC_NAME=$(wpctl status | sed -n '/Sources:/,/Filters:/p' | grep -i Logitech | head -1)
echo "mic_line=$MIC_NAME"

echo '=== after clean ==='
pw-metadata -n settings | grep -E 'quantum|rate|force' || true
wpctl status | sed -n '/Audio/,/Video/p' | head -40
pgrep -af 'pw-loopback' || echo no-loopback
""",
    )

    # Force karaoke API off + restart jukebox so mpv is fresh
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; sleep 3; "
        "systemctl is-active jukebox",
    )
    run(
        c,
        r"""
python3 - <<'PY'
import json, urllib.request, time
req=urllib.request.Request(
    'http://127.0.0.1:8000/api/karaoke',
    data=json.dumps({'enabled': False}).encode(),
    headers={'Content-Type':'application/json'},
    method='POST',
)
print('karaoke', urllib.request.urlopen(req, timeout=30).read().decode())
print('status', urllib.request.urlopen('http://127.0.0.1:8000/api/karaoke').read().decode())
time.sleep(2)
PY
export XDG_RUNTIME_DIR=/run/user/1000
# Reafirmar HyperX tras jukebox
SINKS="$(wpctl status | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
HX="$(printf '%s\n' "$SINKS" | grep vol: | grep -iE 'HyperX|Kingston' | head -1 | grep -oE '[0-9]+' | head -1)"
[ -n "$HX" ] && wpctl set-default "$HX" && wpctl set-volume "$HX" 1.0
pgrep -af 'mpv ' | head -2
pgrep -af pw-loopback || echo no-loopback
timeout 2 pw-top -b -n 1 2>/dev/null | head -25 || true
grep -E 'AO:|swresample|48000|44100' /home/saskweise/Rockola-Raspberry/logs/mpv-ambient.log 2>/dev/null | tail -12 || true
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
