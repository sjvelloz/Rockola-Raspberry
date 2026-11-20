"""Pull reboot-hold change and restart jukebox on both Pis."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
USER = "saskweise"
HOSTS = ("192.168.1.244", "192.168.1.245")


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
    for host in HOSTS:
        print(f"\n=== {host} ===")
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(host, username=USER, password=PASSWORD, timeout=15)
        except Exception as e:
            print(f"CONNECT_FAIL {e}")
            continue
        run(
            c,
            "cd ~/Rockola-Raspberry && git fetch origin && "
            "git reset --hard origin/main && "
            "grep -n REBOOT_HOLD_SECONDS config.py",
        )
        run(
            c,
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
            "sleep 2; systemctl is-active jukebox",
        )
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
