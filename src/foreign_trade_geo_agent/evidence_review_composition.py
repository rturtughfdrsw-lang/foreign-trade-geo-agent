"""Explicit TEST preflight/Draft wiring and locked production boundary.

Production is deliberately unavailable until independently authenticated Windows
IPC, protected key/state loading, durable rollback guards and trusted clocks have
concrete implementations AND owner deployment acceptance. No env/JSON switch.
"""
from .adapters.evidence_review_client import EvidenceReviewClient
from .adapters._evidence_review_protocol import ReviewEnvironment
from .adapters.registered_evidence_review import RegisteredEvidenceReviewLoader
from .workflows.persisted_evidence_review import PersistedEvidenceSufficiencyPreflight


class ProductionDraftAdmission:
    """No trusted production task/review/Draft purpose exists in this release.

    Installed at the shared CLI/Live runtime boundary. This is a denial, not an
    authority that callers can unlock with JSON, environment or old receipts.
    """

    def rejection_reason(self, value):
        return "DRAFT_EXECUTION_AUTHORIZATION_REQUIRED"


def _missing_protected_root():
    raise ValueError("PROTECTED_WINDOWS_REVIEW_ROOT_REQUIRED")


def production_preflight() -> PersistedEvidenceSufficiencyPreflight:
    """No caller-supplied identities, anchors, grants, clocks or test ports accepted.

    Always refuses in this release. A usable production composition requires a
    subsequent reviewed installation adapter, not a deployment_verified boolean.
    """
    return PersistedEvidenceSufficiencyPreflight(clock=_missing_protected_root)


def isolated_test_preflight(*, receipt_reader, client: EvidenceReviewClient, clock):
    """Explicit TEST API, accepting only TEST anchors; never production approval."""
    if (receipt_reader is None or type(client) is not EvidenceReviewClient or clock is None
        or client.anchors.environment is not ReviewEnvironment.TEST):
        raise ValueError("ISOLATED_TEST_ROOT_REQUIRED")
    loader = RegisteredEvidenceReviewLoader(receipt_reader=receipt_reader,
        authenticator=client, registry=client)
    return PersistedEvidenceSufficiencyPreflight(review_loader=loader, clock=clock, allow_synthetic=True)


def production_p_only_draft():
    """Locked production entry: no injectable synthetic root or enable flag."""
    from .workflows.content_draft import ContentDraftWorkflow
    return ContentDraftWorkflow(None)


def isolated_test_p_only_draft(*, receipt_reader, client: EvidenceReviewClient, clock):
    """TEST anchors only; local deterministic generator; never a provider writer."""
    from .adapters.p_only_draft import FrozenPOnlyDraftConsumer, DeterministicExcerptDraftGenerator
    from .workflows.content_draft import ContentDraftWorkflow
    if (receipt_reader is None or type(client) is not EvidenceReviewClient or clock is None
        or client.anchors.environment is not ReviewEnvironment.TEST):
        raise ValueError("ISOLATED_TEST_ROOT_REQUIRED")
    loader = RegisteredEvidenceReviewLoader(receipt_reader=receipt_reader, authenticator=client, registry=client)
    return ContentDraftWorkflow(None,
        p_only_consumer=FrozenPOnlyDraftConsumer(review_loader=loader, clock=clock),
        p_only_generator=DeterministicExcerptDraftGenerator())
