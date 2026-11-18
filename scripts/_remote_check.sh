#!/usr/bin/env bash
set -eu
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0

# Kill current user mpv if any
pkill -f 'mpv .*mpv-user' 2>/dev/null || pkill -x mpv 2>/dev/null || true
sleep 1

echo "=== release HP from compositor ==="
wlr-randr --output HDMI-A-2 --off
sleep 1
wlr-randr | awk '/^[^ ]/ || /Enabled:/ || /Position:/ {print}'

echo "=== try drm playback 6s on HDMI-A-2 ==="
timeout 8 mpv --vo=drm --drm-device=/dev/dri/card1 --drm-connector=HDMI-A-2 \
  --ao=pipewire --volume=100 --really-quiet --length=6 \
  'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3' 2>&1 | tail -20
echo exit=$?

# That was audio only file - try with video lavfi
timeout 8 mpv --vo=drm --drm-device=/dev/dri/card1 --drm-connector=HDMI-A-2 \
  --ao=null --length=5 \
  av://lavfi:testsrc=size=1280x720:rate=30 2>&1 | tail -40
echo video_exit=$?

echo "=== restore HP to compositor ==="
wlr-randr --output HDMI-A-2 --on --pos 1920,0 || wlr-randr --output HDMI-A-2 --on
wlr-randr | awk '/^[^ ]/ || /Enabled:/ || /Position:/ {print}'
