"""Process-local sanitized diagnostics for one planning run."""

from __future__ import annotations

from dataclasses import dataclass

from foreign_trade_geo_agent.core.change_plan import (
    FieldContractViolation,
    GroundingViolation,
    TargetLocatorViolation,
)
from foreign_trade_geo_agent.core.content_draft import ClaimTypeViolation, CompetitorMentionViolation, DraftBlockBudgetViolation, NumericGroundingViolation


@dataclass(slots=True)
class RunDiagnosticContext:
    """Carry transient planning violations to an in-process operator."""

    field_contract_violation: FieldContractViolation | None = None
    grounding_violation: GroundingViolation | None = None
    target_locator_violation: TargetLocatorViolation | None = None
    competitor_mention_violation: CompetitorMentionViolation | None = None
    block_budget_violation: DraftBlockBudgetViolation | None = None
    numeric_grounding_violation: NumericGroundingViolation | None = None
    claim_type_violation: ClaimTypeViolation | None = None

    def clear(self) -> None:
        self.field_contract_violation = None
        self.grounding_violation = None
        self.target_locator_violation = None
        self.competitor_mention_violation = None
        self.block_budget_violation = None
        self.numeric_grounding_violation = None
        self.claim_type_violation = None

    def capture_change_plan_violation(
        self,
        *,
        field_contract_violation: FieldContractViolation | None = None,
        grounding_violation: GroundingViolation | None = None,
        target_locator_violation: TargetLocatorViolation | None = None,
    ) -> None:
        if field_contract_violation is not None and not isinstance(
            field_contract_violation,
            FieldContractViolation,
        ):
            raise TypeError("Field contract diagnostic is invalid.")
        if grounding_violation is not None and not isinstance(
            grounding_violation,
            GroundingViolation,
        ):
            raise TypeError("Grounding diagnostic is invalid.")
        if target_locator_violation is not None and not isinstance(
            target_locator_violation,
            TargetLocatorViolation,
        ):
            raise TypeError("Target locator diagnostic is invalid.")
        if sum(
            value is not None
            for value in (
                field_contract_violation,
                grounding_violation,
                target_locator_violation,
            )
        ) > 1:
            raise ValueError("Only one Change Plan diagnostic may be active.")
        self.field_contract_violation = field_contract_violation
        self.grounding_violation = grounding_violation
        self.target_locator_violation = target_locator_violation
