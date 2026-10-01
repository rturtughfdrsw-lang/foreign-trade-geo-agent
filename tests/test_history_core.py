from __future__ import annotations

from datetime import UTC, datetime
import unittest

from foreign_trade_geo_agent.core.history import (
    ArtifactRecord,
    ArtifactType,
    RunStatus,
    WorkflowRun,
    WordPressAttemptState,
    WordPressDraftAttempt,
    site_key_from_url,
    valid_public_remote_link,
)


RUN_ID = "11111111-1111-4111-8111-111111111111"
ARTIFACT_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)


class SiteIdentityTests(unittest.TestCase):
    def test_normalizes_case_idna_and_effective_ports(self) -> None:
        self.assertEqual(
            site_key_from_url("HTTPS://Faß.DE/products?q=1#part"),
            "https://xn--fa-hia.de:443",
        )
        self.assertEqual(
            site_key_from_url("http://EXAMPLE.com:8080/path"),
            "http://example.com:8080",
        )

    def test_default_ports_paths_queries_and_fragments_share_identity(self) -> None:
        values = {
            site_key_from_url("https://example.com"),
            site_key_from_url("https://example.com:443/one"),
            site_key_from_url("https://example.com/two?q=secret#fragment"),
        }
        self.assertEqual(values, {"https://example.com:443"})

    def test_rejects_credentials_and_invalid_urls(self) -> None:
        for value in (
            "https://user:password@example.com/",
            "ftp://example.com/",
            "https://example.com:0/",
            "https:///missing-host",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                site_key_from_url(value)


class RemoteLinkValidationTests(unittest.TestCase):
    def test_rejects_invalid_url_ports(self) -> None:
        for value in (
            "https://example.com:99999/x",
            "https://example.com:0/x",
            "https://example.com:abc/x",
            "https://example.com:-1/x",
        ):
            with self.subTest(value=value):
                self.assertFalse(valid_public_remote_link(value))

    def test_accepts_default_and_in_range_ports(self) -> None:
        for value in (
            "https://example.com/x",
            "https://example.com:443/x",
            "https://example.com:8443/x",
        ):
            with self.subTest(value=value):
                self.assertTrue(valid_public_remote_link(value))


class HistoryModelTests(unittest.TestCase):
    def test_run_and_artifact_accept_canonical_uuid_and_aware_datetime(self) -> None:
        run = WorkflowRun(
            run_id=RUN_ID,
            site_key="https://example.com:443",
            workflow_name="content_draft",
            started_at=NOW,
            completed_at=None,
            status=RunStatus.RUNNING,
            failure_kind=None,
            sanitized_error=None,
        )
        artifact = ArtifactRecord(
            artifact_id=ARTIFACT_ID,
            run_id=RUN_ID,
            artifact_type=ArtifactType.SITE_CONTENT,
            payload_version=1,
            created_at=NOW,
            payload=object(),
        )
        self.assertEqual(run.status, RunStatus.RUNNING)
        self.assertEqual(artifact.payload_version, 1)

    def test_rejects_noncanonical_ids_and_naive_datetimes(self) -> None:
        base = dict(
            site_key="https://example.com:443",
            workflow_name="content_draft",
            started_at=NOW,
            completed_at=None,
            status=RunStatus.RUNNING,
            failure_kind=None,
            sanitized_error=None,
        )
        with self.assertRaises(ValueError):
            WorkflowRun(run_id="ABCDEFAB-CDEF-4ABC-8DEF-ABCDEFABCDEF", **base)
        with self.assertRaises(ValueError):
            WorkflowRun(
                run_id=RUN_ID,
                **{**base, "started_at": datetime(2026, 10, 2, 8, 30)},
            )

    def test_run_lifecycle_fields_are_consistent(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowRun(
                run_id=RUN_ID,
                site_key="https://example.com:443",
                workflow_name="content_draft",
                started_at=NOW,
                completed_at=NOW,
                status=RunStatus.RUNNING,
                failure_kind=None,
                sanitized_error=None,
            )
        with self.assertRaises(ValueError):
            WorkflowRun(
                run_id=RUN_ID,
                site_key="https://example.com:443",
                workflow_name="content_draft",
                started_at=NOW,
                completed_at=None,
                status=RunStatus.FAILED,
                failure_kind="storage_error",
                sanitized_error="failed",
            )

    def test_attempt_rejects_boolean_fingerprint_version(self) -> None:
        with self.assertRaises(ValueError):
            WordPressDraftAttempt(
                attempt_id="33333333-3333-4333-8333-333333333333",
                run_id=RUN_ID,
                content_draft_artifact_id=ARTIFACT_ID,
                draft_item_id="D1",
                target_site_key="https://cms.example.com:443",
                fingerprint_version=True,
                request_fingerprint="a" * 64,
                attempted_at=NOW,
                completed_at=None,
                outcome=WordPressAttemptState.PENDING,
                remote_post_id=None,
                remote_link=None,
                failure_kind=None,
                sanitized_error=None,
            )


if __name__ == "__main__":
    unittest.main()
