"""Launch Chromium with CDP on Pi2 and dump search-row DOM state."""
from __future__ import annotations

import os
import sys
import textwrap

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

    py = textwrap.dedent(
        r"""
        import json, urllib.request, asyncio, subprocess, sys
        try:
            import websockets
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "websockets"])
            import websockets

        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
        page = next((t for t in tabs if t.get("type") == "page" and "8000" in t.get("url", "")), None)
        if page is None and tabs:
            page = next((t for t in tabs if t.get("type") == "page"), tabs[0])
        print("TAB", page.get("url"), page.get("webSocketDebuggerUrl"))

        expr = r'''(() => {
          const btn = document.getElementById("clear-search-btn");
          const wrap = document.querySelector(".search-wrap");
          return {
            hasBtn: !!btn,
            btnText: btn ? btn.textContent : null,
            btnDisplay: btn ? getComputedStyle(btn).display : null,
            btnVisibility: btn ? getComputedStyle(btn).visibility : null,
            btnRect: btn ? {
              x: btn.getBoundingClientRect().x,
              y: btn.getBoundingClientRect().y,
              w: btn.getBoundingClientRect().width,
              h: btn.getBoundingClientRect().height
            } : null,
            wrapHTML: wrap ? wrap.outerHTML.slice(0, 1000) : "NO_WRAP",
            bodyStart: document.body.innerHTML.slice(0, 500),
            cssHref: [...document.querySelectorAll("link[rel=stylesheet]")].map(l => l.href),
            jsSrc: [...document.scripts].map(s => s.src),
          };
        })()'''

        async def main():
            async with websockets.connect(page["webSocketDebuggerUrl"]) as ws:
                await ws.send(json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True},
                }))
                while True:
                    raw = json.loads(await ws.recv())
                    if raw.get("id") == 1:
                        print(json.dumps(raw.get("result", {}).get("result", {}).get("value"), indent=2, ensure_ascii=False))
                        break

        asyncio.get_event_loop().run_until_complete(main())
        """
    )

    launch = textwrap.dedent(
        r"""
        export XDG_RUNTIME_DIR=/run/user/1000
        export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
        export WAYLAND_DISPLAY=wayland-0
        export DISPLAY=:0
        for pid in $(pgrep -f '/usr/lib/chromium/chromium' || true); do kill -9 "$pid" 2>/dev/null || true; done
        sleep 1
        PROFILE=/home/saskweise/.config/rockola-chromium
        rm -f "$PROFILE"/SingletonLock "$PROFILE"/SingletonSocket "$PROFILE"/SingletonCookie
        rm -rf "$PROFILE/Default/Cache" "$PROFILE/Default/Code Cache" "$PROFILE/Default/GPUCache"
        nohup chromium --kiosk --start-fullscreen --window-position=0,0 \
          --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
          --disable-restore-session-state --force-device-scale-factor=1 \
          --disk-cache-size=1 --remote-debugging-port=9222 \
          --user-data-dir="$PROFILE" --app=http://127.0.0.1:8000/ \
          >/tmp/chromium-debug.log 2>&1 &
        sleep 7
        curl -s http://127.0.0.1:9222/json/list | head -c 1500; echo
        """
    )

    sftp = c.open_sftp()
    with sftp.file("/home/saskweise/dom_eval.py", "w") as f:
        f.write(py.replace("\r\n", "\n"))
    with sftp.file("/home/saskweise/launch_cdp.sh", "w") as f:
        f.write(launch.replace("\r\n", "\n"))
    sftp.chmod("/home/saskweise/launch_cdp.sh", 0o755)
    sftp.close()

    run(c, "bash /home/saskweise/launch_cdp.sh")
    run(c, "python3 /home/saskweise/dom_eval.py")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
