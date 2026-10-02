"""Shared deterministic selection and numbering for bounded audit evidence."""

from foreign_trade_geo_agent.core.audit import (
    AuditEvidence,
    AuditEvidenceCategory,
    AuditEvidenceOutcome,
)
from foreign_trade_geo_agent.core.optimization import (
    MAX_AUDIT_EVIDENCE,
    MAX_AUDIT_MATERIAL_CHARS,
    NumberedAuditEvidence,
    OptimizationPrompt,
)


_OUTCOME_PRIORITY = {
    AuditEvidenceOutcome.WARNING: 0,
    AuditEvidenceOutcome.ABSENT: 1,
    AuditEvidenceOutcome.CHECK_FAILED: 2,
    AuditEvidenceOutcome.NOT_DETECTED: 3,
    AuditEvidenceOutcome.UNKNOWN: 4,
    AuditEvidenceOutcome.OBSERVED: 5,
    AuditEvidenceOutcome.PRESENT: 6,
}
_CATEGORY_PRIORITY = {
    category: number for number, category in enumerate(AuditEvidenceCategory)
}
_PREFERRED_EVIDENCE_KEYS = {
    "robots.file_detected", "robots.ai_crawlers.allowed",
    "robots.ai_crawlers.blocked", "robots.ai_crawlers.missing_rules",
    "robots.ai_crawlers.partial", "meta.title.present",
    "meta.description.present", "meta.canonical.present",
    "schema.any_present", "schema.types", "schema.json_parse_errors",
    "schema.missing_fields", "schema.incomplete_types", "content.h1.present",
    "content.word_count", "content.heading_hierarchy.present",
}
_OPTIONAL_ABSENCE_KEYS = {
    "robots.crawl_delay", "meta.noai.present", "meta.x_robots_noindex",
    "schema.article.present", "schema.faq.present", "schema.howto.present",
    "schema.person.present", "schema.product.present",
}


def _business_priority(item: AuditEvidence) -> int:
    if item.check_key in _PREFERRED_EVIDENCE_KEYS:
        return 0
    if (
        item.check_key in _OPTIONAL_ABSENCE_KEYS
        and item.outcome is AuditEvidenceOutcome.ABSENT
    ) or (
        item.category is AuditEvidenceCategory.AI_DISCOVERY
        and item.outcome in {
            AuditEvidenceOutcome.ABSENT,
            AuditEvidenceOutcome.NOT_DETECTED,
        }
    ):
        return 2
    return 1


def _sort_key(item: AuditEvidence) -> tuple[int, int, int, str, str]:
    return (
        _business_priority(item),
        _OUTCOME_PRIORITY.get(item.outcome, 99),
        _CATEGORY_PRIORITY[item.category],
        item.check_key,
        item.provider_field,
    )


def select_numbered_audit_evidence(
    evidence: tuple[AuditEvidence, ...],
) -> tuple[NumberedAuditEvidence, ...]:
    """Select a stable, bounded A# catalog without imposing sufficiency."""

    eligible: list[AuditEvidence] = []
    for item in evidence:
        if item.outcome in {
            AuditEvidenceOutcome.NOT_CHECKED,
            AuditEvidenceOutcome.NOT_APPLICABLE,
        }:
            continue
        if item not in eligible:
            eligible.append(item)
    eligible.sort(key=_sort_key)
    selected = [item for item in eligible if _business_priority(item) == 0][
        :MAX_AUDIT_EVIDENCE
    ]
    for category in AuditEvidenceCategory:
        allowance = max(0, 4 - sum(item.category is category for item in selected))
        category_items = [
            item
            for item in eligible
            if item.category is category and item not in selected
        ]
        selected.extend(category_items[:allowance])
        selected = selected[: MAX_AUDIT_EVIDENCE]
        if len(selected) >= MAX_AUDIT_EVIDENCE:
            break
    selected.sort(key=_sort_key)

    numbered: list[NumberedAuditEvidence] = []
    for item in selected:
        candidate = NumberedAuditEvidence(f"A{len(numbered) + 1}", item)
        prompt = OptimizationPrompt("x", ("x",), (), tuple((*numbered, candidate)), ())
        if prompt.audit_material_chars() <= MAX_AUDIT_MATERIAL_CHARS:
            numbered.append(candidate)
    return tuple(numbered)
