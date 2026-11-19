"""Deploy LAN API bind (0.0.0.0) + latest code to both Pis; verify from outside."""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
USER = "saskweise"
HOSTS = ["192.168.1.245", "192.168.1.244"]


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors="replace") + stderr.read().decode(
        errors="replace"
    )


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1

    for host in HOSTS:
        print(f"=== {host} ===")
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(host, username=USER, password=PASSWORD, timeout=15)
        except Exception as exc:
            print(f"connect failed: {exc}")
            continue

        print(
            run(
                c,
                "cd ~/Rockola-Raspberry && git fetch origin && "
                "git reset --hard origin/main && git log -1 --oneline",
            )
        )
        print(
            run(
                c,
                f"printf '%s\\n' {PASSWORD!r} | sudo -S cp "
                "~/Rockola-Raspberry/jukebox.service /etc/systemd/system/jukebox.service; "
                f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl daemon-reload; "
                f"printf '%s\\n' {PASSWORD!r} | sudo -S systemctl restart jukebox; "
                "sleep 3; systemctl is-active jukebox; "
                "ss -lntp | grep 8000 || netstat -lntp 2>/dev/null | grep 8000 || true; "
                "curl -s --max-time 3 http://127.0.0.1:8000/api/credits; echo",
            )
        )
        c.close()

        # Test from this PC (LAN)
        url = f"http://{host}:8000/api/credits"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode()
                print(f"LAN OK {url} → {body}")
        except Exception as exc:
            print(f"LAN FAIL {url} → {exc}")

        try:
            req = urllib.request.Request(
                f"http://{host}:8000/api/player/pause",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"PAUSE OK → {resp.read().decode()[:120]}")
        except Exception as exc:
            print(f"PAUSE FAIL → {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
