#!/usr/bin/env bash
# Chromium kiosk en la táctil (pantalla completa, escala 1:1).
# Se puede lanzar desde SSH: adjunta la sesión gráfica local (labwc/X11).

set -euo pipefail

URL="${JUKEBOX_URL:-http://127.0.0.1:8000/}"
PROFILE="${HOME}/.config/rockola-chromium"
UID_NUM="$(id -u)"

# Si venimos por SSH sin DISPLAY, usar la sesión gráfica del usuario
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${UID_NUM}}"
  if [ -S "${XDG_RUNTIME_DIR}/wayland-0" ]; then
    export WAYLAND_DISPLAY=wayland-0
  elif [ -S "${XDG_RUNTIME_DIR}/wayland-1" ]; then
    export WAYLAND_DISPLAY=wayland-1
  elif [ -e /tmp/.X11-unix/X0 ]; then
    export DISPLAY=:0
  fi
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  echo "No hay sesión gráfica (ni DISPLAY ni WAYLAND_DISPLAY)." >&2
  echo "Activa Desktop Autologin: sudo raspi-config nonint do_boot_behaviour B4" >&2
  echo "Luego: sudo reboot" >&2
  exit 1
fi

# Esperar backend
for _ in $(seq 1 90); do
  if curl -sf "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

mkdir -p "$PROFILE"
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' "$PROFILE/Default/Preferences" 2>/dev/null || true
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PROFILE/Default/Preferences" 2>/dev/null || true

CHROME=""
if command -v chromium >/dev/null 2>&1; then
  CHROME="chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROME="chromium-browser"
else
  echo "Instala Chromium: sudo apt install -y chromium" >&2
  exit 1
fi

# Ocultar cursor (solo X11; en Wayland unclutter suele fallar — ignorar)
if [ -n "${DISPLAY:-}" ] && command -v unclutter >/dev/null 2>&1; then
  unclutter -idle 0.2 -root >/dev/null 2>&1 &
fi

# Flags pensados para Pi táctil: fullscreen real, sin zoom raro, más fluido
exec "$CHROME" \
  --kiosk \
  --start-fullscreen \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --disable-translate \
  --disable-features=TranslateUI,IsolateOrigins,site-per-process \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  --force-device-scale-factor=1 \
  --high-dpi-support=1 \
  --enable-gpu-rasterization \
  --ignore-gpu-blocklist \
  --num-raster-threads=2 \
  --user-data-dir="$PROFILE" \
  --app="$URL"
