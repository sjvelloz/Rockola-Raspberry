#!/usr/bin/env bash
# Dual HDMI Rockola:
#   TELE (HP / HDMI-A-2)  → posición 0,0  (primaria: fullscreen de mpv/SDL cae aquí)
#   TÁCTIL (Mediatrix)    → posición 1920,0 + toque mapeado + Chromium
#
# Uso: bash ~/Rockola-Raspberry/scripts/configure-displays.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/rockola.env"
LABWC_RC="${HOME}/.config/labwc/rc.xml"

echo "==> Detectando salidas de vídeo…"
echo

mapfile -t OUTS < <(
  if command -v wlr-randr >/dev/null 2>&1; then
    echo "--- wlr-randr ---" >&2
    wlr-randr >&2 || true
    wlr-randr 2>/dev/null | awk '/^[^ ]/ && !/^$/ {print $1}'
  elif command -v xrandr >/dev/null 2>&1; then
    echo "--- xrandr ---" >&2
    xrandr --listmonitors >&2 || xrandr >&2
    xrandr --listmonitors 2>/dev/null | tail -n +2 | awk '{print $NF}'
  else
    echo "No hay wlr-randr ni xrandr." >&2
  fi
)

VIDEO_NAME=""
UI_NAME=""

# Preferencias conocidas de este hardware
for name in "${OUTS[@]}"; do
  up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
  echo "  found $name"
done

# UI = Mediatrix / DSI / HDMI-A-1
for name in "${OUTS[@]}"; do
  if [ "$name" = "HDMI-A-1" ]; then
    UI_NAME="$name"
    break
  fi
done
if [ -z "$UI_NAME" ]; then
  for name in "${OUTS[@]}"; do
    up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
    if echo "$up" | grep -qE 'DSI|DPI|PANEL'; then
      UI_NAME="$name"
      break
    fi
  done
fi

# Vídeo = otra HDMI (HP / HDMI-A-2)
for name in "${OUTS[@]}"; do
  [ "$name" = "$UI_NAME" ] && continue
  up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
  if echo "$up" | grep -qE 'HDMI|DP-'; then
    VIDEO_NAME="$name"
  fi
done

# Fallbacks
if [ -z "$VIDEO_NAME" ] && [ "${#OUTS[@]}" -ge 1 ]; then
  VIDEO_NAME="${OUTS[0]}"
fi
if [ -z "$UI_NAME" ] && [ "${#OUTS[@]}" -ge 2 ]; then
  for name in "${OUTS[@]}"; do
    if [ "$name" != "$VIDEO_NAME" ]; then
      UI_NAME="$name"
      break
    fi
  done
fi

VIDEO_NAME="${VIDEO_NAME:-HDMI-A-2}"
UI_NAME="${UI_NAME:-HDMI-A-1}"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

# CLAVE: tele en 0,0 (primaria). mpv/SDL fullscreen va a la primaria.
if command -v wlr-randr >/dev/null 2>&1; then
  echo "==> Layout: TELE($VIDEO_NAME)=0,0  UI($UI_NAME)=1920,0"
  wlr-randr --output "$VIDEO_NAME" --pos 0,0 2>/dev/null || true
  wlr-randr --output "$UI_NAME" --pos 1920,0 2>/dev/null || true
fi

cat > "$ENV_FILE" <<EOF
# Generado por configure-displays.sh — $(date -Iseconds)
# TELE en 0,0 (primaria) para que mpv fullscreen (vo/sdl) salga ahí.
ROCKOLA_VIDEO_OUTPUT=${VIDEO_NAME}
ROCKOLA_UI_OUTPUT=${UI_NAME}
ROCKOLA_MPV_FS_SCREEN=0
ROCKOLA_VIDEO_GEOMETRY=1920x1080+0+0
ROCKOLA_UI_GEOMETRY=1920x1080+1920+0
EOF

echo
echo "Escrito $ENV_FILE:"
cat "$ENV_FILE"

mkdir -p "$(dirname "$LABWC_RC")"
cat > "$LABWC_RC" <<EOF
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="QDtech MPI1001" mapToOutput="${UI_NAME}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="${UI_NAME}" mouseEmulation="yes"/>
	<windowRules>
		<!-- UI Chromium siempre en la táctil (derecha) -->
		<windowRule identifier="chromium*">
			<action name="MoveTo" x="1920" y="0"/>
		</windowRule>
		<windowRule identifier="Chromium*">
			<action name="MoveTo" x="1920" y="0"/>
		</windowRule>
		<windowRule identifier="org.chromium.Chromium">
			<action name="MoveTo" x="1920" y="0"/>
		</windowRule>
		<!-- mpv: tele primaria (0,0); por si acaso forzar MoveTo -->
		<windowRule identifier="mpv">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
	</windowRules>
</openbox_config>
EOF
echo "labwc rc → touch=${UI_NAME}, chromium@1920, mpv@0"
labwc --reconfigure 2>/dev/null || killall -HUP labwc 2>/dev/null || true

# Reiniciar kiosk en la táctil si está corriendo
if pgrep -f 'rockola-chromium|chromium.*8000' >/dev/null 2>&1; then
  echo "==> Reiniciando Chromium kiosk en la táctil…"
  pkill -f 'chromium.*rockola-chromium' 2>/dev/null || true
  sleep 1
  nohup "$ROOT/scripts/start-kiosk.sh" >/tmp/rockola-kiosk.log 2>&1 &
fi

echo
echo "Reinicia el backend:"
echo "  sudo systemctl restart jukebox.service"
