"""Restore AUX sink volume to 100% on Pi2."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    text = stdout.read().decode(errors="replace") + stderr.read().decode(
        errors="replace"
    )
    print(text)
    return text


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    run(
        c,
        "cd ~/Rockola-Raspberry && git fetch origin && "
        "git reset --hard origin/main && "
        "grep -n SINK_VOLUME config.py | head -3",
    )
    run(
        c,
        "if grep -q '^ROCKOLA_SINK_VOLUME=' ~/Rockola-Raspberry/rockola.env; then "
        "sed -i 's/^ROCKOLA_SINK_VOLUME=.*/ROCKOLA_SINK_VOLUME=1.0/' "
        "~/Rockola-Raspberry/rockola.env; "
        "else echo 'ROCKOLA_SINK_VOLUME=1.0' >> ~/Rockola-Raspberry/rockola.env; fi; "
        "grep -E 'AUDIO|SINK_VOLUME' ~/Rockola-Raspberry/rockola.env",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox",
    )
    run(
        c,
        r"""
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
wpctl set-volume @DEFAULT_AUDIO_SINK@ 1.0
SINKS="$(wpctl status | sed -n '/Sinks:/,/Sources:/p')"
ID="$(printf '%s\n' "$SINKS" | grep 'vol:' | grep -vi HDMI | head -1 | grep -oE '[0-9]+' | head -1)"
if [ -n "$ID" ]; then
  wpctl set-default "$ID"
  wpctl set-volume "$ID" 1.0
fi
echo "sink=$ID"
wpctl get-volume @DEFAULT_AUDIO_SINK@
wpctl status | sed -n '/Sinks:/,/Sources:/p'
""",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
