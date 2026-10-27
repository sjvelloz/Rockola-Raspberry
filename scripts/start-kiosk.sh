#!/usr/bin/env bash
# Chromium kiosk en la táctil (pantalla completa, escala 1:1).

set -euo pipefail

URL="${JUKEBOX_URL:-http://127.0.0.1:8000/}"
PROFILE="${HOME}/.config/rockola-chromium"

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

# Ocultar cursor si está instalado
command -v unclutter >/dev/null 2>&1 && unclutter -idle 0.2 -root &

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
