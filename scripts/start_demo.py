"""Stdlib-only Windows one-click launcher for the local SEO Agent Demo."""

from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


DEMO_HOST = "127.0.0.1"
DEMO_PORT = 8000
HEALTHZ_URL = "http://127.0.0.1:8000/healthz"
DEMO_URL = "http://127.0.0.1:8000"
DEMO_MARKER = "seo-agent-demo"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def venv_python() -> Path:
    return repo_root() / ".venv" / "Scripts" / "python.exe"


def tcp_port_reachable(
    host: str = DEMO_HOST,
    port: int = DEMO_PORT,
    timeout: float = 1.0,
) -> bool:
    """Return whether a TCP listener accepts connections on ``host:port``."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


def classify_healthz(url: str = HEALTHZ_URL, timeout: float = 1.0) -> str:
    """Return ``running``, ``occupied``, or ``free``."""

    if not tcp_port_reachable(timeout=timeout):
        return "free"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(256).decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return "occupied"
            if (
                response.status == 200
                and isinstance(payload, dict)
                and payload.get("app") == DEMO_MARKER
            ):
                return "running"
            return "occupied"
    except urllib.error.HTTPError:
        return "occupied"
    except urllib.error.URLError:
        return "occupied"
    except (TimeoutError, OSError):
        return "occupied"


def open_browser(url: str = DEMO_URL) -> None:
    webbrowser.open(url)


def spawn_demo(python: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [str(python), "-m", "foreign_trade_geo_agent.web"],
        cwd=repo_root(),
    )


def wait_until_ready(timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if classify_healthz() == "running":
            return True
        time.sleep(0.2)
    return False


def _bounded_kill(child: subprocess.Popen[bytes]) -> None:
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()


def run() -> int:
    python = venv_python()
    if not python.is_file():
        print(
            "Setup required: create .venv, then run "
            'python -m pip install -e ".[demo]".'
        )
        return 1

    state = classify_healthz()
    if state == "running":
        print("SEO Agent Demo is already running.")
        open_browser()
        return 0
    if state == "occupied":
        print("Error: port 8000 is occupied by another process. Not launching.")
        return 1

    child = spawn_demo(python)
    if not wait_until_ready():
        print("Error: the Demo did not become ready. Stopping the owned process.")
        child.terminate()
        _bounded_kill(child)
        return 1

    open_browser()
    print("SEO Agent Demo is running.")
    print("Press Ctrl+C to stop.")
    try:
        return child.wait()
    except KeyboardInterrupt:
        child.terminate()
        _bounded_kill(child)
        return 0
    finally:
        if child.poll() is None:
            child.terminate()
            _bounded_kill(child)


if __name__ == "__main__":
    raise SystemExit(run())
