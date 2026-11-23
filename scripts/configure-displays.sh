#!/usr/bin/env bash
# Dual HDMI Rockola — detecta por nombre EDID:
#   UI  = Mediatrix / MPI / QDtech / DSI  (táctil + Chromium)
#   VIDEO = HP / Samsung / resto HDMI     (solo vídeo mpv; apagada en IDLE)
#
# Uso: bash ~/Rockola-Raspberry/scripts/configure-displays.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/rockola.env"
LABWC_RC="${HOME}/.config/labwc/rc.xml"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DISPLAY="${DISPLAY:-:0}"

echo "==> Detectando salidas…"
if ! command -v wlr-randr >/dev/null 2>&1; then
  echo "Falta wlr-randr" >&2
  exit 1
fi
wlr-randr || true

mapfile -t OUTS < <(wlr-randr 2>/dev/null | awk '/^[^ ]/ && !/^$/ {print $1}')

UI_NAME=""
VIDEO_NAME=""

is_touch() {
  local name="$1"
  wlr-randr 2>/dev/null | awk -v n="$name" '
    $0 ~ "^"n" " {p=1; next}
    p && /^[^ ]/ {exit}
    p && /Mediatrix|MPI|QDtech|touch|DSI|DPI/ {found=1}
    END {exit !found}
  '
}

is_tv() {
  local name="$1"
  wlr-randr 2>/dev/null | awk -v n="$name" '
    $0 ~ "^"n" " {p=1; next}
    p && /^[^ ]/ {exit}
    p && /Samsung|HP Inc|LG Electronics|Sony|Philips|TCL|Hisense|TV/ {found=1}
    END {exit !found}
  '
}

for name in "${OUTS[@]}"; do
  if is_touch "$name"; then
    UI_NAME="$name"
  elif is_tv "$name"; then
    VIDEO_NAME="$name"
  fi
done

# Fallbacks por nombre de conector si EDID no matchea
if [ -z "$UI_NAME" ]; then
  for name in "${OUTS[@]}"; do
    case "$name" in
      HDMI-A-1|DSI-1|DSI-2) UI_NAME="$name"; break ;;
    esac
  done
fi
if [ -z "$VIDEO_NAME" ]; then
  for name in "${OUTS[@]}"; do
    [ "$name" = "${UI_NAME:-}" ] && continue
    case "$name" in
      HDMI-A-*|HDMI-B-*|DP-*) VIDEO_NAME="$name"; break ;;
    esac
  done
fi

# Una sola pantalla: es UI (no apagarla); avisar
if [ -z "$VIDEO_NAME" ] && [ -n "$UI_NAME" ]; then
  echo "AVISO: solo hay una salida ($UI_NAME). La tele no está detectada."
elif [ -z "$UI_NAME" ] && [ -n "$VIDEO_NAME" ]; then
  echo "AVISO: solo se ve la TELE ($VIDEO_NAME). Enchufa la táctil para la UI."
  # No usar la tele como UI permanente: dejamos UI vacío y VIDEO marcado
  UI_NAME=""
fi

UI_NAME="${UI_NAME:-}"
VIDEO_NAME="${VIDEO_NAME:-}"

echo "UI=$UI_NAME  VIDEO=$VIDEO_NAME"

# Layout: táctil 0,0 ; tele 1920,0 (si existen)
if [ -n "$UI_NAME" ]; then
  wlr-randr --output "$UI_NAME" --on --pos 0,0 2>/dev/null || true
fi
if [ -n "$VIDEO_NAME" ] && [ "$VIDEO_NAME" != "$UI_NAME" ]; then
  # Por defecto APAGADA en idle (solo se enciende al reproducir)
  wlr-randr --output "$VIDEO_NAME" --off 2>/dev/null || true
fi

# Índice X11 de la tele (con ella encendida un momento para medir)
X11_SCREEN="1"
GEO="1920x1080+1920+0"
if [ -n "$VIDEO_NAME" ] && [ "$VIDEO_NAME" != "$UI_NAME" ]; then
  wlr-randr --output "$VIDEO_NAME" --on --mode 1920x1080 --pos 1920,0 2>/dev/null || \
    wlr-randr --output "$VIDEO_NAME" --on --pos 1920,0 2>/dev/null || true
  sleep 1
  if command -v xrandr >/dev/null 2>&1; then
    echo "--- xrandr monitors ---"
    xrandr --listmonitors || true
    idx="$(xrandr --listmonitors 2>/dev/null | awk -v n="$VIDEO_NAME" '
      NR>1 {
        mon=$NF
        gsub(/^\+/,"",mon)
        if (mon==n) { print $1; exit }
      }' | tr -d ':')"
    if [ -n "${idx}" ]; then
      X11_SCREEN="$idx"
    fi
  fi
  # Volver a apagar tele (idle)
  wlr-randr --output "$VIDEO_NAME" --off 2>/dev/null || true
fi

cat > "$ENV_FILE" <<EOF
# Generado por configure-displays.sh — $(date -Iseconds)
ROCKOLA_UI_OUTPUT=${UI_NAME}
ROCKOLA_VIDEO_OUTPUT=${VIDEO_NAME}
ROCKOLA_VIDEO_GEOMETRY=${GEO}
ROCKOLA_X11_SCREEN=${X11_SCREEN}
ROCKOLA_MPV_VO=x11
ROCKOLA_MPV_FS_SCREEN=${X11_SCREEN}
# soft = tele ON con fondo negro; hard = apaga la salida
ROCKOLA_BLANK_TV_WHEN_IDLE=soft
# aux = jack 3.5 mm; hdmi = audio por la tele
ROCKOLA_AUDIO_SINK=hyperx
EOF

echo
echo "Escrito $ENV_FILE:"
cat "$ENV_FILE"

mkdir -p "$(dirname "$LABWC_RC")"
TOUCH_OUT="${UI_NAME:-HDMI-A-1}"
MPV_X=1920
if [ -z "$UI_NAME" ] || [ "$UI_NAME" = "$VIDEO_NAME" ]; then
  MPV_X=0
fi
# Nombre exacto del táctil (cambia con el puerto USB: 1-1.1, 1-1.2, …)
TOUCH_DEV="$(libinput list-devices 2>/dev/null | awk '
  /^Device:/ {name=substr($0,9); gsub(/^ +/,"",name)}
  /Capabilities:.*touch/ {print name; exit}
')"
TOUCH_DEV="${TOUCH_DEV:-QDtech MPI1001}"
cat > "$LABWC_RC" <<EOF
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="${TOUCH_DEV}" mapToOutput="${TOUCH_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001" mapToOutput="${TOUCH_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="${TOUCH_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.2)" mapToOutput="${TOUCH_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.3)" mapToOutput="${TOUCH_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.4)" mapToOutput="${TOUCH_OUT}" mouseEmulation="yes"/>
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
			<action name="MoveTo" x="${MPV_X}" y="0"/>
		</windowRule>
	</windowRules>
</openbox_config>
EOF
labwc --reconfigure 2>/dev/null || killall -HUP labwc 2>/dev/null || true
echo "Táctil '${TOUCH_DEV}' → ${TOUCH_OUT}"

echo
echo "Reinicia: sudo systemctl restart jukebox.service"
