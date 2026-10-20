import unittest

from foreign_trade_geo_agent.core.live_analysis import (
    DEFAULT_LIVE_SEO_GOAL,
    LiveAnalysisInput,
    normalize_live_website_url,
)


class LiveAnalysisInputTests(unittest.TestCase):
    def test_normalizes_idna_host_default_port_empty_path_and_fragment(self) -> None:
        analysis_input = LiveAnalysisInput(
            website_url="https://BÜCHER.Example:443#overview",
        )

        self.assertEqual(
            analysis_input.website_url,
            "https://xn--bcher-kva.example/",
        )
        self.assertEqual(analysis_input.display_identity, "xn--bcher-kva.example")

    def test_preserves_bounded_path_and_query(self) -> None:
        value = "https://Example.COM:8443/products/cnc?series=5&sort=asc#details"

        self.assertEqual(
            normalize_live_website_url(value),
            "https://example.com:8443/products/cnc?series=5&sort=asc",
        )

    def test_rejects_http_credentials_whitespace_backslash_and_malformed_port(self) -> None:
        invalid_values = (
            "http://example.com/",
            "https://user:secret@example.com/",
            "https://example.com/a b",
            "https://example.com\\private",
            "https://example.com:not-a-port/",
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_live_website_url(value)

    def test_rejects_localhost_private_loopback_link_local_reserved_and_benchmark_literals(self) -> None:
        invalid_values = (
            "https://localhost/",
            "https://api.localhost/",
            "https://127.0.0.1/",
            "https://10.0.0.1/",
            "https://169.254.1.1/",
            "https://192.0.2.1/",
            "https://198.18.0.1/",
            "https://[::1]/",
            "https://[fc00::1]/",
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                LiveAnalysisInput(value)

    def test_rejects_unsupported_language_and_oversized_goal(self) -> None:
        with self.assertRaises(ValueError):
            LiveAnalysisInput("https://example.com/", target_language="zh")
        with self.assertRaises(ValueError):
            LiveAnalysisInput("https://example.com/", seo_goal="g" * 301)

    def test_accepts_normalized_url_at_2048_characters(self) -> None:
        prefix = "https://example.com/?q="
        value = prefix + ("a" * (2_048 - len(prefix)))

        analysis_input = LiveAnalysisInput(value)

        self.assertEqual(len(analysis_input.website_url), 2_048)
        self.assertEqual(analysis_input.website_url, value)

    def test_rejects_normalized_url_over_2048_characters(self) -> None:
        prefix = "https://example.com/?q="
        value = prefix + ("a" * (2_049 - len(prefix)))

        with self.assertRaises(ValueError):
            LiveAnalysisInput(value)

    def test_defaults_to_english_goal_and_hostname_identity(self) -> None:
        analysis_input = LiveAnalysisInput("https://www.example.com/")

        self.assertEqual(analysis_input.seo_goal, DEFAULT_LIVE_SEO_GOAL)
        self.assertEqual(analysis_input.target_language, "en")
        self.assertEqual(analysis_input.display_identity, "www.example.com")


if __name__ == "__main__":
    unittest.main()
