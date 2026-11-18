#!/usr/bin/env bash
set -eu
PASS="${ROCKOLA_PI_PASS:-}"
ROOT=/home/saskweise/Rockola-Raspberry

sudo_run() {
  if [ -n "$PASS" ]; then printf '%s\n' "$PASS" | sudo -S "$@"; else sudo "$@"; fi
}

echo "=== host / ip ==="
hostname
hostname -I
ip -4 -br addr

echo "=== repo ==="
cd "$ROOT"
git fetch origin
git reset --hard origin/main
git log -1 --oneline

echo "=== venv / yt-dlp / mpv / chromium ==="
./venv/bin/python -c "import yt_dlp; print('yt-dlp', yt_dlp.version.__version__)"
command -v mpv; mpv --version | head -1
command -v chromium || command -v chromium-browser || echo NO_CHROMIUM
./venv/bin/python -c "import RPi.GPIO as G; print('RPi.GPIO OK')" 2>&1 || \
  ./venv/bin/python -c "import lgpio; print('lgpio OK')" 2>&1 || echo "NO_GPIO_LIB"

echo "=== service ==="
systemctl is-enabled jukebox.service
systemctl is-active jukebox.service
systemctl show jukebox.service -p User -p Environment --no-pager | tr ' ' '\n' | grep -E 'User=|XDG|DISPLAY|ROCKOLA|PULSE' || true
curl -s http://127.0.0.1:8000/api/credits; echo

echo "=== autostart ==="
ls -la ~/.config/autostart/ 2>/dev/null || true
grep -n start-kiosk ~/.config/labwc/autostart 2>/dev/null || echo "no labwc autostart line"
systemctl get-default
grep -E 'autologin-user' /etc/lightdm/lightdm.conf 2>/dev/null | grep -v '^#' || true

echo "=== sudoers reboot ==="
sudo_run cat /etc/sudoers.d/rockola-reboot 2>/dev/null || echo "MISSING sudoers"

echo "=== groups ==="
groups

echo "=== rockola.env / labwc ==="
cat "$ROOT/rockola.env" 2>/dev/null || echo missing-env
cat ~/.config/labwc/rc.xml 2>/dev/null || echo missing-rc

echo "=== displays ==="
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
wlr-randr 2>/dev/null | awk '/^[^ ]/ || /Position:/ || /Enabled:/ {print}' || echo "no wlr-randr session"

echo "=== chromium ==="
pgrep -af 'chromium.*8000' | head -2 || echo "no kiosk yet"

# Finish gaps if any
NEED_FIX=0
if ! systemctl is-enabled jukebox.service >/dev/null; then NEED_FIX=1; fi
if [ ! -f /etc/sudoers.d/rockola-reboot ]; then NEED_FIX=1; fi
if [ ! -f ~/.config/autostart/rockola-kiosk.desktop ]; then NEED_FIX=1; fi

if [ "$NEED_FIX" = 1 ]; then
  echo "==> Completando huecos…"
  sudo_run usermod -aG gpio,video,audio,render saskweise || true
  echo 'saskweise ALL=(ALL) NOPASSWD: /sbin/reboot' | sudo_run tee /etc/sudoers.d/rockola-reboot >/dev/null
  sudo_run chmod 440 /etc/sudoers.d/rockola-reboot
  sudo_run -v
  bash "$ROOT/scripts/install-autostart.sh" || true
  bash "$ROOT/scripts/configure-displays.sh" || true
  cat > "$ROOT/rockola.env" <<'EOF'
ROCKOLA_UI_OUTPUT=HDMI-A-1
ROCKOLA_VIDEO_OUTPUT=HDMI-A-2
ROCKOLA_VIDEO_GEOMETRY=1920x1080+1920+0
ROCKOLA_X11_SCREEN=1
ROCKOLA_MPV_VO=x11
ROCKOLA_MPV_FS_SCREEN=1
EOF
  sudo_run cp "$ROOT/jukebox.service" /etc/systemd/system/jukebox.service
  sudo_run systemctl daemon-reload
  sudo_run systemctl enable --now jukebox.service
  sudo_run systemctl restart jukebox.service
fi

# Ensure static IP still .245
CON="$(nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | awk -F: '$2=="wlan0" || $2=="eth0" {print $1; exit}')"
if [ -n "$CON" ]; then
  ADDR="$(nmcli -t -f IP4.ADDRESS con show "$CON" 2>/dev/null | head -1 | cut -d: -f2 | cut -d/ -f1)"
  echo "NM $CON -> $ADDR"
  if [ "$ADDR" != "192.168.1.245" ]; then
    echo "==> Reaplicando IP estática 192.168.1.245"
    sudo_run nmcli con mod "$CON" ipv4.method manual \
      ipv4.addresses 192.168.1.245/24 ipv4.gateway 192.168.1.1 \
      ipv4.dns 192.168.1.1 ipv4.ignore-auto-dns yes
    sudo_run nmcli con up "$CON" || true
  fi
fi

echo
echo "OK Pi2"
hostname -I
curl -s http://127.0.0.1:8000/api/credits; echo
