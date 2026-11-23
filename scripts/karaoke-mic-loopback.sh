#!/usr/bin/env bash
# Karaoke: micrófono Logitech siempre abierto hacia HyperX (pw-link directo).
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
export PULSE_SERVER="${PULSE_SERVER:-unix:${XDG_RUNTIME_DIR}/pulse/native}"

MIC_MATCH="${ROCKOLA_MIC_MATCH:-Logitech USB Microphone}"
SINK_MATCH="${ROCKOLA_KARAOKE_SINK_MATCH:-HyperX|Kingston}"

if ! command -v wpctl >/dev/null 2>&1 || ! command -v pw-link >/dev/null 2>&1; then
  echo "karaoke: wpctl/pw-link no disponibles"
  exit 0
fi

SINKS="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
SRCS="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | awk '/Sources:/{p=1;next} /Filters:/{p=0} p')"

MIC_ID="$(printf '%s\n' "$SRCS" | grep 'vol:' | grep -i "$MIC_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"
HX_ID="$(printf '%s\n' "$SINKS" | grep 'vol:' | grep -iE "$SINK_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"

if [ -z "${MIC_ID:-}" ]; then
  echo "karaoke: sin micrófono todavía"
  exit 0
fi
if [ -z "${HX_ID:-}" ]; then
  echo "karaoke: sin HyperX"
  exit 0
fi

MIC_NAME="$(wpctl inspect "$MIC_ID" 2>/dev/null | awk -F'"' '/node.name/ {print $2; exit}')"
HX_NAME="$(wpctl inspect "$HX_ID" 2>/dev/null | awk -F'"' '/node.name/ {print $2; exit}')"

# Volumen / unmute
wpctl set-mute "$MIC_ID" 0 2>/dev/null || true
wpctl set-volume "$MIC_ID" 1.0 2>/dev/null || true
wpctl set-default "$MIC_ID" 2>/dev/null || true
wpctl set-mute "$HX_ID" 0 2>/dev/null || true
wpctl set-default "$HX_ID" 2>/dev/null || true
wpctl set-volume "$HX_ID" "${ROCKOLA_SINK_VOLUME:-1.0}" 2>/dev/null || true

# Ganancia ALSA del mic (card "Microphone") — 70% para no saturar ruido
if command -v amixer >/dev/null 2>&1; then
  for card in 3 4 5; do
    name="$(cat /proc/asound/card${card}/id 2>/dev/null || true)"
    case "$name" in
      Microphone|mic*)
        amixer -c "$card" sset Mic 70% unmute 2>/dev/null || true
        amixer -c "$card" sset Capture 70% unmute 2>/dev/null || true
        ;;
      Sound)
        amixer -c "$card" sset PCM 100% unmute 2>/dev/null || true
        ;;
    esac
  done
fi

# Enlace directo mic → HyperX (FL+FR). Idempotente: pw-link falla si ya existe.
link_ok=0
for src in "${MIC_NAME}:capture_MONO" "${MIC_NAME}:capture_FL" "${MIC_NAME}:capture_FR"; do
  pw-link "$src" "${HX_NAME}:playback_FL" 2>/dev/null && link_ok=1 || true
  pw-link "$src" "${HX_NAME}:playback_FR" 2>/dev/null && link_ok=1 || true
done

# Comprobar
if pw-link -l 2>/dev/null | grep -F "${MIC_NAME}:capture" | grep -q "${HX_NAME}:playback"; then
  echo "karaoke: OK mic=$MIC_ID → HyperX=$HX_ID ($MIC_NAME → $HX_NAME)"
  exit 0
fi

if [ "$link_ok" -eq 1 ]; then
  echo "karaoke: enlaces creados mic=$MIC_ID → HyperX=$HX_ID"
  exit 0
fi

echo "karaoke: no se pudo enlazar ($MIC_NAME → $HX_NAME)"
pw-link -o 2>/dev/null | grep -i logitech || true
pw-link -i 2>/dev/null | grep -i hyperx || true
exit 0
