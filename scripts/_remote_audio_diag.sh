#!/usr/bin/env bash
set -eu
echo "=== env uvicorn ==="
UPID=$(pgrep -n -f 'uvicorn main:app' || true)
echo pid=$UPID
tr '\0' '\n' < /proc/"$UPID"/environ | grep -E 'XDG|PULSE|PIPE|USER' || true
echo "=== mpv ==="
pgrep -af mpv || echo no-mpv
echo "=== journal last ==="
journalctl -u jukebox.service -n 50 --no-pager | tail -50
echo "=== state ==="
curl -s http://127.0.0.1:8000/api/queue; echo
