"""Set Rockola 2 audio to 3.5mm aux and restart services."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors="replace") + stderr.read().decode(
        errors="replace"
    )


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    print(
        run(
            c,
            "cd ~/Rockola-Raspberry && git fetch origin && "
            "git reset --hard origin/main && git log -1 --oneline && "
            "chmod +x scripts/rockola-session.sh scripts/start-kiosk.sh",
        )
    )

    # Persist aux in rockola.env
    print(
        run(
            c,
            r"""
cd ~/Rockola-Raspberry
touch rockola.env
if grep -q '^ROCKOLA_AUDIO_SINK=' rockola.env; then
  sed -i 's/^ROCKOLA_AUDIO_SINK=.*/ROCKOLA_AUDIO_SINK=aux/' rockola.env
else
  echo 'ROCKOLA_AUDIO_SINK=aux' >> rockola.env
fi
grep ROCKOLA_AUDIO_SINK rockola.env
""",
        )
    )

    # Switch sink now in the graphical session
    print(
        run(
            c,
            r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
echo '=== sinks before ==='
wpctl status | sed -n '/Sinks/,/Sources/p'
SINK_ID=$(wpctl status | awk '
  /vol:/ {
    line=$0
    low=tolower(line)
    is_hdmi = (low ~ /hdmi/)
    is_aux = (!is_hdmi) && (low ~ /headphone|analog|av jack|built-in audio stereo/)
    if (!is_aux) next
    gsub(/[^0-9. ]/," ",line); split(line,a," ");
    for (i in a) if (a[i] ~ /^[0-9]+$/) { print a[i]; exit }
  }
')
echo "aux_sink=$SINK_ID"
if [ -n "$SINK_ID" ]; then
  wpctl set-default "$SINK_ID"
  wpctl set-volume "$SINK_ID" 1.0
  echo "OK default → aux $SINK_ID"
else
  echo 'WARN: no analog/headphones sink found'
fi
echo '=== sinks after ==='
wpctl status | sed -n '/Sinks/,/Sources/p'
wpctl get-volume @DEFAULT_AUDIO_SINK@
""",
        )
    )

    print(
        run(
            c,
            f"printf '%s\\n' {PASSWORD!r} | sudo -S cp "
            "~/Rockola-Raspberry/jukebox.service /etc/systemd/system/jukebox.service; "
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl daemon-reload; "
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
            "sleep 3; systemctl is-active jukebox",
        )
    )
    c.close()
    print("DONE aux on Pi2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
