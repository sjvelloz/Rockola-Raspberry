#!/usr/bin/env bash
# Configura rockola-raspberry-2 igual que la 1, con IP estática .245
set -euo pipefail
PASS="${ROCKOLA_PI_PASS:-}"
STATIC_IP="192.168.1.245"
GATEWAY="192.168.1.1"
DNS="192.168.1.1"
REPO="https://github.com/sjvelloz/Rockola-Raspberry.git"
ROOT="/home/saskweise/Rockola-Raspberry"
USER_NAME="saskweise"

sudo_run() {
  if [ -n "$PASS" ]; then
    printf '%s\n' "$PASS" | sudo -S "$@"
  else
    sudo "$@"
  fi
}

echo "==> Host: $(hostname) / $(whoami)"
echo "==> IP actual: $(hostname -I)"

# --- IP estática (NetworkManager) ---
echo "==> Configurando IP estática ${STATIC_IP}…"
CON="$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | awk -F: '$2=="wlan0" || $2=="eth0" {print $1; exit}')"
IFACE="$(nmcli -t -f DEVICE con show --active 2>/dev/null | awk -F: '$1=="wlan0" || $1=="eth0" {print $1; exit}')"
IFACE="${IFACE:-wlan0}"
if [ -z "$CON" ]; then
  CON="$(nmcli -t -f NAME,DEVICE con show 2>/dev/null | awk -F: -v i="$IFACE" '$2==i {print $1; exit}')"
fi
echo "    connection=${CON:-?} iface=$IFACE"
nmcli -t -f NAME,DEVICE,TYPE con show --active 2>/dev/null || true

if [ -n "$CON" ]; then
  sudo_run nmcli con mod "$CON" ipv4.method manual \
    ipv4.addresses "${STATIC_IP}/24" \
    ipv4.gateway "$GATEWAY" \
    ipv4.dns "$DNS" \
    ipv4.ignore-auto-dns yes
  # Aplicar sin cortar SSH de golpe: reapply
  sudo_run nmcli con up "$CON" || true
else
  echo "AVISO: no se encontró conexión NM; creando perfil Rockola-static"
  sudo_run nmcli con add type wifi ifname wlan0 con-name Rockola-static \
    ipv4.method manual ipv4.addresses "${STATIC_IP}/24" \
    ipv4.gateway "$GATEWAY" ipv4.dns "$DNS" || true
fi

sleep 2
echo "    IP ahora: $(hostname -I)"
ip -4 addr show | grep -E 'inet ' || true

# --- Paquetes base ---
echo "==> Apt packages…"
export DEBIAN_FRONTEND=noninteractive
sudo_run apt-get update -qq
sudo_run apt-get install -y -qq \
  git python3-venv python3-pip \
  mpv chromium \
  wlr-randr \
  unclutter \
  || true

# --- Repo ---
echo "==> Clonar / actualizar Rockola…"
if [ -d "$ROOT/.git" ]; then
  git -C "$ROOT" fetch origin
  git -C "$ROOT" reset --hard origin/main
else
  rm -rf "$ROOT"
  git clone "$REPO" "$ROOT"
fi
cd "$ROOT"
git log -1 --oneline
chmod +x scripts/*.sh || true

# --- venv + deps ---
echo "==> venv…"
if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/pip install -U pip wheel -q
./venv/bin/pip install -r requirements.txt -q
./venv/bin/pip install RPi.GPIO -q || ./venv/bin/pip install rpi-lgpio -q || true
./venv/bin/python -m yt_dlp -U || true

# --- grupos ---
sudo_run usermod -aG gpio,video,audio,render "$USER_NAME" || true

# --- sudoers reboot ---
echo "$USER_NAME ALL=(ALL) NOPASSWD: /sbin/reboot" | sudo_run tee /etc/sudoers.d/rockola-reboot >/dev/null
sudo_run chmod 440 /etc/sudoers.d/rockola-reboot

# --- autostart (API + kiosk + linger + desktop login) ---
echo "==> install-autostart…"
# Cache sudo then run as user script (not sudo bash)
sudo_run -v
bash "$ROOT/scripts/install-autostart.sh"

# --- pantallas (si hay HDMI) ---
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DISPLAY="${DISPLAY:-:0}"
bash "$ROOT/scripts/configure-displays.sh" || true

# Asegurar rockola.env típico dual HDMI (como la Pi 1)
cat > "$ROOT/rockola.env" <<'EOF'
ROCKOLA_UI_OUTPUT=HDMI-A-1
ROCKOLA_VIDEO_OUTPUT=HDMI-A-2
ROCKOLA_VIDEO_GEOMETRY=1920x1080+1920+0
ROCKOLA_X11_SCREEN=1
ROCKOLA_MPV_VO=x11
ROCKOLA_MPV_FS_SCREEN=1
EOF

# Reaplicar unit con DISPLAY etc. desde el repo
TMP=$(mktemp)
cp "$ROOT/jukebox.service" "$TMP"
sudo_run cp "$TMP" /etc/systemd/system/jukebox.service
rm -f "$TMP"
sudo_run systemctl daemon-reload
sudo_run systemctl enable --now jukebox.service
sudo_run systemctl restart jukebox.service

sleep 4
echo
echo "======== RESUMEN ========"
echo "hostname: $(hostname)"
echo "IP:       $(hostname -I)"
echo "repo:     $(git -C "$ROOT" log -1 --oneline)"
echo "jukebox:  $(systemctl is-active jukebox.service) / $(systemctl is-enabled jukebox.service)"
curl -s http://127.0.0.1:8000/api/credits || echo "API no responde aún"
echo
echo "cat rockola.env:"
cat "$ROOT/rockola.env"
echo
echo "Listo. Esta Pi debe quedar en ${STATIC_IP}"
echo "Si SSH se cortó al cambiar IP, reconecta a ${STATIC_IP}"
