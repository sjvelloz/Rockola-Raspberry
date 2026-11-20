from __future__ import annotations

import os
import sys
import time

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
        "git reset --hard origin/main && git log -1 --oneline && "
        "grep 'height<=720' youtube_service.py",
    )
    run(
        c,
        f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
        "sleep 2; systemctl is-active jukebox",
    )
    run(c, "nohup /home/saskweise/kiosk-hard.sh >/dev/null 2>&1 & echo relaunched")
    time.sleep(8)
    run(
        c,
        "pgrep -f '/usr/lib/chromium/chromium .*--app=http' >/dev/null "
        "&& echo CHROMIUM_UP || echo CHROMIUM_DOWN; "
        "tail -20 /tmp/kiosk-hard.log",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
