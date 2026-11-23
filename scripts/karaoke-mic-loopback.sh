#!/usr/bin/env bash
# Karaoke: micrófono Logitech → HyperX siempre abierto (module-loopback).
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
export PULSE_SERVER="${PULSE_SERVER:-unix:${XDG_RUNTIME_DIR}/pulse/native}"

MIC_MATCH="${ROCKOLA_MIC_MATCH:-Logitech USB Microphone}"
SINK_MATCH="${ROCKOLA_KARAOKE_SINK_MATCH:-HyperX|Kingston}"
TAG="rockola-karaoke"
STATE="${XDG_RUNTIME_DIR}/rockola-karaoke.state"

if ! command -v wpctl >/dev/null 2>&1; then
  echo "karaoke: wpctl no disponible"
  exit 0
fi

SINKS="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
SRCS="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | awk '/Sources:/{p=1;next} /Filters:/{p=0} p')"

MIC_ID="$(printf '%s\n' "$SRCS" | grep 'vol:' | grep -i "$MIC_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"
if [ -z "${MIC_ID:-}" ]; then
  echo "karaoke: sin micrófono todavía"
  exit 0
fi

HX_ID="$(printf '%s\n' "$SINKS" | grep 'vol:' | grep -iE "$SINK_MATCH" | head -1 | grep -oE '[0-9]+' | head -1 || true)"
if [ -z "${HX_ID:-}" ]; then
  echo "karaoke: sin HyperX"
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

# ¿Ya hay un loopback vivo y enlazado?
if command -v pactl >/dev/null 2>&1; then
  if pactl list short modules 2>/dev/null | grep -q "module-loopback.*source=${MIC_NAME}.*sink=${HX_NAME}"; then
    echo "karaoke: pactl loopback ok mic=$MIC_ID → sink=$HX_ID"
    exit 0
  fi
  # Quitar loopbacks karaoke viejos
  pactl list short modules 2>/dev/null | grep module-loopback | while read -r mid rest; do
    case "$rest" in
      *"$TAG"*|*source="${MIC_NAME}"*|*Logitech*)
        pactl unload-module "$mid" 2>/dev/null || true
        ;;
    esac
  done
fi

# Matar pw-loopback viejo (la config anterior no enlazaba bien)
pkill -f "pw-loopback.*${TAG}" 2>/dev/null || true
rm -f "${XDG_RUNTIME_DIR}/rockola-karaoke-loopback.pid" 2>/dev/null || true

LOADED=""
if command -v pactl >/dev/null 2>&1; then
  LOADED="$(pactl load-module module-loopback \
    source="$MIC_NAME" \
    sink="$HX_NAME" \
    latency_msec=30 \
    source_dont_move=true \
    sink_dont_move=true \
    sink_input_properties=media.name=${TAG} \
    2>&1 || true)"
fi

if [[ "$LOADED" =~ ^[0-9]+$ ]]; then
  echo "module=$LOADED" >"$STATE"
  echo "karaoke: pactl module-loopback=$LOADED mic=$MIC_ID($MIC_NAME) → sink=$HX_ID($HX_NAME)"
  exit 0
fi

echo "karaoke: pactl falló ($LOADED); probando pw-loopback+pw-link"

# Fallback: pw-loopback + enlaces manuales
nohup pw-loopback -c 1 --name "$TAG" \
  >/tmp/rockola-karaoke.log 2>&1 &
echo $! >"${XDG_RUNTIME_DIR}/rockola-karaoke-loopback.pid"
sleep 0.8

# Enlazar mic → input del loopback y output del loopback → HyperX
if command -v pw-link >/dev/null 2>&1; then
  # Desenlaces previos del tag
  pw-link -d "${MIC_NAME}:capture_MONO" 2>/dev/null || true
  # Buscar puertos del loopback
  pw-link -o 2>/dev/null | grep -i "$TAG" || true
  pw-link -i 2>/dev/null | grep -i "$TAG" || true

  # mono mic → loopback capture (varios nombres posibles)
  for cap in \
    "input.${TAG}:capture_MONO" \
    "input.${TAG}:capture_FL" \
    "${TAG}:input_MONO" \
    "loopback-.*:input_FL"
  do
    pw-link "${MIC_NAME}:capture_MONO" "$cap" 2>/dev/null && break || true
  done

  for play in \
    "output.${TAG}:output_MONO" \
    "output.${TAG}:output_FL" \
    "${TAG}:output_FL"
  do
    pw-link "$play" "${HX_NAME}:playback_FL" 2>/dev/null || true
    pw-link "$play" "${HX_NAME}:playback_FR" 2>/dev/null || true
  done
fi

echo "karaoke: fallback pw-loopback pid=$(cat "${XDG_RUNTIME_DIR}/rockola-karaoke-loopback.pid" 2>/dev/null || echo ?)"
pw-link -l 2>/dev/null | grep -iE "Logitech|HyperX|${TAG}|loopback" | head -40 || true
