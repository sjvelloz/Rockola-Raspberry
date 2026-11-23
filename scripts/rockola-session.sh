#!/usr/bin/env bash
# Arranque de sesión gráfica Rockola (labwc autostart).
# Orden: layout → táctil → audio → fondo tele → esperar API → Chromium kiosk.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DISPLAY="${DISPLAY:-:0}"
LOG=/tmp/rockola-session.log
exec >>"$LOG" 2>&1
echo "=== rockola-session $(date -Iseconds) ==="

# Cargar env si existe (acepta valores con o sin comillas)
if [ -f "$ROOT/rockola.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in
      ''|\#*) continue ;;
      *=*)
        key="${line%%=*}"
        val="${line#*=}"
        case "$key" in
          *[!A-Z0-9_]*) continue ;;
        esac
        # Quitar comillas envolventes si las hay
        case "$val" in
          \"*\") val="${val#\"}"; val="${val%\"}" ;;
          \'*\') val="${val#\'}"; val="${val%\'}" ;;
        esac
        export "$key=$val"
        ;;
    esac
  done < "$ROOT/rockola.env"
fi

UI_OUT="${ROCKOLA_UI_OUTPUT:-HDMI-A-2}"
VIDEO_OUT="${ROCKOLA_VIDEO_OUTPUT:-HDMI-A-1}"

# Esperar compositor
for _ in $(seq 1 30); do
  if [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ] || [ -S "${XDG_RUNTIME_DIR}/wayland-0" ]; then
    break
  fi
  sleep 1
done
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

# Layout: táctil 0,0 / tele 1920,0
if command -v wlr-randr >/dev/null 2>&1; then
  wlr-randr --output "$UI_OUT" --on --pos 0,0 --transform normal --scale 1 2>/dev/null || true
  if [ -n "$VIDEO_OUT" ] && [ "$VIDEO_OUT" != "$UI_OUT" ]; then
    wlr-randr --output "$VIDEO_OUT" --on --pos 1920,0 --transform normal --scale 1 2>/dev/null || true
  fi
fi

# Táctil → salida UI (nombre exacto del dispositivo)
TOUCH_DEV="${ROCKOLA_TOUCH_DEVICE:-}"
if [ -z "$TOUCH_DEV" ] && command -v libinput >/dev/null 2>&1; then
  TOUCH_DEV="$(libinput list-devices 2>/dev/null | awk '
    /^Device:/ {name=substr($0,9); gsub(/^ +/,"",name)}
    /Capabilities:.*touch/ {print name; exit}
  ')"
fi
TOUCH_DEV="${TOUCH_DEV:-QDtech MPI1001}"
mkdir -p "${HOME}/.config/labwc"
# Solo mapeo táctil (sin windowRules: en labwc nuevo dan "Config errors detected")
cat > "${HOME}/.config/labwc/rc.xml" <<EOF
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="${TOUCH_DEV}" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.2)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.3)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.4)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
</openbox_config>
EOF
if [ -n "${LABWC_PID:-}" ] || LABWC_PID="$(pgrep -n labwc 2>/dev/null || true)"; then
  export LABWC_PID
  labwc --reconfigure 2>/dev/null || true
fi
echo "Touch '${TOUCH_DEV}' → ${UI_OUT}"

# Audio: sink preferido (ROCKOLA_AUDIO_SINK=hyperx|aux|hdmi). Karaoke OFF por defecto.
sleep 1
if command -v wpctl >/dev/null 2>&1; then
  SINK_VOL="${ROCKOLA_SINK_VOLUME:-1.0}"
  wpctl set-volume @DEFAULT_AUDIO_SINK@ "$SINK_VOL" 2>/dev/null || true
  PREFER_AUDIO="$(echo "${ROCKOLA_AUDIO_SINK:-hyperx}" | tr '[:upper:]' '[:lower:]')"
  SINKS_BLOCK="$(wpctl status 2>/dev/null | sed -n '/Audio/,/Video/p' | sed -n '/Sinks:/,/Sources:/p')"
  case "$PREFER_AUDIO" in
    hdmi|tv|1)
      SINK_ID="$(printf '%s\n' "$SINKS_BLOCK" | grep 'vol:' | grep -i HDMI | head -1 | grep -oE '[0-9]+' | head -1)"
      ;;
    hyperx|usb|card|sound|kingston)
      SINK_ID="$(printf '%s\n' "$SINKS_BLOCK" | grep 'vol:' | grep -iE 'HyperX|Kingston' | head -1 | grep -oE '[0-9]+' | head -1)"
      ;;
    aux|headphones|analog|jack|3.5|headphone)
      SINK_ID="$(printf '%s\n' "$SINKS_BLOCK" | grep 'vol:' | grep -viE 'HDMI|HyperX|Logitech' | grep -iE 'Headphones|bcm2835|mailbox|Built-in Audio Stereo' | head -1 | grep -oE '[0-9]+' | head -1)"
      if [ -z "${SINK_ID:-}" ]; then
        SINK_ID="$(printf '%s\n' "$SINKS_BLOCK" | grep 'vol:' | grep -viE 'HDMI|HyperX|Logitech' | head -1 | grep -oE '[0-9]+' | head -1)"
      fi
      ;;
    *)
      SINK_ID="$(printf '%s\n' "$SINKS_BLOCK" | grep 'vol:' | grep -i "$PREFER_AUDIO" | head -1 | grep -oE '[0-9]+' | head -1)"
      ;;
  esac
  if [ -n "${SINK_ID:-}" ]; then
    wpctl set-default "$SINK_ID" 2>/dev/null || true
    wpctl set-volume "$SINK_ID" "$SINK_VOL" 2>/dev/null || true
    echo "Audio sink ($PREFER_AUDIO) → $SINK_ID vol=$SINK_VOL"
  fi
fi

# Karaoke desactivado al arrancar (música limpia). Se activa desde la UI.
pkill -f 'pw-loopback.*rockola-karaoke' 2>/dev/null || true
rm -f "${XDG_RUNTIME_DIR}/rockola-karaoke-loopback.pid" 2>/dev/null || true
pw-metadata -n settings 0 clock.force-quantum 0 2>/dev/null || true
pw-metadata -n settings 0 clock.quantum 1024 2>/dev/null || true
amixer -c 3 sset PCM 70 unmute 2>/dev/null || true
echo "Karaoke OFF (activar en pantalla)"

# Fondo negro SOLO en la tele
pkill -x swaybg 2>/dev/null || true
if [ -n "$VIDEO_OUT" ] && [ "$VIDEO_OUT" != "$UI_OUT" ] && command -v swaybg >/dev/null 2>&1; then
  swaybg -o "$VIDEO_OUT" -c '#000000' &
fi

# Esperar backend jukebox
URL="${JUKEBOX_URL:-http://127.0.0.1:8000/}"
for _ in $(seq 1 90); do
  if curl -sf "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Un solo Chromium kiosk
pkill -f 'chromium.*rockola-chromium' 2>/dev/null || true
sleep 1
chmod +x "$ROOT/scripts/start-kiosk.sh" 2>/dev/null || true
sed -i 's/\r$//' "$ROOT/scripts/start-kiosk.sh" 2>/dev/null || true
export ROCKOLA_UI_POSITION=0,0
exec "$ROOT/scripts/start-kiosk.sh"
