#!/usr/bin/env python3
"""SSH helper for Rockola Pi. Usage: python scripts/_ssh_pi.py 'command'"""
from __future__ import annotations

import os
import sys

import paramiko

HOST = os.environ.get("ROCKOLA_PI_HOST", "192.168.1.244")
USER = os.environ.get("ROCKOLA_PI_USER", "saskweise")
PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")


def main() -> int:
    if not PASSWORD:
        print("Set ROCKOLA_PI_PASS", file=sys.stderr)
        return 2
    cmd = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "true"
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    try:
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=300, get_pty=True)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        if out:
            sys.stdout.write(out)
            if not out.endswith("\n"):
                sys.stdout.write("\n")
        if err:
            sys.stderr.write(err)
            if not err.endswith("\n"):
                sys.stderr.write("\n")
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
