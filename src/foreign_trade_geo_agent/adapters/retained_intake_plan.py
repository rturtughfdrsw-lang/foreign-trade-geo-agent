"""Offline native candidate selection for revalidating a retained EXPLAIN Plan.

This does not invent a new strategy or assess customer evidence. The ordinary
ChangePlanWorkflow still owns parsing, validation, scope and finalization.
"""
import json

from foreign_trade_geo_agent.core.change_plan import (
    ChangeOperationType, ChangePlanGeneration, ChangePlanGenerationStatus,
)
from foreign_trade_geo_agent.core.evidence_intake import require


class RetainedIntakePlanWriter:
    async def write_change_plan(self, prompt):
        context = prompt.input.customer_context
        require(context is not None)
        snapshot = context.snapshot
        op = snapshot.planning_input.change_plan_report.operations[0]
        candidates = prompt.content_point_candidates_for(op.opportunity_ref)
        points = [next(c for c in candidates if c.text == subject
                       and c.origin_ref in (*op.page_refs, *op.source_refs))
                  for subject in snapshot.point_subjects]
        operation = {
            "source_action_code": op.source_action_code.value,
            "operation_type": op.operation_type.value,
            "source_refs": list(op.source_refs),
            "content_points": [{"intent": "EXPLAIN", "subject_ref": c.candidate_id} for c in points],
        }
        if op.operation_type is ChangeOperationType.CREATE_NEW_RESOURCE:
            resource = op.new_resource_spec
            require(resource is not None and resource.comparison_table_spec is None)
            operation.update({
                "page_bindings": [{"page_ref": ref,
                    "suggested_source": ref in resource.suggested_source_page_refs} for ref in op.page_refs],
                "resource_purpose": resource.resource_purpose.value,
                "proposed_title": resource.proposed_title,
                "comparison_table_brief": None,
            })
        else:
            locator = next(c for c in prompt.locator_candidates_for(op.opportunity_ref)
                           if c.locator_kind == op.locator.locator_kind
                           and c.page_ref == op.locator.page_ref
                           and c.target_heading == op.locator.observed_heading)
            operation.update(page_refs=list(op.page_refs), locator_ref=locator.candidate_id)
        if op.audit_refs:
            operation["audit_refs"] = list(op.audit_refs)
        body = {"opportunity_operations": {op.opportunity_ref: {
            "primary_operation": operation, "secondary_operation": None}}}
        return ChangePlanGeneration("local", "retained-plan-revalidation",
            ChangePlanGenerationStatus.SUCCESS, json.dumps(body), None)
