"""Explicit V1 reading fixtures; never obtain legacy tables via new Planning."""

from foreign_trade_geo_agent.core.change_plan import (
    CHANGE_PLAN_LIMITATIONS, ChangeOperation, ChangeOperationType, ChangePlanReport,
    ChangePlanStatus, ChangeTargetKind, ComparisonTableSpec, SectionLocator,
    SectionLocatorKind,
)
from foreign_trade_geo_agent.core.content_opportunity import ContentOpportunityActionCode


def legacy_table_operation(*, change_id="C1", opportunity_ref="R1",
                           page_ref="P1",
                           columns=("material selection", "port size"),
                           rows=("application",), heading="Pump Comparison"):
    return ChangeOperation(
        change_id=change_id, opportunity_ref=opportunity_ref,
        source_action_code=ContentOpportunityActionCode.ADD_COMPARISON_TABLE,
        operation_type=ChangeOperationType.ADD_COMPARISON_TABLE,
        target_kind=ChangeTargetKind.MODIFY_EXISTING_PAGE,
        page_refs=(page_ref,), source_refs=("S1",),
        locator=SectionLocator(SectionLocatorKind.PAGE_LEVEL, page_ref, None, None, None),
        proposed_heading=heading, comparison_table_spec=ComparisonTableSpec(columns, rows),
        content_points=(), ordered_headings=(), complete_page_order=False,
        section_purpose=None, internal_link_spec=None, new_resource_spec=None,
    )


def legacy_plan(*operations):
    return ChangePlanReport(ChangePlanStatus.SUCCESS, tuple(operations),
                            CHANGE_PLAN_LIMITATIONS, None)


def validate_legacy_table(number, specification, operation, opportunity, site, report):
    """Exercise retained V1 cell rules and build a historical reading fixture.

    This intentionally calls the cell validator, not new Draft execution.
    Execution eligibility is tested separately through the public finalizer.
    """
    from foreign_trade_geo_agent.core import content_draft as draft
    block, error = draft._finalize_table(
        specification, operation,
        draft._build_evidence_context(operation, site, report), draft._ClaimState(),
    )
    if error is not None:
        return None, error
    return draft.DraftItem(
        draft_id=f"D{number}", change_ref=operation.change_id,
        opportunity_ref=operation.opportunity_ref,
        draft_type=draft.ContentDraftType.COMPARISON_TABLE_DRAFT,
        target_kind=operation.target_kind, target_page_ref=operation.locator.page_ref,
        locator=operation.locator, heading=None, ordered_headings=(),
        blocks=(block,),
        page_refs=operation.page_refs, source_refs=operation.source_refs,
    ), None
