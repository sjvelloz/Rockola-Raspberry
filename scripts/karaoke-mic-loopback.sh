#!/usr/bin/env bash
# Karaoke: Logitech mic → pw-loopback → HyperX.
# No fuerza quantum global (eso rompe la música); solo pide latencia en el loopback.
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

MIC_MATCH="${ROCKOLA_MIC_MATCH:-Logitech USB Microphone}"
SINK_MATCH="${ROCKOLA_KARAOKE_SINK_MATCH:-HyperX|Kingston}"
TAG="rockola-karaoke"
PIDFILE="${XDG_RUNTIME_DIR}/rockola-karaoke-loopback.pid"
# Latencia del loopback (no global). 512 ≈ buen equilibrio mic/música en Pi.
QUANTUM="${ROCKOLA_KARAOKE_QUANTUM:-512}"
RATE="${ROCKOLA_KARAOKE_RATE:-48000}"
LATENCY="${QUANTUM}/${RATE}"

if ! command -v wpctl >/dev/null 2>&1 || ! command -v pw-loopback >/dev/null 2>&1; then
  echo "karaoke: herramientas PipeWire no disponibles"
  exit 0
fi

SINKS="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
SRCS="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | awk '/Sources:/{p=1;next} /Filters:/{p=0} p')"
MIC_ID="$(printf '%s\n' "$SRCS" | grep 'vol:' | grep -i "$MIC_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"
HX_ID="$(printf '%s\n' "$SINKS" | grep 'vol:' | grep -iE "$SINK_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"

if [ -z "${MIC_ID:-}" ] || [ -z "${HX_ID:-}" ]; then
  echo "karaoke: falta mic ($MIC_ID) o HyperX ($HX_ID)"
  exit 0
fi

MIC_NAME="$(wpctl inspect "$MIC_ID" 2>/dev/null | awk -F'"' '/node.name/ {print $2; exit}')"
HX_NAME="$(wpctl inspect "$HX_ID" 2>/dev/null | awk -F'"' '/node.name/ {print $2; exit}')"

wpctl set-mute "$MIC_ID" 0 2>/dev/null || true
wpctl set-volume "$MIC_ID" 1.0 2>/dev/null || true
wpctl set-default "$MIC_ID" 2>/dev/null || true
wpctl set-mute "$HX_ID" 0 2>/dev/null || true
wpctl set-default "$HX_ID" 2>/dev/null || true
wpctl set-volume "$HX_ID" "${ROCKOLA_SINK_VOLUME:-1.0}" 2>/dev/null || true

if command -v amixer >/dev/null 2>&1; then
  for card in 3 4 5; do
    name="$(cat /proc/asound/card${card}/id 2>/dev/null || true)"
    case "$name" in
      Microphone|mic*) amixer -c "$card" sset Mic 80% unmute 2>/dev/null || true ;;
      Sound) amixer -c "$card" sset PCM 100% unmute 2>/dev/null || true ;;
    esac
  done
fi

# Importante: NO forzar clock.force-quantum global (estropea mpv/música).
# Liberar cualquier force previo.
if command -v pw-metadata >/dev/null 2>&1; then
  pw-metadata -n settings 0 clock.force-quantum 0 >/dev/null 2>&1 || true
fi

need_restart=1
if [ -f "$PIDFILE" ]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    if tr '\0' ' ' <"/proc/$old/cmdline" 2>/dev/null | grep -q -- "-l ${LATENCY}"; then
      need_restart=0
    fi
  fi
fi

if [ "$need_restart" -eq 1 ]; then
  pkill -f "pw-loopback.*${TAG}" 2>/dev/null || true
  sleep 0.2
  if command -v pw-link >/dev/null 2>&1; then
    pw-link -d "${MIC_NAME}:capture_MONO" "${HX_NAME}:playback_FL" 2>/dev/null || true
    pw-link -d "${MIC_NAME}:capture_MONO" "${HX_NAME}:playback_FR" 2>/dev/null || true
  fi
  nohup pw-loopback -c 2 --name "$TAG" -l "$LATENCY" \
    --capture-props="node.latency=${LATENCY}" \
    --playback-props="node.latency=${LATENCY}" \
    >/tmp/rockola-karaoke.log 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.6
fi

L() { pw-link "$1" "$2" 2>/dev/null || true; }

for mp in capture_MONO capture_FL capture_FR; do
  for ip in input_MONO input_FL input_FR; do
    L "${MIC_NAME}:${mp}" "input.${TAG}:${ip}"
  done
done
for op in output_FL output_FR output_MONO; do
  L "output.${TAG}:${op}" "${HX_NAME}:playback_FL"
  L "output.${TAG}:${op}" "${HX_NAME}:playback_FR"
done

echo "karaoke: loopback=${LATENCY} (sin force global) mic=$MIC_ID → HyperX=$HX_ID pid=$(cat "$PIDFILE" 2>/dev/null || echo ?)"
pw-link -l 2>/dev/null | grep -E "Logitech|${TAG}|HyperX Virtual" | head -30 || true
