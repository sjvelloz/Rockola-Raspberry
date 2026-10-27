#!/usr/bin/env bash
# Configura arranque automático: jukebox.service + Chromium kiosk.
# Ejecutar UNA vez en la Pi:
#   bash ~/Rockola-Raspberry/scripts/install-autostart.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
HOME_DIR="${HOME}"

echo "==> Proyecto: $ROOT"
echo "==> Usuario:  $USER_NAME"

chmod +x "$ROOT/scripts/start-kiosk.sh" "$ROOT/scripts/install-autostart.sh"

# --- Backend systemd ---
echo "==> Instalando jukebox.service…"
# Asegurar rutas del usuario actual en el unit
TMP_UNIT="$(mktemp)"
sed \
  -e "s|/home/saskweise/Rockola-Raspberry|$ROOT|g" \
  -e "s|/home/pi/Rockola-Raspberry|$ROOT|g" \
  -e "s|^User=.*|User=$USER_NAME|" \
  -e "s|^Group=.*|Group=$USER_NAME|" \
  -e "s|/home/saskweise/.config/mpv|$HOME_DIR/.config/mpv|" \
  -e "s|/home/pi/.config/mpv|$HOME_DIR/.config/mpv|" \
  "$ROOT/jukebox.service" > "$TMP_UNIT"

sudo cp "$TMP_UNIT" /etc/systemd/system/jukebox.service
rm -f "$TMP_UNIT"
sudo systemctl daemon-reload
sudo systemctl enable jukebox.service
sudo systemctl restart jukebox.service
echo "    jukebox.service: $(systemctl is-enabled jukebox.service) / $(systemctl is-active jukebox.service)"

# --- Desktop autostart (.desktop) ---
echo "==> Autostart Chromium (.desktop)…"
mkdir -p "$HOME_DIR/.config/autostart"
cat > "$HOME_DIR/.config/autostart/rockola-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Rockola Kiosk
Comment=Chromium pantalla completa — jukebox
Exec=$ROOT/scripts/start-kiosk.sh
X-GNOME-Autostart-enabled=true
Terminal=false
EOF

# --- labwc (Bookworm Wayland por defecto) ---
if [ -d "$HOME_DIR/.config/labwc" ] || true; then
  echo "==> Autostart labwc…"
  mkdir -p "$HOME_DIR/.config/labwc"
  AUTOSTART="$HOME_DIR/.config/labwc/autostart"
  LINE="$ROOT/scripts/start-kiosk.sh &"
  touch "$AUTOSTART"
  if ! grep -Fq "start-kiosk.sh" "$AUTOSTART" 2>/dev/null; then
    echo "$LINE" >> "$AUTOSTART"
    echo "    Añadido a $AUTOSTART"
  else
    echo "    Ya estaba en $AUTOSTART"
  fi
  chmod +x "$AUTOSTART" 2>/dev/null || true
fi

# --- wayfire (por si acaso) ---
if [ -f "$HOME_DIR/.config/wayfire.ini" ]; then
  echo "==> Detectado wayfire.ini (revisa [autostart] manualmente si hace falta)"
fi

# --- Pantallas (HDMI = vídeo) ---
echo "==> Configurando pantallas (tele HDMI)…"
chmod +x "$ROOT/scripts/configure-displays.sh" || true
if bash "$ROOT/scripts/configure-displays.sh"; then
  sudo systemctl restart jukebox.service || true
fi

echo
echo "Listo. Comprueba:"
echo "  curl -s http://127.0.0.1:8000/api/credits"
echo "  systemctl is-enabled jukebox.service"
echo "  cat $ROOT/rockola.env"
echo
echo "Para ver el kiosk ahora (sin reiniciar):"
echo "  $ROOT/scripts/start-kiosk.sh"
echo
echo "Luego: sudo reboot"
echo "Boot: Desktop + autologin ($USER_NAME)"
