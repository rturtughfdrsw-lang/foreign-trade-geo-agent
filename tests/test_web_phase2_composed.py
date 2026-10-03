from __future__ import annotations

import asyncio
from contextlib import ExitStack
from pathlib import Path
import re
import socket
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.web.app import create_app
from foreign_trade_geo_agent.web.application import DemoApplicationService
from foreign_trade_geo_agent.web.composition import build_demo_composition
from foreign_trade_geo_agent.web.jobs import LocalJobRegistry


def _unexpected_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("Demo HTTP flow attempted real network access")


def _run_id_after_start(client: TestClient) -> str:
    launched = client.post("/start", follow_redirects=False)
    location = launched.headers["location"]
    for _ in range(300):
        progress = client.get(location, headers={"HX-Request": "true"})
        location = progress.headers.get("HX-Replace-Url", location)
        if "hx-trigger" not in progress.text:
            break
        time.sleep(0.01)
    match = re.search(r"/runs/([^/]+)/progress", location)
    assert match is not None
    return match.group(1)


class DemoPhase2ComposedTests(unittest.TestCase):
    def test_start_to_verified_has_hard_no_network_tripwire(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)

            def factory(_path, _jobs):
                return DemoApplicationService(composition, LocalJobRegistry())

            app = create_app(db_path=db_path, service_factory=factory)
            with TestClient(app) as client:
                with ExitStack() as guards:
                    guards.enter_context(patch.object(socket, "getaddrinfo", _unexpected_network))
                    guards.enter_context(patch.object(socket, "create_connection", _unexpected_network))
                    guards.enter_context(patch.object(socket.socket, "connect", _unexpected_network))
                    guards.enter_context(patch.object(socket.socket, "connect_ex", _unexpected_network))
                    guards.enter_context(
                        patch.object(
                            asyncio.BaseEventLoop,
                            "create_connection",
                            _unexpected_network,
                        )
                    )
                    run_id = _run_id_after_start(client)
                    setup = client.get(f"/runs/{run_id}/drafts/D1/delivery")
                    created = client.post(
                        f"/runs/{run_id}/drafts/D1/delivery",
                        data={"intent_confirmed": "true"},
                        follow_redirects=False,
                    )
                    attempt_id = created.headers["location"].rsplit("/", 1)[1]
                    result = client.get(created.headers["location"])
                    verified = client.post(
                        f"/runs/{run_id}/deliveries/{attempt_id}/verify",
                        follow_redirects=False,
                    )
                    verification = client.get(verified.headers["location"])
            observations = composition.wordpress_transport.observations

        self.assertEqual(setup.status_code, 200)
        self.assertEqual(created.status_code, 303)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(verified.status_code, 303)
        self.assertEqual(verification.status_code, 200)
        self.assertIn("Verification outcome: VERIFIED", verification.text)
        self.assertEqual(
            tuple(observation.method for observation in observations),
            ("POST", "GET"),
        )
        self.assertEqual(len(observations), 2)

    def test_ambiguous_create_contract_posts_once_and_gets_zero(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "history.sqlite3"
            composition = build_demo_composition(db_path)
            composition.wordpress_transport.post_timeout = True

            def factory(_path, _jobs):
                return DemoApplicationService(composition, LocalJobRegistry())

            app = create_app(db_path=db_path, service_factory=factory)
            with TestClient(app) as client:
                with ExitStack() as guards:
                    guards.enter_context(patch.object(socket, "getaddrinfo", _unexpected_network))
                    guards.enter_context(patch.object(socket, "create_connection", _unexpected_network))
                    guards.enter_context(patch.object(socket.socket, "connect", _unexpected_network))
                    guards.enter_context(patch.object(socket.socket, "connect_ex", _unexpected_network))
                    guards.enter_context(
                        patch.object(
                            asyncio.BaseEventLoop,
                            "create_connection",
                            _unexpected_network,
                        )
                    )
                    run_id = _run_id_after_start(client)
                    created = client.post(
                        f"/runs/{run_id}/drafts/D1/delivery",
                        data={"intent_confirmed": "true"},
                        follow_redirects=False,
                    )
                    attempt_id = created.headers["location"].rsplit("/", 1)[1]
                    client.post(
                        f"/runs/{run_id}/deliveries/{attempt_id}/verify",
                        follow_redirects=False,
                    )
                    retry = client.post(
                        f"/runs/{run_id}/drafts/D1/delivery",
                        data={"intent_confirmed": "true"},
                        follow_redirects=False,
                    )
                    verification = client.get(
                        f"/runs/{run_id}/deliveries/{attempt_id}/verification"
                    )
            observations = composition.wordpress_transport.observations

        self.assertEqual(created.status_code, 303)
        self.assertEqual(retry.status_code, 303)
        self.assertEqual(retry.headers["location"].rsplit("/", 1)[1], attempt_id)
        self.assertIn("Verification outcome: UNRESOLVED", verification.text)
        self.assertEqual(
            tuple(observation.method for observation in observations),
            ("POST",),
        )
        self.assertEqual(len(observations), 1)


if __name__ == "__main__":
    unittest.main()
