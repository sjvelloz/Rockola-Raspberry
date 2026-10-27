#!/usr/bin/env bash
# Lanza Chromium en modo kiosk contra la UI local del jukebox.
# Autostart: ~/.config/autostart/rockola-kiosk.desktop

set -euo pipefail

URL="${JUKEBOX_URL:-http://127.0.0.1:8000/}"
PROFILE="${HOME}/.config/rockola-chromium"

# Esperar a que el backend (jukebox.service) responda
for _ in $(seq 1 90); do
  if curl -sf "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

mkdir -p "$PROFILE"

# Evitar diálogo "¿Restaurar páginas?"
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' "$PROFILE/Default/Preferences" 2>/dev/null || true
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PROFILE/Default/Preferences" 2>/dev/null || true

# Bookworm puede tener "chromium" o "chromium-browser"
CHROME=""
if command -v chromium >/dev/null 2>&1; then
  CHROME="chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROME="chromium-browser"
else
  echo "No se encontró chromium. Instala: sudo apt install -y chromium" >&2
  exit 1
fi

exec "$CHROME" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  --overscroll-history-navigation=0 \
  --disable-features=TranslateUI \
  --user-data-dir="$PROFILE" \
  "$URL"
