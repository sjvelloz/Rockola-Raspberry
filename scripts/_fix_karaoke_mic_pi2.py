"""Diagnose and fix karaoke mic loopback on Pi2."""
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
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

echo '=== devices ==='
wpctl status | sed -n '/Audio/,/Video/p'

echo '=== loopback procs ==='
pgrep -af pw-loopback || echo no-pw-loopback
cat /tmp/rockola-karaoke.log 2>/dev/null || true
cat /tmp/rockola-karaoke-watch.log 2>/dev/null || true

echo '=== pw-link list ==='
pw-link -l 2>/dev/null | head -80 || true

echo '=== mic levels / mute ==='
for id in 101 103; do
  echo "-- $id --"
  wpctl get-volume "$id" 2>/dev/null || true
  wpctl inspect "$id" 2>/dev/null | grep -iE 'node.name|node.description|mute|volume|channel' | head -15
done

echo '=== record 2s from logitech ==='
SRC=alsa_input.usb-Logitech_USB_Microphone-00.mono-fallback
timeout 2 parecord --device="$SRC" /tmp/mic-test.wav 2>/tmp/mic-test.err || \
timeout 2 arecord -D plughw:4,0 -f S16_LE -r 48000 -c 1 /tmp/mic-test.wav 2>>/tmp/mic-test.err || true
ls -la /tmp/mic-test.wav 2>/dev/null || true
cat /tmp/mic-test.err 2>/dev/null || true
# peak check
python3 - <<'PY'
import wave,struct,os,sys
p='/tmp/mic-test.wav'
if not os.path.exists(p) or os.path.getsize(p)<1000:
    print('NO_WAV')
    sys.exit(0)
w=wave.open(p,'rb')
n=w.getnframes(); ch=w.getnchannels(); sw=w.getsampwidth(); rate=w.getframerate()
raw=w.readframes(n); w.close()
if sw==2:
    samples=struct.unpack('<'+'h'*(len(raw)//2), raw)
    peak=max(abs(s) for s in samples) if samples else 0
    avg=sum(abs(s) for s in samples)/len(samples) if samples else 0
    print(f'wav frames={n} rate={rate} ch={ch} peak={peak} avg={avg:.1f}')
else:
    print('wav other format', sw)
PY
""",
    )

    # Rebuild loopback with explicit pw-link style / pactl module-loopback
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export PULSE_SERVER=unix:/run/user/1000/pulse/native

# Kill old loopbacks
pkill -f 'pw-loopback.*rockola-karaoke' 2>/dev/null || true
rm -f /run/user/1000/rockola-karaoke-loopback.pid
sleep 0.5

# Unload previous pulse loopbacks if any
pactl list short modules 2>/dev/null | grep module-loopback | awk '{print $1}' | while read -r m; do
  pactl unload-module "$m" 2>/dev/null || true
done

# Find ids
SINKS="$(wpctl status | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
SRCS="$(wpctl status | sed -n '/Audio/,/Video/p' | awk '/Sources:/{p=1;next} /Filters:/{p=0} p')"
MIC="$(printf '%s\n' "$SRCS" | grep vol: | grep -i 'Logitech USB Microphone' | head -1 | grep -oE '[0-9]+' | head -1)"
HX="$(printf '%s\n' "$SINKS" | grep vol: | grep -iE 'HyperX|Kingston' | head -1 | grep -oE '[0-9]+' | head -1)"
echo "mic=$MIC hyperx=$HX"

wpctl set-mute "$MIC" 0
wpctl set-volume "$MIC" 1.0
wpctl set-default "$MIC"
wpctl set-default "$HX"
wpctl set-volume "$HX" 1.0
wpctl set-mute "$HX" 0

MIC_NAME="$(wpctl inspect "$MIC" | awk -F'"' '/node.name/ {print $2; exit}')"
HX_NAME="$(wpctl inspect "$HX" | awk -F'"' '/node.name/ {print $2; exit}')"
echo "mic_name=$MIC_NAME"
echo "hx_name=$HX_NAME"

# Try pactl module-loopback (often more reliable for monitoring)
MOD=$(pactl load-module module-loopback \
  source="$MIC_NAME" \
  sink="$HX_NAME" \
  latency_msec=20 \
  source_dont_move=true \
  sink_dont_move=true \
  2>&1) || true
echo "pactl_loopback=$MOD"

# Also start pw-loopback as backup with channels=2 remap
nohup pw-loopback -c 2 --name rockola-karaoke \
  --capture-props="media.class=Audio/Source target.object=${MIC_NAME} audio.position=[MONO] node.latency=512/48000" \
  --playback-props="media.class=Audio/Sink target.object=${HX_NAME} audio.position=[FL FR] node.latency=512/48000" \
  >/tmp/rockola-karaoke.log 2>&1 &
echo $! > /run/user/1000/rockola-karaoke-loopback.pid
sleep 1

echo '=== after fix ==='
pgrep -af 'pw-loopback|module-loopback' || true
pactl list short modules 2>/dev/null | grep loopback || true
wpctl status | sed -n '/Audio/,/Video/p' | head -50
pw-link -l 2>/dev/null | grep -iE 'Logitech|HyperX|loopback|karaoke|Rockola' | head -40 || true

# Play the recorded mic sample to HyperX so user can hear if mic captured anything
if [ -f /tmp/mic-test.wav ] && [ -s /tmp/mic-test.wav ]; then
  echo '=== playback mic-test.wav to HyperX ==='
  timeout 3 paplay --device="$HX_NAME" /tmp/mic-test.wav 2>&1 || \
  timeout 3 pw-play /tmp/mic-test.wav 2>&1 || true
fi
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
