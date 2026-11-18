#!/bin/bash
set -euo pipefail
PASS="${ROCKOLA_PI_PASS:-}"
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0

# Volumen a tope
wpctl set-volume 45 1.0 || true
wpctl set-volume 54 1.0 || true
# Preferir HDMI (altavoces de la tele)
wpctl set-default 45 || true

# Soft-blank: tele ENCENDIDA (para audio HDMI) pero fondo negro
wlr-randr --output HDMI-A-1 --on --pos 1920,0 || true
wlr-randr --output HDMI-A-2 --on --pos 0,0 || true

if ! command -v swaybg >/dev/null 2>&1; then
  printf '%s\n' "$PASS" | sudo -S apt-get install -y -qq swaybg
fi
pkill -x swaybg 2>/dev/null || true
nohup swaybg -o HDMI-A-1 -c '#000000' >/tmp/swaybg.log 2>&1 &

# Persistir preferencias audio/blank suave
cd /home/saskweise/Rockola-Raspberry
grep -q ROCKOLA_BLANK_TV_WHEN_IDLE rockola.env 2>/dev/null && \
  sed -i 's/^ROCKOLA_BLANK_TV_WHEN_IDLE=.*/ROCKOLA_BLANK_TV_WHEN_IDLE=soft/' rockola.env || \
  echo 'ROCKOLA_BLANK_TV_WHEN_IDLE=soft' >> rockola.env
grep -q ROCKOLA_AUDIO_SINK rockola.env || echo 'ROCKOLA_AUDIO_SINK=hdmi' >> rockola.env

# Autostart swaybg negro en tele
mkdir -p ~/.config/labwc
if ! grep -Fq 'swaybg' ~/.config/labwc/autostart 2>/dev/null; then
  echo 'swaybg -o HDMI-A-1 -c "#000000" &' >> ~/.config/labwc/autostart
fi
# Volumen HDMI al login
if ! grep -Fq 'wpctl set-default' ~/.config/labwc/autostart 2>/dev/null; then
  cat >> ~/.config/labwc/autostart <<'EOF'
( sleep 2; wpctl set-volume @DEFAULT_AUDIO_SINK@ 100%; for s in $(wpctl status | awk '/Built-in Audio Digital Stereo \(HDMI\)/{print $1+0}'); do wpctl set-default $s; wpctl set-volume $s 1.0; done ) &
EOF
fi

printf '%s\n' "$PASS" | sudo -S systemctl restart jukebox.service
sleep 6

echo "=== audio ==="
wpctl get-volume @DEFAULT_AUDIO_SINK@
wpctl status | sed -n '/Sinks/,/Sources/p'
echo "=== layout ==="
wlr-randr | awk '/^[^ ]/ || /Enabled:/ || /Position:/ {print}'
echo "=== mpv ==="
pgrep -af 'mpv ' | head -2 || echo no-mpv
curl -s http://127.0.0.1:8000/api/queue; echo
