#!/bin/bash
set -euo pipefail
PASS="${ROCKOLA_PI_PASS:-}"
ROOT=/home/saskweise/Rockola-Raspberry
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0

# Autostart sesión completa
mkdir -p ~/.config/labwc ~/.config/autostart
cat > ~/.config/labwc/autostart <<EOF
$ROOT/scripts/rockola-session.sh &
EOF
chmod +x ~/.config/labwc/autostart
cat > ~/.config/autostart/rockola-kiosk.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Rockola Kiosk
Exec=$ROOT/scripts/rockola-session.sh
X-GNOME-Autostart-enabled=true
Terminal=false
EOF

printf '%s\n' "$PASS" | sudo -S systemctl restart jukebox.service || true
sleep 4
pkill -f 'chromium.*rockola-chromium' 2>/dev/null || true
pkill -f rockola-session 2>/dev/null || true
sleep 1
nohup "$ROOT/scripts/rockola-session.sh" >/tmp/rockola-session.log 2>&1 &
for i in $(seq 1 40); do
  pgrep -f 'chromium.*rockola-chromium' >/dev/null && break
  sleep 1
done

echo "=== $(hostname) $(hostname -I) ==="
git -C "$ROOT" log -1 --oneline
grep COIN "$ROOT/rockola.env"
systemctl is-active jukebox
pgrep -af 'chromium.*8000' | head -1 || echo NO_CHROMIUM
curl -s http://127.0.0.1:8000/api/credits; echo
cat ~/.config/labwc/autostart
