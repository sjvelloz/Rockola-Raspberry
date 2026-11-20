"""Deploy button polarity fix to Pi1 (.244 or legacy .150)."""
from __future__ import annotations

import os
import sys
import time

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
USER = "saskweise"
HOSTS = ["192.168.1.244", "192.168.1.150"]


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    for host in HOSTS:
        print("try", host)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(host, username=USER, password=PASSWORD, timeout=12)
        except Exception as exc:
            print(" fail", type(exc).__name__, exc)
            time.sleep(2)
            continue
        cmd = (
            "hostname; hostname -I; "
            "cd ~/Rockola-Raspberry && git fetch origin && "
            "git reset --hard origin/main && git log -1 --oneline; "
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
            "sleep 2; systemctl is-active jukebox; "
            "journalctl -u jukebox -n 8 --no-pager | tail -8"
        )
        _, stdout, stderr = client.exec_command(cmd, timeout=90)
        print(stdout.read().decode(errors="replace"))
        err = stderr.read().decode(errors="replace")
        if err.strip():
            print(err)
        client.close()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
