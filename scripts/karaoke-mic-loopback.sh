#!/usr/bin/env bash
# Mantiene el micrófono de karaoke abierto: loopback Source → HyperX.
# El dongle suele aparecer como "Logitech USB Microphone" (USB).

set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

MIC_MATCH="${ROCKOLA_MIC_MATCH:-Logitech USB Microphone}"
SINK_MATCH="${ROCKOLA_KARAOKE_SINK_MATCH:-HyperX|Kingston}"
PIDFILE="${XDG_RUNTIME_DIR}/rockola-karaoke-loopback.pid"
NAME="rockola-karaoke"

if ! command -v wpctl >/dev/null 2>&1 || ! command -v pw-loopback >/dev/null 2>&1; then
  echo "karaoke: wpctl/pw-loopback no disponibles"
  exit 0
fi

# Source del mic (prioriza Logitech; evita HyperX headset mic si hay mic dedicado)
SRC_BLOCK="$(wpctl status 2>/dev/null | awk '/Sources:/{p=1;next} /Filters:/{p=0} p')"
SRC_ID="$(printf '%s\n' "$SRC_BLOCK" | grep 'vol:' | grep -i "$MIC_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"
if [ -z "${SRC_ID:-}" ]; then
  SRC_ID="$(printf '%s\n' "$SRC_BLOCK" | grep 'vol:' | grep -viE 'HyperX|hdmi|isp|monitor' | head -1 | grep -oE '[0-9]+' | head -1 || true)"
fi
if [ -z "${SRC_ID:-}" ]; then
  echo "karaoke: sin micrófono todavía"
  exit 0
fi

# Sink HyperX (tarjeta de sonido USB)
SNK_BLOCK="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
SNK_ID="$(printf '%s\n' "$SNK_BLOCK" | grep 'vol:' | grep -iE "$SINK_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"
if [ -z "${SNK_ID:-}" ]; then
  echo "karaoke: sin sink HyperX"
  exit 0
fi

SRC_NAME="$(wpctl inspect "$SRC_ID" 2>/dev/null | awk -F'"' '/node.name/ {print $2; exit}')"
SNK_NAME="$(wpctl inspect "$SNK_ID" 2>/dev/null | awk -F'"' '/node.name/ {print $2; exit}')"

wpctl set-mute "$SRC_ID" 0 2>/dev/null || true
wpctl set-volume "$SRC_ID" 1.0 2>/dev/null || true
wpctl set-default "$SRC_ID" 2>/dev/null || true
wpctl set-default "$SNK_ID" 2>/dev/null || true
wpctl set-volume "$SNK_ID" "${ROCKOLA_SINK_VOLUME:-1.0}" 2>/dev/null || true

# ¿Ya hay un loopback vivo?
if [ -f "$PIDFILE" ]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    echo "karaoke: loopback ok pid=$old mic=$SRC_ID($SRC_NAME) → sink=$SNK_ID($SNK_NAME)"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

# Mata instancias previas con el mismo nombre
pkill -f "pw-loopback.*${NAME}" 2>/dev/null || true
sleep 0.3

nohup pw-loopback \
  --name "$NAME" \
  --capture-props="media.class=Audio/Source target.object=${SRC_NAME} node.description=Rockola Karaoke Mic" \
  --playback-props="media.class=Audio/Sink target.object=${SNK_NAME} node.description=Rockola Karaoke Out" \
  >/tmp/rockola-karaoke.log 2>&1 &
echo $! >"$PIDFILE"
sleep 0.5
if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "karaoke: started pid=$(cat "$PIDFILE") mic=$SRC_ID → sink=$SNK_ID"
else
  echo "karaoke: falló al arrancar (ver /tmp/rockola-karaoke.log)"
  rm -f "$PIDFILE"
fi
