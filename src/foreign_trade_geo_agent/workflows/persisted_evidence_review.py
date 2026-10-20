"""Offline persisted review preflight. Trusted clock/ports, no Draft writer or runtime hook."""
from collections.abc import Callable
from datetime import UTC, datetime

from foreign_trade_geo_agent.core.evidence_review_registry import PersistedEvidenceReviewLoader
from foreign_trade_geo_agent.core.evidence_sufficiency import (
    EvidenceGateResult, EvidenceGateStatus, ExcerptReviewTarget, aware_time, bounded_id,
)
from .evidence_sufficiency import EvidenceSufficiencyPreflight


class _PersistedReviewBridge:
    def __init__(self, loader: PersistedEvidenceReviewLoader, review_id: str):
        self._loader = loader
        self._review_id = review_id

    def load_review(self, target, record, proof, now):
        return self._loader.load_persisted_review(target, self._review_id, now)


class PersistedEvidenceSufficiencyPreflight:
    def __init__(self, *, review_loader: PersistedEvidenceReviewLoader | None = None,
                 clock: Callable[[], datetime] | None = None, allow_synthetic: bool = False):
        if type(allow_synthetic) is not bool:
            raise TypeError("Offline synthetic mode must be explicit.")
        self._loader = review_loader
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._allow_synthetic = allow_synthetic

    def check(self, target: ExcerptReviewTarget, review_id: str) -> EvidenceGateResult:
        try:
            now = self._clock()
            if not bounded_id(review_id) or not aware_time(now):
                raise ValueError()
            bridge = None if self._loader is None else _PersistedReviewBridge(self._loader, review_id)
            return EvidenceSufficiencyPreflight(review_loader=bridge, allow_synthetic=self._allow_synthetic).check(target, now=now)
        except Exception:
            return EvidenceGateResult(EvidenceGateStatus.REJECTED, "CURRENT_TRUSTED_REVIEW_REQUIRED")
