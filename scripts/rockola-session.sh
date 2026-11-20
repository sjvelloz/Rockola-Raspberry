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

# Cargar env si existe (valores con espacios van entre comillas)
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
cat > "${HOME}/.config/labwc/rc.xml" <<EOF
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="${TOUCH_DEV}" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.2)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.3)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.4)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<windowRules>
		<windowRule identifier="chromium*">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="Chromium*">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="org.chromium.Chromium">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="mpv" serverDecoration="no">
			<action name="MoveTo" x="1920" y="0"/>
		</windowRule>
	</windowRules>
</openbox_config>
EOF
labwc --reconfigure 2>/dev/null || true

# Audio: sink preferido (ROCKOLA_AUDIO_SINK=aux|hdmi) a tope
sleep 1
if command -v wpctl >/dev/null 2>&1; then
  wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0 2>/dev/null || true
  PREFER_AUDIO="$(echo "${ROCKOLA_AUDIO_SINK:-aux}" | tr '[:upper:]' '[:lower:]')"
  # Pi OS: jack = "Built-in Audio Stereo"; HDMI = "... (HDMI)"
  SINK_ID="$(wpctl status 2>/dev/null | awk -v prefer="$PREFER_AUDIO" '
    /vol:/ {
      line=$0
      low=tolower(line)
      is_hdmi = (low ~ /hdmi/)
      is_aux = (!is_hdmi) && (low ~ /headphone|analog|av jack|built-in audio stereo/)
      keep=0
      if (prefer=="hdmi" || prefer=="tv" || prefer=="1") keep=is_hdmi
      else if (prefer=="aux" || prefer=="headphones" || prefer=="analog" || prefer=="jack" || prefer=="3.5" || prefer=="headphone") keep=is_aux
      else keep=(index(low, prefer)>0)
      if (!keep) next
      gsub(/[^0-9. ]/," ",line); split(line,a," ");
      for (i in a) if (a[i] ~ /^[0-9]+$/) { print a[i]; exit }
    }
  ')"
  if [ -n "${SINK_ID:-}" ]; then
    wpctl set-default "$SINK_ID" 2>/dev/null || true
    wpctl set-volume "$SINK_ID" 1.0 2>/dev/null || true
    echo "Audio sink ($PREFER_AUDIO) → $SINK_ID"
  fi
fi

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
