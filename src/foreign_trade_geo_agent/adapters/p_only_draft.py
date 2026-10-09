"""Frozen-input consumer and local deterministic renderer for isolated TEST."""
import hashlib

from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.core.p_only_draft import (
    FrozenPOnlyDraft, POnlyDraftGeneration, POnlyDraftMaterial, POnlyDraftRequestV1,
    draft_review_binding_error, p_only_draft_target_error,
)
from .evidence_review import freeze_excerpt_target, load_excerpt_target, draft_input_digest


class FrozenPOnlyDraftConsumer:
    """Uses existing persisted loader; no cached GREEN or editable decision flags."""
    def __init__(self, *, review_loader, clock):
        self._loader, self._clock = review_loader, clock

    def prepare(self, request: POnlyDraftRequestV1) -> FrozenPOnlyDraft:
        if type(request) is not POnlyDraftRequestV1:
            raise ValueError("P_ONLY_DRAFT_REQUEST_INVALID")
        # Copy scalar/bytes fields once; decode a private graph. Never execute
        # caller-supplied DraftInput or read a mutable target after authorization.
        snapshot = POnlyDraftRequestV1(request.frozen_target, request.review_id, request.schema_version)
        target = load_excerpt_target(snapshot.frozen_target)
        if p_only_draft_target_error(target) is not None or freeze_excerpt_target(target) != snapshot.frozen_target:
            raise ValueError("P_ONLY_DRAFT_INPUT_INVALID")
        return FrozenPOnlyDraft(snapshot, target, hashlib.sha256(snapshot.frozen_target).hexdigest(),
                               draft_input_digest(target.draft_input))

    def revalidate(self, execution: FrozenPOnlyDraft):
        if (p_only_draft_target_error(execution.target) is not None
            or freeze_excerpt_target(execution.target) != execution.request.frozen_target
            or hashlib.sha256(execution.request.frozen_target).hexdigest() != execution.frozen_sha256
            or draft_input_digest(execution.target.draft_input) != execution.draft_input_sha256):
            raise ValueError("P_ONLY_DRAFT_INPUT_INVALID")
        review = self._loader.load_persisted_review(execution.target, execution.request.review_id, self._clock())
        if draft_review_binding_error(execution, review):
            raise ValueError("DRAFT_AUTHORIZATION_REQUIRED")
        return review


class DeterministicExcerptDraftGenerator:
    """Local copy only, no LLM, transport, retries, summary or paraphrase."""
    def generate(self, material: POnlyDraftMaterial) -> POnlyDraftGeneration:
        claims = tuple(cd.DraftClaimSpecification(text, cd.DraftClaimType.OBSERVED_PRODUCT_FACT,
            (material.page_ref,), ()) for text in material.statements)
        specification = cd.ContentDraftSpecification(material.change_ref, cd.ContentDraftType.SECTION_DRAFT,
            blocks=tuple(cd.ParagraphSpecification(cd.DraftBlockKind.PARAGRAPH, claims[i:i+4])
                         for i in range(0, len(claims), 4)))
        return POnlyDraftGeneration(specification, material.context, material.attribution)
