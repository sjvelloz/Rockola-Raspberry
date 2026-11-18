#!/bin/bash
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0

# Descubrir nombre exacto del táctil
TOUCH_NAME="$(libinput list-devices 2>/dev/null | awk '
  /^Device:/ {name=substr($0,9); gsub(/^ +/,"",name)}
  /Capabilities:.*touch/ {print name; exit}
')"
# Fallback: cualquier QDtech
if [ -z "$TOUCH_NAME" ]; then
  TOUCH_NAME="$(libinput list-devices 2>/dev/null | awk '/^Device:.*QDtech/{print substr($0,9); exit}' | sed 's/^ *//')"
fi
echo "TOUCH_NAME=[$TOUCH_NAME]"

# UI = Mediatrix
UI_OUT="HDMI-A-2"
VIDEO_OUT="HDMI-A-1"
wlr-randr --output "$UI_OUT" --on --pos 0,0 --transform normal --scale 1
wlr-randr --output "$VIDEO_OUT" --on --pos 1920,0 --transform normal --scale 1

mkdir -p ~/.config/labwc
# labwc: deviceName exacto (el puerto USB cambia 1-1.1 / 1-1.2)
cat > ~/.config/labwc/rc.xml <<EOF
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
	<touch deviceName="${TOUCH_NAME}" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.1)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.2)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.3)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<touch deviceName="QDtech MPI1001 (USB 1-1.4)" mapToOutput="${UI_OUT}" mouseEmulation="yes"/>
	<windowRules>
		<windowRule identifier="chromium*">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="Chromium*">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="org.chromium.Chromium">
			<action name="MoveTo" x="0" y="0"/>
		</windowRule>
		<windowRule identifier="mpv" serverDecoration="no">
			<action name="MoveTo" x="1920" y="0"/>
		</windowRule>
	</windowRules>
</openbox_config>
EOF

# Guardar en rockola.env
cd ~/Rockola-Raspberry
grep -q '^ROCKOLA_TOUCH_DEVICE=' rockola.env 2>/dev/null && \
  sed -i "s|^ROCKOLA_TOUCH_DEVICE=.*|ROCKOLA_TOUCH_DEVICE=${TOUCH_NAME}|" rockola.env || \
  echo "ROCKOLA_TOUCH_DEVICE=${TOUCH_NAME}" >> rockola.env
grep -q '^ROCKOLA_UI_OUTPUT=' rockola.env && \
  sed -i "s|^ROCKOLA_UI_OUTPUT=.*|ROCKOLA_UI_OUTPUT=${UI_OUT}|" rockola.env || \
  echo "ROCKOLA_UI_OUTPUT=${UI_OUT}" >> rockola.env

labwc --reconfigure 2>/dev/null || killall -HUP labwc 2>/dev/null || true
sleep 1

# Reiniciar kiosk
pkill -f 'chromium.*rockola-chromium' 2>/dev/null || true
sleep 1
chmod +x scripts/start-kiosk.sh
sed -i 's/\r$//' scripts/start-kiosk.sh
bash scripts/start-kiosk.sh >/tmp/rockola-kiosk.log 2>&1 &
sleep 2

echo "=== rc touch lines ==="
grep touch ~/.config/labwc/rc.xml
echo "=== OK: toca esquina SUP-IZQ de la Mediatrix ==="
