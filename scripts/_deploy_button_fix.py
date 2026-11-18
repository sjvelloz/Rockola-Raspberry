"""Pull latest on both Pis and restart jukebox. Needs ROCKOLA_PI_PASS."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOSTS = ["192.168.1.244", "192.168.1.245"]
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 90) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return out + err


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    for host in HOSTS:
        print(f"=== {host} ===")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(host, username=USER, password=PASSWORD, timeout=15)
        except Exception as exc:
            print(f"connect failed: {exc}")
            continue
        print(
            run(
                client,
                "cd ~/Rockola-Raspberry && git fetch origin && "
                "git reset --hard origin/main && git log -1 --oneline",
            )
        )
        restart = (
            f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox.service; "
            "sleep 2; systemctl is-active jukebox; "
            "journalctl -u jukebox -n 12 --no-pager | tail -12"
        )
        print(run(client, restart))
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
