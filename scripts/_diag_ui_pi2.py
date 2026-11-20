"""Diagnose why UI changes are not visible on Pi2."""
from __future__ import annotations

import os
import sys

import paramiko

PASSWORD = os.environ.get("ROCKOLA_PI_PASS", "")
HOST = "192.168.1.245"
USER = "saskweise"


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    text = stdout.read().decode(errors="replace") + stderr.read().decode(
        errors="replace"
    )
    print(f"\n$ {cmd}\n{text}")
    return text


def main() -> int:
    if not PASSWORD:
        print("ROCKOLA_PI_PASS required", file=sys.stderr)
        return 1
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    run(c, "cd ~/Rockola-Raspberry && git log -1 --oneline && git status -sb")
    run(
        c,
        "grep -n clear-search-btn ~/Rockola-Raspberry/static/index.html; "
        "grep -n 'height<=720' ~/Rockola-Raspberry/youtube_service.py; "
        "grep -n enableTouchScroll ~/Rockola-Raspberry/static/js/app.js | head -3",
    )
    run(
        c,
        "systemctl is-active jukebox; "
        "systemctl show jukebox -p WorkingDirectory -p ExecStart -p FragmentPath --no-pager",
    )
    run(c, "ss -ltnp | grep -E ':8000|:8080|:80 ' || true")
    run(
        c,
        "curl -s http://127.0.0.1:8000/ | grep -n clear-search || echo NO_CLEAR_IN_ROOT; "
        "curl -sI http://127.0.0.1:8000/static/js/app.js | head -15; "
        "curl -s http://127.0.0.1:8000/static/js/app.js | grep -n clearSearchText | head -5 || echo NO_CLEAR_IN_JS",
    )
    run(c, "pgrep -af '/usr/lib/chromium/chromium' | head -8")
    run(c, "pgrep -af 'uvicorn|python.*main|jukebox' | head -10")
    run(
        c,
        "ls -la ~/Rockola-Raspberry/static/index.html "
        "~/Rockola-Raspberry/static/js/app.js; "
        "stat -c '%y %n' ~/Rockola-Raspberry/static/index.html "
        "~/Rockola-Raspberry/static/js/app.js",
    )
    # Check if Chromium uses a cached offline copy / different URL
    run(
        c,
        "tr '\\0' ' ' </proc/$(pgrep -n -f '/usr/lib/chromium/chromium .*--app=' || "
        "pgrep -n chromium)/cmdline 2>/dev/null | head -c 2000; echo",
    )
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
