#!/usr/bin/env bash
# Detecta pantallas y escribe rockola.env (HDMI = vídeo mpv, DSI/táctil = UI).
# Uso: bash ~/Rockola-Raspberry/scripts/configure-displays.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/rockola.env"

echo "==> Detectando salidas de vídeo…"
echo

HDMI_IDX=""
DSI_IDX=""
i=0

if command -v wlr-randr >/dev/null 2>&1; then
  echo "--- wlr-randr ---"
  wlr-randr || true
  # Parsear nombres de salida (líneas sin indentar)
  while IFS= read -r name; do
    up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
    echo "  [$i] $name"
    if echo "$up" | grep -qE 'HDMI|DP-'; then
      HDMI_IDX="$i"
    fi
    if echo "$up" | grep -qE 'DSI|DPI|PANEL|TOUCH|LCD|WIDE'; then
      DSI_IDX="$i"
    fi
    i=$((i + 1))
  done < <(wlr-randr 2>/dev/null | awk '/^[^ ]/ && !/^$/ {print $1}')
elif command -v xrandr >/dev/null 2>&1; then
  echo "--- xrandr ---"
  xrandr --listmonitors || xrandr
  while IFS= read -r line; do
    name="$(echo "$line" | awk '{print $NF}')"
    up="$(echo "$name" | tr '[:lower:]' '[:upper:]')"
    echo "  [$i] $name"
    if echo "$up" | grep -qE 'HDMI|DP-'; then
      HDMI_IDX="$i"
    fi
    if echo "$up" | grep -qE 'DSI|DPI|PANEL'; then
      DSI_IDX="$i"
    fi
    i=$((i + 1))
  done < <(xrandr --listmonitors 2>/dev/null | tail -n +2)
else
  echo "No hay wlr-randr ni xrandr. Instala: sudo apt install -y wlr-randr"
fi

# Fallback: si hay 2+ pantallas y no detectamos HDMI, usar la última (suele ser HDMI)
if [ -z "${HDMI_IDX}" ] && [ "$i" -ge 2 ]; then
  HDMI_IDX=$((i - 1))
  echo "Aviso: no se identificó HDMI por nombre; usando índice $HDMI_IDX"
fi

if [ -z "${HDMI_IDX}" ]; then
  HDMI_IDX=0
  echo "Aviso: solo se ve una pantalla o ninguna. mpv usará pantalla 0."
  echo "        Conecta la tele por micro-HDMI y vuelve a ejecutar este script."
fi

cat > "$ENV_FILE" <<EOF
# Generado por configure-displays.sh — $(date -Iseconds)
# Pantalla del VÍDEO (tele / HDMI) para mpv fullscreen
ROCKOLA_MPV_FS_SCREEN=${HDMI_IDX}
# UI Chromium en la táctil (DSI). Índice informativo: ${DSI_IDX:-?}
EOF

echo
echo "Escrito $ENV_FILE:"
cat "$ENV_FILE"
echo
echo "Reinicia el backend:"
echo "  sudo systemctl restart jukebox.service"
