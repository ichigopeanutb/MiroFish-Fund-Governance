#!/usr/bin/env python3
"""Stable local launcher for MiroFish development services.

The normal dev command runs Flask with the debug reloader, which is useful while
editing but fragile when the browser is used as a product demo surface. This
launcher starts backend/frontend as background processes, writes PID and log
files, and performs simple health checks.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ".mirofish_runtime"
LOG_DIR = RUNTIME_DIR / "logs"
BACKEND_PID = RUNTIME_DIR / "backend.pid"
FRONTEND_PID = RUNTIME_DIR / "frontend.pid"
BACKEND_URL = "http://127.0.0.1:5001/api/business-simulation/demo"
FRONTEND_URL = "http://127.0.0.1:5174/"


def _root_env_values() -> dict[str, str]:
    env_path = ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    if _pid_running(pid):
        return pid
    path.unlink(missing_ok=True)
    return None


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _health(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except URLError:
        return False
    except TimeoutError:
        return False


def _backend_python() -> Path:
    candidates = [
        ROOT / "backend" / ".venv" / "bin" / "python",
        ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _spawn(name: str, command: list[str], cwd: Path, env: dict[str, str], pid_path: Path) -> int:
    _ensure_dirs()
    log_path = LOG_DIR / f"{name}.log"
    log_file = log_path.open("ab")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_path.write_text(str(process.pid), encoding="utf-8")
    return process.pid


def _start_backend() -> str:
    pid = _read_pid(BACKEND_PID)
    if pid and _health(BACKEND_URL):
        return f"backend already running pid={pid}"
    if _port_open(5001) and _health(BACKEND_URL):
        return "backend already running externally on port=5001"

    env = os.environ.copy()
    env.update({
        "FLASK_DEBUG": "false",
        "FLASK_HOST": "127.0.0.1",
        "FLASK_PORT": "5001",
        "PYTHONUNBUFFERED": "1",
    })
    pid = _spawn(
        "backend",
        [str(_backend_python()), "run.py"],
        ROOT / "backend",
        env,
        BACKEND_PID,
    )
    return f"backend started pid={pid}"


def _start_frontend() -> str:
    pid = _read_pid(FRONTEND_PID)
    if pid and _health(FRONTEND_URL):
        return f"frontend already running pid={pid}"
    if _port_open(5174) and _health(FRONTEND_URL):
        return "frontend already running externally on port=5174"

    env = os.environ.copy()
    env.setdefault("VITE_API_BASE_URL", "http://127.0.0.1:5001")
    root_env = _root_env_values()
    access_code = (
        env.get("VITE_BUSINESS_DEMO_PASSWORD")
        or env.get("BUSINESS_DEMO_ACCESS_CODE")
        or root_env.get("VITE_BUSINESS_DEMO_PASSWORD")
        or root_env.get("BUSINESS_DEMO_ACCESS_CODE")
    )
    if access_code:
        env["VITE_BUSINESS_DEMO_PASSWORD"] = access_code
    pid = _spawn(
        "frontend",
        ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5174"],
        ROOT / "frontend",
        env,
        FRONTEND_PID,
    )
    return f"frontend started pid={pid}"


def start() -> None:
    print(_start_backend())
    print(_start_frontend())
    deadline = time.time() + 20
    while time.time() < deadline:
        if _health(BACKEND_URL) and _health(FRONTEND_URL):
            break
        time.sleep(0.5)
    print(json.dumps(status_payload(), ensure_ascii=False, indent=2))


def _stop_one(name: str, pid_path: Path) -> str:
    pid = _read_pid(pid_path)
    if not pid:
        pid_path.unlink(missing_ok=True)
        return f"{name} not running"
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        pid_path.unlink(missing_ok=True)
        return f"{name} pid={pid} could not be controlled; cleared stale pid file"
    deadline = time.time() + 5
    while time.time() < deadline and _pid_running(pid):
        time.sleep(0.2)
    if _pid_running(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except PermissionError:
            pid_path.unlink(missing_ok=True)
            return f"{name} pid={pid} could not be killed; cleared pid file"
    pid_path.unlink(missing_ok=True)
    return f"{name} stopped pid={pid}"


def stop() -> None:
    print(_stop_one("frontend", FRONTEND_PID))
    print(_stop_one("backend", BACKEND_PID))


def restart() -> None:
    stop()
    start()


def status_payload() -> dict[str, object]:
    backend_pid = _read_pid(BACKEND_PID)
    frontend_pid = _read_pid(FRONTEND_PID)
    return {
        "backend": {
            "pid": backend_pid,
            "port_open": _port_open(5001),
            "healthy": _health(BACKEND_URL),
            "url": BACKEND_URL,
            "log": str(LOG_DIR / "backend.log"),
        },
        "frontend": {
            "pid": frontend_pid,
            "port_open": _port_open(5174),
            "healthy": _health(FRONTEND_URL),
            "url": "http://127.0.0.1:5174/",
            "log": str(LOG_DIR / "frontend.log"),
        },
    }


def status() -> None:
    print(json.dumps(status_payload(), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage stable local MiroFish services")
    parser.add_argument("command", choices=["start", "stop", "restart", "status"])
    args = parser.parse_args()

    if args.command == "start":
        start()
    elif args.command == "stop":
        stop()
    elif args.command == "restart":
        restart()
    else:
        status()


if __name__ == "__main__":
    main()
