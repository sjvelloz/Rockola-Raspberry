#!/usr/bin/env bash
set -eu
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DISPLAY=:0
man wlrctl 2>/dev/null | col -b | sed -n '1,160p'
echo '===='
wlrctl pointer move 2880 540; echo move_exit=$?
# Also try relative
wlrctl toplevel focus title:Rockola 2>&1 | head -5 || true
wlrctl toplevel list -j 2>&1 | head -5 || wlrctl toplevel list 2>&1 | head -10
