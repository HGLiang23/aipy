"""常驻启动器：拉起 uvicorn + next dev，探活后保持存活直到进程被回收。用完即删。

以 run_in_background 方式运行，子进程继承本进程生命周期。
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
LOGS = ROOT / ".workbuddy/backups"
LOGS.mkdir(parents=True, exist_ok=True)

API_PORT = 8000
WEB_PORT = 3000

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"


def port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def probe(url: str, timeout: float = 5.0) -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as r:
            return f"{r.status} len={len(r.read())}"
    except Exception as e:  # noqa: BLE001
        return f"FAIL {type(e).__name__}: {e}"


def spawn(cmd: list[str], cwd: Path, log_name: str):
    handle = open(LOGS / log_name, "w", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )


report: dict[str, object] = {}

api = None
if not port_busy(API_PORT):
    api = spawn(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", str(API_PORT)],
        ROOT,
        "runtime_api.log",
    )
    report["api_pid"] = api.pid
else:
    report["api_pid"] = "already-running"

web = None
if not port_busy(WEB_PORT):
    node = shutil.which("node") or r"C:\nvm4w\nodejs\node.exe"
    next_entry = WEB / "node_modules/next/dist/bin/next"
    web = spawn([node, str(next_entry), "dev", "-H", "0.0.0.0", "-p", str(WEB_PORT)], WEB, "runtime_web.log")
    report["web_pid"] = web.pid
    report["web_node"] = node
else:
    report["web_pid"] = "already-running"

deadline = time.time() + 120
api_ok = web_ok = False
while time.time() < deadline:
    if not api_ok:
        api_ok = probe(f"http://127.0.0.1:{API_PORT}/health/live", 3).startswith("200")
    if not web_ok:
        web_ok = probe(f"http://127.0.0.1:{WEB_PORT}/", 5).startswith("200")
    if api_ok and web_ok:
        break
    time.sleep(3)

report["api_health"] = probe(f"http://127.0.0.1:{API_PORT}/health/live")
report["api_openapi"] = probe(f"http://127.0.0.1:{API_PORT}/openapi.json")
report["web_root"] = probe(f"http://127.0.0.1:{WEB_PORT}/", 10)
report["web_login"] = probe(f"http://127.0.0.1:{WEB_PORT}/login", 10)
report["listening"] = {str(API_PORT): port_busy(API_PORT), str(WEB_PORT): port_busy(WEB_PORT)}
for name in ("runtime_api.log", "runtime_web.log"):
    p = LOGS / name
    report[name] = p.read_text("utf-8", "replace")[-1200:] if p.exists() else "(missing)"

(LOGS / "launch_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

# 保持存活，避免子进程随父进程退出被连带回收
while True:
    time.sleep(3600)
