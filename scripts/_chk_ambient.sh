#!/bin/bash
set -eu
export XDG_RUNTIME_DIR=/run/user/1000
echo "=== sinks ==="
wpctl status 2>/dev/null | sed -n '/Sinks/,/Sources/p'
echo "=== default ==="
wpctl get-volume @DEFAULT_AUDIO_SINK@
pactl info 2>/dev/null | grep -i 'default sink' || true
pactl list short sinks 2>/dev/null || true
echo "=== mpv ambient log ==="
tail -30 ~/Rockola-Raspberry/logs/mpv-ambient.log 2>/dev/null | grep -iE 'ao/|error|Audio|pipewire|alsa|hdmi' || tail -15 ~/Rockola-Raspberry/logs/mpv-ambient.log
echo "=== set volume 100% and prefer non-hdmi if possible ==="
# List sink ids/names
wpctl status 2>/dev/null
