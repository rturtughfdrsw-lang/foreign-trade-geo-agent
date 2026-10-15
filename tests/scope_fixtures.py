"""Explicit scripted scope decisions for transport tests; no semantic proof."""
from foreign_trade_geo_agent.core.evidence_intake import (
    ArticleScopeCoverage, SemanticAssessment, RequirementDecision, EvidenceSpan,
    SupportVerdict, snapshot_digest,
)


class ExplicitTestScopeReviewer:
    def assess(self, snapshot, *, now):
        decisions = []
        for requirement in snapshot.task.requirements:
            sources = [e.supplement for e in snapshot.active_evidence
                       if requirement.requirement_id in e.supplement.requirement_ids]
            spans = tuple(EvidenceSpan(s.evidence_id, 0, len(s.content), s.content) for s in sources)
            decisions.append(RequirementDecision(requirement.requirement_id,
                SupportVerdict.SUPPORTED if spans else SupportVerdict.MISSING,
                'Explicit TEST fixture decision; source and scope assumed for transport testing only.', spans))
        return SemanticAssessment(snapshot_digest(snapshot), 'TEST-ONLY-SCOPE-NOT-HUMAN', now,
            tuple(decisions), ArticleScopeCoverage(True, 'Explicit TEST fixture scope assumption, not human signoff.'))
