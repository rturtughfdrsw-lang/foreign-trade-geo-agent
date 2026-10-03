from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.web.app import create_app


ROOT = Path(__file__).resolve().parents[1]


def _load_start_demo():
    spec = importlib.util.spec_from_file_location(
        "start_demo",
        ROOT / "scripts" / "start_demo.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeUrlResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit: int = -1) -> bytes:
        return self._body


class _FakeSocket:
    def __init__(self, connect_result: int) -> None:
        self.connect_result = connect_result
        self.timeout: float | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect_ex(self, address: tuple[str, int]) -> int:
        return self.connect_result


class _FakeChild:
    def __init__(self, wait_raises: bool = False) -> None:
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.wait_raises = wait_raises

    def poll(self):
        return self.returncode

    def wait(self, timeout: float | None = None):
        if self.wait_raises:
            self.wait_raises = False
            raise KeyboardInterrupt
        self.returncode = 0
        return 0

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = 0


class DemoLauncherTests(unittest.TestCase):
    def test_healthz_returns_demo_marker(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory) / "history.sqlite3")
            with TestClient(app) as client:
                response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertIn("seo-agent-demo", response.text)

    def test_no_tcp_listener_is_free_and_starts_owned_child(self) -> None:
        start_demo = _load_start_demo()
        child = _FakeChild()

        with (
            patch.object(socket, "socket", return_value=_FakeSocket(10061)),
            patch.object(
                start_demo.urllib.request,
                "urlopen",
                side_effect=AssertionError("free port must not be queried over HTTP"),
            ) as urlopen,
            patch.object(start_demo, "wait_until_ready", return_value=True),
            patch.object(start_demo, "spawn_demo", return_value=child) as spawn,
            patch.object(start_demo, "open_browser"),
        ):
            self.assertEqual(start_demo.run(), 0)

        urlopen.assert_not_called()
        spawn.assert_called_once_with(start_demo.venv_python())

    def test_tcp_listener_with_exact_demo_marker_is_running(self) -> None:
        start_demo = _load_start_demo()

        def open_url(url: str, timeout: float):
            return _FakeUrlResponse(200, b'{"app": "seo-agent-demo"}')

        with (
            patch.object(socket, "socket", return_value=_FakeSocket(0)),
            patch.object(start_demo.urllib.request, "urlopen", side_effect=open_url),
        ):
            self.assertEqual(start_demo.classify_healthz(), "running")

    def test_tcp_listener_with_wrong_marker_is_occupied(self) -> None:
        start_demo = _load_start_demo()

        for body in (b'{"app": "not-seo-agent-demo"}', b"other", b"[]"):
            with self.subTest(body=body):
                with (
                    patch.object(socket, "socket", return_value=_FakeSocket(0)),
                    patch.object(
                        start_demo.urllib.request,
                        "urlopen",
                        return_value=_FakeUrlResponse(200, body),
                    ),
                ):
                    self.assertEqual(start_demo.classify_healthz(), "occupied")

    def test_tcp_listener_with_http_error_is_occupied_not_free(self) -> None:
        start_demo = _load_start_demo()

        for status in (404, 500):
            with self.subTest(status=status):
                error = start_demo.urllib.error.HTTPError(
                    start_demo.HEALTHZ_URL,
                    status,
                    "health error",
                    {},
                    None,
                )
                with (
                    patch.object(socket, "socket", return_value=_FakeSocket(0)),
                    patch.object(
                        start_demo.urllib.request,
                        "urlopen",
                        side_effect=error,
                    ),
                ):
                    self.assertEqual(start_demo.classify_healthz(), "occupied")

    def test_case_a_already_running_opens_browser_only(self) -> None:
        start_demo = _load_start_demo()
        with (
            patch.object(start_demo, "classify_healthz", return_value="running"),
            patch.object(start_demo, "open_browser") as browser,
            patch.object(start_demo, "spawn_demo", side_effect=AssertionError("must not spawn")),
        ):
            self.assertEqual(start_demo.run(), 0)

        browser.assert_called_once()

    def test_case_b_occupied_errors_and_kills_nothing(self) -> None:
        start_demo = _load_start_demo()
        with (
            patch.object(start_demo, "classify_healthz", return_value="occupied"),
            patch.object(start_demo, "open_browser") as browser,
            patch.object(start_demo, "spawn_demo", side_effect=AssertionError("must not spawn")),
        ):
            self.assertNotEqual(start_demo.run(), 0)

        browser.assert_not_called()

    def test_case_c_spawns_owned_child_with_venv_python(self) -> None:
        start_demo = _load_start_demo()
        child = _FakeChild()
        spawned: list[Path] = []

        def fake_spawn(python: Path):
            spawned.append(python)
            return child

        with (
            patch.object(start_demo, "classify_healthz", return_value="free"),
            patch.object(start_demo, "wait_until_ready", return_value=True),
            patch.object(start_demo, "spawn_demo", side_effect=fake_spawn),
            patch.object(start_demo, "open_browser") as browser,
        ):
            self.assertEqual(start_demo.run(), 0)

        self.assertEqual(spawned, [start_demo.venv_python()])
        browser.assert_called_once()
        self.assertEqual(child.returncode, 0)

    def test_shutdown_terminates_only_owned_child(self) -> None:
        start_demo = _load_start_demo()
        child = _FakeChild(wait_raises=True)

        def fake_spawn(python: Path):
            return child

        with (
            patch.object(start_demo, "classify_healthz", return_value="free"),
            patch.object(start_demo, "wait_until_ready", return_value=True),
            patch.object(start_demo, "spawn_demo", side_effect=fake_spawn),
            patch.object(start_demo, "open_browser"),
        ):
            self.assertEqual(start_demo.run(), 0)

        self.assertTrue(child.terminated)

    def test_launcher_uses_venv_python_not_path_python(self) -> None:
        start_demo = _load_start_demo()
        venv = start_demo.venv_python()

        self.assertIn(".venv", str(venv))
        self.assertEqual(venv.name, "python.exe")
        self.assertNotEqual(str(venv), "python")

        captured: list[list[str]] = []

        class _FakePopen:
            def __init__(self, argv, **kwargs):
                captured.append(list(argv))

        with patch.object(start_demo.subprocess, "Popen", _FakePopen):
            start_demo.spawn_demo(venv)

        self.assertEqual(captured[0][0], str(venv))
        self.assertEqual(captured[0][1:], ["-m", "foreign_trade_geo_agent.web"])


if __name__ == "__main__":
    unittest.main()
