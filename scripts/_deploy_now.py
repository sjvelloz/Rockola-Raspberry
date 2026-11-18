#!/usr/bin/env python3
"""Deploy latest Rockola fix to the Pi over SSH."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = os.environ.get("ROCKOLA_PI_HOST", "192.168.1.244")
USER = os.environ.get("ROCKOLA_PI_USER", "saskweise")
PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    try:
        remote = "/home/saskweise/Rockola-Raspberry/scripts/_remote_fix.sh"
        sftp = client.open_sftp()
        sftp.put(str(ROOT / "scripts" / "_remote_fix.sh"), remote)
        sftp.chmod(remote, 0o755)
        sftp.close()

        cmd = f"ROCKOLA_PI_PASS={PASSWORD!r} bash {remote}"
        print("Running remote fix…")
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        sys.stdout.write(out)
        if err:
            sys.stderr.write(err)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
