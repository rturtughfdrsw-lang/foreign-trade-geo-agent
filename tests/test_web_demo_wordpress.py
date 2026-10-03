from __future__ import annotations

import unittest

import httpx

from foreign_trade_geo_agent.core.history import site_key_from_url
from foreign_trade_geo_agent.web.demo_wordpress import (
    DEMO_WORDPRESS_POST_ID,
    DemoWordPressRequestObservation,
    DemoWordPressTransport,
    demo_wordpress_origin,
)


class DemoWordPressTransportTests(unittest.TestCase):
    def test_post_returns_deterministic_draft(self) -> None:
        transport = DemoWordPressTransport()
        origin = "https://demo-wordpress-11111111-1111-4111-8111-111111111111.example"
        response = transport(
            httpx.Request(
                "POST",
                f"{origin}/wp-json/wp/v2/posts",
                json={"title": "T", "content": "C", "status": "draft"},
            )
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["id"], DEMO_WORDPRESS_POST_ID)
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(
            site_key_from_url(payload["link"]),
            "https://demo-wordpress-11111111-1111-4111-8111-111111111111.example:443",
        )

    def test_get_returns_same_origin_draft(self) -> None:
        transport = DemoWordPressTransport()
        origin = "https://demo-wordpress-22222222-2222-4222-8222-222222222222.example:443"
        response = transport(
            httpx.Request("GET", f"{origin}/wp-json/wp/v2/posts/{DEMO_WORDPRESS_POST_ID}")
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], DEMO_WORDPRESS_POST_ID)
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(
            site_key_from_url(payload["link"]),
            "https://demo-wordpress-22222222-2222-4222-8222-222222222222.example:443",
        )
        self.assertEqual(payload["title"]["rendered"], "NovaCNC demo draft")

    def test_put_patch_delete_and_unknown_paths_fail_closed(self) -> None:
        transport = DemoWordPressTransport()
        origin = "https://demo-wordpress-33333333-3333-4333-8333-333333333333.example"
        for method in ("PUT", "PATCH", "DELETE"):
            with self.subTest(method=method), self.assertRaises(AssertionError):
                transport(
                    httpx.Request(
                        method,
                        f"{origin}/wp-json/wp/v2/posts/{DEMO_WORDPRESS_POST_ID}",
                    )
                )
        with self.assertRaises(AssertionError):
            transport(httpx.Request("GET", f"{origin}/wp-json/wp/v2/posts/999"))

    def test_post_rejects_non_draft_status(self) -> None:
        transport = DemoWordPressTransport()
        origin = "https://demo-wordpress-44444444-4444-4444-8444-444444444444.example"
        with self.assertRaises(AssertionError):
            transport(
                httpx.Request(
                    "POST",
                    f"{origin}/wp-json/wp/v2/posts",
                    json={"title": "T", "content": "C", "status": "publish"},
                )
            )

    def test_observations_are_sanitized_and_omit_authorization(self) -> None:
        transport = DemoWordPressTransport()
        origin = "https://demo-wordpress-55555555-5555-4555-8555-555555555555.example"
        transport(
            httpx.Request(
                "POST",
                f"{origin}/wp-json/wp/v2/posts",
                json={"title": "T", "content": "C", "status": "draft"},
                headers={"Authorization": "Basic c2VjcmV0"},
            )
        )
        transport(
            httpx.Request(
                "GET",
                f"{origin}/wp-json/wp/v2/posts/{DEMO_WORDPRESS_POST_ID}",
                headers={"Authorization": "Basic c2VjcmV0"},
            )
        )

        self.assertEqual(
            transport.observations,
            (
                DemoWordPressRequestObservation(
                    "POST", "/wp-json/wp/v2/posts", "draft", None
                ),
                DemoWordPressRequestObservation(
                    "GET",
                    f"/wp-json/wp/v2/posts/{DEMO_WORDPRESS_POST_ID}",
                    None,
                    DEMO_WORDPRESS_POST_ID,
                ),
            ),
        )
        for observation in transport.observations:
            self.assertFalse(hasattr(observation, "headers"))
            self.assertFalse(hasattr(observation, "request"))
        serialized = repr(transport.observations)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("Basic", serialized)

    def test_per_run_origin_is_valid_and_distinct(self) -> None:
        first = demo_wordpress_origin("11111111-1111-4111-8111-111111111111")
        second = demo_wordpress_origin("22222222-2222-4222-8222-222222222222")

        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("https://demo-wordpress-"))
        self.assertTrue(first.endswith(".example"))
        self.assertEqual(site_key_from_url(first), f"{first}:443")


if __name__ == "__main__":
    unittest.main()
