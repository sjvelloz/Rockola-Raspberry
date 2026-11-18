#!/usr/bin/env python3
"""Upload and run a remote shell script on the Pi (streams output)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

HOST = os.environ.get("ROCKOLA_PI_HOST", "192.168.1.244")
USER = os.environ.get("ROCKOLA_PI_USER", "saskweise")
PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
TIMEOUT = int(os.environ.get("ROCKOLA_PI_TIMEOUT", "900"))


def main() -> int:
    if len(sys.argv) < 2 or not PASSWORD:
        print(
            "Usage: ROCKOLA_PI_PASS=... python scripts/_run_remote.py script.sh",
            file=sys.stderr,
        )
        return 2
    local = Path(sys.argv[1])
    text = local.read_text(encoding="utf-8").replace("\r\n", "\n")
    remote = f"/tmp/{local.name}"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    try:
        sftp = client.open_sftp()
        with sftp.file(remote, "w") as fh:
            fh.write(text)
        sftp.chmod(remote, 0o755)
        sftp.close()
        cmd = f"ROCKOLA_PI_PASS={PASSWORD!r} bash {remote}"
        transport = client.get_transport()
        assert transport is not None
        chan = transport.open_session()
        chan.settimeout(TIMEOUT)
        chan.exec_command(cmd)
        deadline = time.time() + TIMEOUT
        while True:
            if chan.recv_ready():
                sys.stdout.write(chan.recv(65535).decode(errors="replace"))
                sys.stdout.flush()
            if chan.recv_stderr_ready():
                sys.stderr.write(chan.recv_stderr(65535).decode(errors="replace"))
                sys.stderr.flush()
            if chan.exit_status_ready():
                while chan.recv_ready():
                    sys.stdout.write(chan.recv(65535).decode(errors="replace"))
                while chan.recv_stderr_ready():
                    sys.stderr.write(chan.recv_stderr(65535).decode(errors="replace"))
                return chan.recv_exit_status()
            if time.time() > deadline:
                print("\nTIMEOUT waiting for remote script", file=sys.stderr)
                return 124
            time.sleep(0.2)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
