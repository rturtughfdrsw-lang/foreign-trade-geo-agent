"""Bounded, lossless UTF-8 document boundary; no file path/URL execution."""
import hashlib

from foreign_trade_geo_agent.core.evidence_intake import MAX_TEXT, Supplement, SupplementMethod, require


def text_document(*, evidence_id: str, requirement_ids: tuple[str, ...], payload: bytes,
                  source_label: str, source_locator: str, declared_source_owner: str,
                  supersedes: str | None = None) -> Supplement:
    try:
        require(type(payload) is bytes and 0 < len(payload) <= MAX_TEXT * 4)
        content = payload.decode("utf-8", errors="strict")
        return Supplement(evidence_id, requirement_ids, SupplementMethod.TEXT_DOCUMENT, content,
                          source_label, source_locator, declared_source_owner,
                          hashlib.sha256(payload).hexdigest(), supersedes)
    except Exception:
        raise ValueError("CUSTOMER_TEXT_DOCUMENT_REJECTED") from None
