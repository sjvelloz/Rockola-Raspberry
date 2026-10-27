#!/usr/bin/env bash
# Dual HDMI Rockola:
#   TÁCTIL (Mediatrix / HDMI-A-1) → 0,0   (UI Chromium + toque)
#   TELE   (HP / HDMI-A-2)        → 1920,0 (vídeo mpv vía X11 screen N)
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
if command -v wlr-randr >/dev/null 2>&1; then
  wlr-randr || true
fi

UI_NAME="HDMI-A-1"
VIDEO_NAME="HDMI-A-2"

# Layout fijo: táctil izquierda, tele derecha
if command -v wlr-randr >/dev/null 2>&1; then
  wlr-randr --output "$UI_NAME" --on --pos 0,0 2>/dev/null || true
  wlr-randr --output "$VIDEO_NAME" --on --pos 1920,0 2>/dev/null || true
fi

# Índice X11 (xrandr --listmonitors) de la tele
X11_SCREEN="1"
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

GEO="1920x1080+1920+0"

cat > "$ENV_FILE" <<EOF
# Generado por configure-displays.sh — $(date -Iseconds)
ROCKOLA_UI_OUTPUT=${UI_NAME}
ROCKOLA_VIDEO_OUTPUT=${VIDEO_NAME}
ROCKOLA_VIDEO_GEOMETRY=${GEO}
ROCKOLA_X11_SCREEN=${X11_SCREEN}
ROCKOLA_MPV_VO=x11
ROCKOLA_MPV_FS_SCREEN=${X11_SCREEN}
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
		<windowRule identifier="chromium*">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="Chromium*">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="org.chromium.Chromium">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<!-- mpv X11: tele a la derecha; MoveTo antes de fullscreen -->
		<windowRule identifier="mpv" serverDecoration="no">
			<action name="MoveTo" x="1920" y="0"/>
		</windowRule>
	</windowRules>
</openbox_config>
EOF
labwc --reconfigure 2>/dev/null || killall -HUP labwc 2>/dev/null || true

echo
echo "Reinicia: sudo systemctl restart jukebox.service"
