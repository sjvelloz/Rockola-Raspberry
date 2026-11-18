#!/bin/bash
# Alinea rockola-raspberry-1 con IP estática .244 y el mismo software que la Pi2.
set -euo pipefail
PASS="${ROCKOLA_PI_PASS:-}"
STATIC_IP="192.168.1.244"
GATEWAY="192.168.1.1"
DNS="192.168.1.1"
ROOT=/home/saskweise/Rockola-Raspberry

sudo_run() {
  printf '%s\n' "$PASS" | sudo -S "$@"
}

echo "==> $(hostname) $(hostname -I)"

# IP estática
CON="$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | awk -F: '$2=="wlan0" || $2=="eth0" {print $1; exit}')"
echo "NM connection=$CON"
if [ -n "$CON" ]; then
  sudo_run nmcli con mod "$CON" ipv4.method manual \
    ipv4.addresses "${STATIC_IP}/24" \
    ipv4.gateway "$GATEWAY" \
    ipv4.dns "$DNS" \
    ipv4.ignore-auto-dns yes
  sudo_run nmcli con up "$CON" || true
fi
sleep 2
echo "IP ahora: $(hostname -I)"

# Repo + deps
cd "$ROOT" 2>/dev/null || { git clone https://github.com/sjvelloz/Rockola-Raspberry.git "$ROOT"; cd "$ROOT"; }
git fetch origin
git reset --hard origin/main
chmod +x scripts/*.sh
sed -i 's/\r$//' scripts/*.sh || true

if [ ! -d venv ]; then python3 -m venv venv; fi
./venv/bin/pip install -U pip wheel -q
./venv/bin/pip install -r requirements.txt -q
./venv/bin/pip install RPi.GPIO -q || ./venv/bin/pip install rpi-lgpio -q || true

sudo_run usermod -aG gpio,video,audio,render saskweise || true
B64="$(printf '%s\n' 'saskweise ALL=(ALL) NOPASSWD: /sbin/reboot' | base64 -w0)"
sudo_run bash -c "echo $B64 | base64 -d > /etc/sudoers.d/rockola-reboot && chmod 440 /etc/sudoers.d/rockola-reboot"

# Autostart sesión (como Pi2)
mkdir -p ~/.config/autostart ~/.config/labwc
cat > ~/.config/autostart/rockola-kiosk.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Rockola Kiosk
Exec=$ROOT/scripts/rockola-session.sh
X-GNOME-Autostart-enabled=true
Terminal=false
EOF
cat > ~/.config/labwc/autostart <<EOF
$ROOT/scripts/rockola-session.sh &
EOF
chmod +x ~/.config/labwc/autostart scripts/rockola-session.sh scripts/start-kiosk.sh

# Unit
sudo_run cp jukebox.service /etc/systemd/system/jukebox.service
sudo_run systemctl daemon-reload
sudo_run systemctl enable jukebox.service
sudo_run systemctl set-default graphical.target
sudo_run raspi-config nonint do_boot_behaviour B4 2>/dev/null || true

# Displays (sin tele también vale)
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 DISPLAY=:0
bash scripts/configure-displays.sh || true

# Asegurar créditos por ficha en env
grep -q '^ROCKOLA_COIN_CREDITS=' rockola.env 2>/dev/null && \
  sed -i 's/^ROCKOLA_COIN_CREDITS=.*/ROCKOLA_COIN_CREDITS=3/' rockola.env || \
  echo 'ROCKOLA_COIN_CREDITS=3' >> rockola.env

sudo_run systemctl restart jukebox.service
sleep 5

echo "======== Pi1 ========"
hostname
hostname -I
git log -1 --oneline
systemctl is-active jukebox.service
cat rockola.env
curl -s http://127.0.0.1:8000/api/credits; echo
echo "OK — IP objetivo ${STATIC_IP}"
