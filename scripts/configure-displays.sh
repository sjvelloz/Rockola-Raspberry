#!/usr/bin/env bash
# Detecta pantallas y escribe rockola.env + mapeo táctil labwc.
# Dual HDMI típico Rockola:
#   HDMI-A-1 Mediatrix/MPI = táctil UI
#   HDMI-A-2 HP/tele       = vídeo mpv
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
    echo "No hay wlr-randr ni xrandr. Instala: sudo apt install -y wlr-randr" >&2
  fi
)

VIDEO_IDX=""
UI_IDX=""
VIDEO_NAME=""
UI_NAME=""

for i in "${!OUTS[@]}"; do
  name="${OUTS[$i]}"
  up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
  echo "  [$i] $name"

  # Táctil Mediatrix / DSI / panel pequeño
  if echo "$up" | grep -qE 'DSI|DPI|PANEL' \
    || wlr-randr 2>/dev/null | awk -v n="$name" '
        $0 ~ "^"n" " {p=1; next}
        p && /^[^ ]/ {exit}
        p && /Mediatrix|MPI|QDtech|touch/ {found=1}
        END {exit !found}
      '; then
    UI_IDX="$i"
    UI_NAME="$name"
  fi
done

# Si no detectamos táctil por modelo, HDMI-A-1 suele ser la Mediatrix en esta Pi
if [ -z "${UI_NAME}" ]; then
  for i in "${!OUTS[@]}"; do
    if [ "${OUTS[$i]}" = "HDMI-A-1" ]; then
      UI_IDX="$i"
      UI_NAME="${OUTS[$i]}"
      break
    fi
  done
fi

# Vídeo = otra salida HDMI (preferir A-2 / última HDMI distinta de UI)
for i in "${!OUTS[@]}"; do
  name="${OUTS[$i]}"
  up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
  if [ "$name" = "${UI_NAME:-}" ]; then
    continue
  fi
  if echo "$up" | grep -qE 'HDMI|DP-'; then
    VIDEO_IDX="$i"
    VIDEO_NAME="$name"
  fi
done

if [ -z "${VIDEO_IDX}" ] && [ "${#OUTS[@]}" -ge 1 ]; then
  # Una sola pantalla o fallback
  if [ -n "${UI_IDX}" ] && [ "${#OUTS[@]}" -ge 2 ]; then
    for i in "${!OUTS[@]}"; do
      if [ "$i" != "$UI_IDX" ]; then
        VIDEO_IDX="$i"
        VIDEO_NAME="${OUTS[$i]}"
        break
      fi
    done
  else
    VIDEO_IDX=0
    VIDEO_NAME="${OUTS[0]:-}"
  fi
fi

if [ -z "${VIDEO_IDX}" ]; then
  VIDEO_IDX=0
  echo "Aviso: solo se ve una pantalla. mpv usará pantalla 0."
fi

cat > "$ENV_FILE" <<EOF
# Generado por configure-displays.sh — $(date -Iseconds)
# Pantalla del VÍDEO (tele) para mpv fullscreen
ROCKOLA_MPV_FS_SCREEN=${VIDEO_IDX}
ROCKOLA_VIDEO_OUTPUT=${VIDEO_NAME:-}
ROCKOLA_UI_OUTPUT=${UI_NAME:-}
EOF

echo
echo "Escrito $ENV_FILE:"
cat "$ENV_FILE"

# Mapear táctil USB a la salida UI (evita que el toque mueva el cursor en la tele)
if [ -n "${UI_NAME}" ]; then
  mkdir -p "$(dirname "$LABWC_RC")"
  cat > "$LABWC_RC" <<EOF
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="QDtech MPI1001" mapToOutput="${UI_NAME}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="${UI_NAME}" mouseEmulation="yes"/>
</openbox_config>
EOF
  echo
  echo "Táctil mapeado a ${UI_NAME} en $LABWC_RC"
  # Colocar UI a la izquierda, tele a la derecha
  if command -v wlr-randr >/dev/null 2>&1; then
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    wlr-randr --output "$UI_NAME" --pos 0,0 2>/dev/null || true
    if [ -n "${VIDEO_NAME}" ] && [ "$VIDEO_NAME" != "$UI_NAME" ]; then
      wlr-randr --output "$VIDEO_NAME" --pos 1920,0 2>/dev/null || true
    fi
  fi
  labwc --reconfigure 2>/dev/null || killall -HUP labwc 2>/dev/null || true
fi

echo
echo "Reinicia el backend:"
echo "  sudo systemctl restart jukebox.service"
