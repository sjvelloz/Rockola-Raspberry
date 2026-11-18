#!/bin/bash
set -eu
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
echo "=== host ==="
hostname; hostname -I
echo "=== env ==="
cat ~/Rockola-Raspberry/rockola.env 2>/dev/null || true
echo "=== layout ==="
wlr-randr 2>/dev/null | awk '/^[^ ]/ || /Position:/ || /Enabled:/ {print}' || true
echo "=== xrandr ==="
xrandr --listmonitors 2>/dev/null || true
echo "=== procs ==="
pgrep -af chromium | head -5 || true
pgrep -af 'mpv ' | head -5 || true
echo "=== labwc ==="
cat ~/.config/labwc/rc.xml 2>/dev/null || true
UP=$(pgrep -n -f 'uvicorn main:app' || true)
echo "uvicorn=$UP"
if [ -n "$UP" ]; then tr '\0' '\n' < /proc/"$UP"/environ | grep ROCKOLA || true; fi
echo "=== toplevels ==="
wlrctl toplevel list 2>/dev/null || true
