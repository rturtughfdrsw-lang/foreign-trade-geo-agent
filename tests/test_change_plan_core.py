import json
import unittest
from dataclasses import FrozenInstanceError, replace

from foreign_trade_geo_agent.core.change_plan import (
    CHANGE_OPERATION_COMPATIBILITY,
    CHANGE_PLAN_LIMITATIONS,
    MAX_OPERATIONS,
    MAX_OPERATIONS_PER_OPPORTUNITY,
    ChangeOperation,
    ChangeOperationType,
    ChangePlanGeneration,
    ChangePlanGenerationStatus,
    ChangePlanReport,
    ChangePlanStatus,
    ChangePlanValidationCategory,
    ChangeTargetKind,
    ComparisonTableSpec,
    ContentPoint,
    ContentPointIntent,
    ObservedHeadingKind,
    InternalLinkSpec,
    NewResourceSpec,
    NewResourcePurpose,
    NEW_RESOURCE_PURPOSE_BY_ACTION,
    SectionLocator,
    SectionLocatorKind,
    canonical_change_operation_identity,
    phrase_is_grounded,
    proposed_label_is_grounded,
)
from foreign_trade_geo_agent.core.content_opportunity import (
    ContentOpportunityActionCode,
)


class ChangePlanCoreTests(unittest.TestCase):
    def test_status_enums_are_minimal_exact_sets(self) -> None:
        self.assertEqual(
            {item.name for item in ChangePlanStatus},
            {
                "SUCCESS",
                "INVALID_INPUT",
                "INPUT_TOO_LARGE",
                "GENERATION_FAILED",
                "INVALID_OUTPUT",
                "WORKFLOW_TIMEOUT",
            },
        )

    def test_validation_categories_are_the_complete_stable_set(self) -> None:
        self.assertEqual(
            {item.name for item in ChangePlanValidationCategory},
            {
                "JSON_FORMAT",
                "FIELD_CONTRACT",
                "OUTPUT_TOO_LARGE",
                "UNKNOWN_OPPORTUNITY_REFERENCE",
                "UNKNOWN_PAGE_REFERENCE",
                "UNKNOWN_SOURCE_REFERENCE",
                "OPERATION_NOT_ALLOWED",
                "TARGET_LOCATOR_INVALID",
                "EVIDENCE_USE_NOT_ALLOWED",
                "CONTENT_NOT_GROUNDED",
                "INTERNAL_LINK_INVALID",
                "UNSUPPORTED_ABSENCE_CLAIM",
                "INPUT_TOO_LARGE",
            },
        )
        self.assertEqual(
            {item.name for item in ChangePlanGenerationStatus}, {"SUCCESS", "FAILED"}
        )

    def test_operation_enum_is_the_approved_six_item_taxonomy(self) -> None:
        self.assertEqual(
            {item.name for item in ChangeOperationType},
            {
                "EXPAND_SECTION",
                "PROPOSE_SECTION_REORDER",
                "ADD_SECTION",
                "ADD_COMPARISON_TABLE",
                "ADD_INTERNAL_LINK",
                "CREATE_NEW_RESOURCE",
            },
        )

    def test_content_point_intent_is_the_approved_four_item_taxonomy(self) -> None:
        self.assertEqual(
            {item.name for item in ContentPointIntent},
            {"EXPLAIN", "COMPARE", "DESCRIBE", "SUMMARIZE"},
        )

    def test_models_are_frozen_and_slotted(self) -> None:
        point = ContentPoint(ContentPointIntent.EXPLAIN, "chemical compatibility")
        with self.assertRaises(FrozenInstanceError):
            point.subject = "changed"  # type: ignore[misc]
        self.assertFalse(hasattr(point, "__dict__"))

    def test_generation_success_and_failure_invariants(self) -> None:
        successful = ChangePlanGeneration(
            provider="fake",
            model="fake",
            status=ChangePlanGenerationStatus.SUCCESS,
            text='{"operations":[]}',
            error=None,
        )
        failed = ChangePlanGeneration(
            provider="fake",
            model="fake",
            status=ChangePlanGenerationStatus.FAILED,
            text=None,
            error="safe failure",
        )
        self.assertEqual(successful.status, ChangePlanGenerationStatus.SUCCESS)
        self.assertEqual(failed.status, ChangePlanGenerationStatus.FAILED)
        with self.assertRaises(ValueError):
            replace(successful, text=None)
        with self.assertRaises(ValueError):
            replace(failed, text="secret")

    def test_reports_always_require_human_review(self) -> None:
        report = ChangePlanReport(
            status=ChangePlanStatus.SUCCESS,
            operations=(),
            limitations=CHANGE_PLAN_LIMITATIONS,
            error=None,
        )
        self.assertTrue(report.requires_human_review)
        with self.assertRaises(ValueError):
            replace(report, requires_human_review=False)

    def test_success_report_requires_fixed_limitations_and_no_error(self) -> None:
        with self.assertRaises(ValueError):
            ChangePlanReport(ChangePlanStatus.SUCCESS, (), (), None)
        with self.assertRaises(ValueError):
            ChangePlanReport(
                ChangePlanStatus.SUCCESS,
                (),
                CHANGE_PLAN_LIMITATIONS,
                "FIELD_CONTRACT",
            )

    def test_failure_error_must_be_allowlisted_when_present(self) -> None:
        with self.assertRaises(ValueError):
            ChangePlanReport(
                ChangePlanStatus.INVALID_OUTPUT,
                (),
                (),
                "secret exception text",
            )

    def test_validation_failure_requires_category_and_runtime_failure_omits_it(self) -> None:
        with self.assertRaises(ValueError):
            ChangePlanReport(ChangePlanStatus.INVALID_OUTPUT, (), (), None)
        with self.assertRaises(ValueError):
            ChangePlanReport(
                ChangePlanStatus.GENERATION_FAILED,
                (),
                (),
                "FIELD_CONTRACT",
            )

    def test_failure_report_cannot_carry_success_limitations(self) -> None:
        with self.assertRaises(ValueError):
            ChangePlanReport(
                ChangePlanStatus.GENERATION_FAILED,
                (),
                CHANGE_PLAN_LIMITATIONS,
                None,
            )

    def test_failure_report_cannot_carry_operations(self) -> None:
        locator = SectionLocator(
            locator_kind=SectionLocatorKind.PAGE_LEVEL,
            page_ref="P1",
            observed_heading=None,
            observed_heading_kind=None,
            observed_context=None,
        )
        from foreign_trade_geo_agent.core.change_plan import ChangeOperation

        operation = ChangeOperation(
            change_id="C1",
            opportunity_ref="R1",
            source_action_code=ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
            operation_type=ChangeOperationType.EXPAND_SECTION,
            target_kind=ChangeTargetKind.MODIFY_EXISTING_PAGE,
            locator=locator,
            proposed_heading=None,
            content_points=(ContentPoint(ContentPointIntent.EXPLAIN, "compatibility"),),
            comparison_table_spec=None,
            internal_link_spec=None,
            new_resource_spec=None,
            page_refs=("P1",),
            source_refs=("S1",),
            ordered_headings=(),
            section_purpose=None,
        )
        with self.assertRaises(ValueError):
            ChangePlanReport(
                status=ChangePlanStatus.INVALID_OUTPUT,
                operations=(operation,),
                limitations=(),
                error="FIELD_CONTRACT",
            )

    def test_success_report_enforces_aggregate_operation_invariants(self) -> None:
        operation = self._expand_operation("C1", "R1")
        invalid_operation_sets = (
            (operation, replace(operation, change_id="C1", content_points=(ContentPoint(ContentPointIntent.EXPLAIN, "material selection"),))),
            (operation, replace(operation, change_id="C3", content_points=(ContentPoint(ContentPointIntent.EXPLAIN, "material selection"),))),
            (replace(operation, change_id="C2"),),
            tuple(
                self._expand_operation(f"C{index}", f"R{index}")
                for index in range(1, MAX_OPERATIONS + 2)
            ),
            tuple(
                replace(
                    operation,
                    change_id=f"C{index}",
                    content_points=(ContentPoint(ContentPointIntent.EXPLAIN, f"topic {index}"),),
                )
                for index in range(1, MAX_OPERATIONS_PER_OPPORTUNITY + 2)
            ),
            (operation, replace(operation, change_id="C2")),
        )
        for operations in invalid_operation_sets:
            with self.subTest(ids=tuple(item.change_id for item in operations)):
                with self.assertRaises(ValueError):
                    ChangePlanReport(
                        ChangePlanStatus.SUCCESS,
                        operations,
                        CHANGE_PLAN_LIMITATIONS,
                        None,
                    )

    def test_success_report_rejects_canonical_equivalent_operation_payloads(self) -> None:
        operation = self._expand_operation("C1", "R1")
        equivalents = (
            "COMPATIBILITY",
            "ｃｏｍｐａｔｉｂｉｌｉｔｙ",
            "  compatibility  ",
            " ＣＯＭＰＡＴＩＢＩＬＩＴＹ ",
        )
        for equivalent in equivalents:
            with self.subTest(equivalent=equivalent):
                duplicate_point = ContentPoint(
                    ContentPointIntent.EXPLAIN,
                    "compatibility",
                )
                object.__setattr__(duplicate_point, "subject", equivalent)
                duplicate = replace(
                    operation,
                    change_id="C2",
                    content_points=(duplicate_point,),
                )
                with self.assertRaises(ValueError):
                    ChangePlanReport(
                        ChangePlanStatus.SUCCESS,
                        (operation, duplicate),
                        CHANGE_PLAN_LIMITATIONS,
                        None,
                    )

    def test_canonical_identity_keeps_url_case_significant(self) -> None:
        locator = SectionLocator(
            SectionLocatorKind.PAGE_LEVEL,
            "P1",
            None,
            None,
            None,
        )
        operation = ChangeOperation(
            change_id="C1",
            opportunity_ref="R1",
            source_action_code=ContentOpportunityActionCode.ADD_INTERNAL_LINK,
            operation_type=ChangeOperationType.ADD_INTERNAL_LINK,
            target_kind=ChangeTargetKind.MODIFY_EXISTING_PAGE,
            locator=locator,
            proposed_heading=None,
            content_points=(),
            comparison_table_spec=None,
            internal_link_spec=InternalLinkSpec(
                "P1",
                "P2",
                "https://example.com/Path?Key=Value",
                "https://example.com/Target",
                "chemical compatibility",
            ),
            new_resource_spec=None,
            page_refs=("P1", "P2"),
            source_refs=("S1",),
            ordered_headings=(),
            section_purpose=None,
        )
        changed_url = replace(
            operation,
            change_id="C2",
            internal_link_spec=replace(
                operation.internal_link_spec,
                source_url="https://example.com/path?Key=Value",
            ),
        )

        self.assertNotEqual(
            canonical_change_operation_identity(operation),
            canonical_change_operation_identity(changed_url),
        )

    @staticmethod
    def _expand_operation(change_id: str, opportunity_ref: str) -> ChangeOperation:
        return ChangeOperation(
            change_id=change_id,
            opportunity_ref=opportunity_ref,
            source_action_code=ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
            operation_type=ChangeOperationType.EXPAND_SECTION,
            target_kind=ChangeTargetKind.MODIFY_EXISTING_PAGE,
            locator=SectionLocator(SectionLocatorKind.PAGE_LEVEL, "P1", None, None, None),
            proposed_heading=None,
            content_points=(ContentPoint(ContentPointIntent.EXPLAIN, "compatibility"),),
            comparison_table_spec=None,
            internal_link_spec=None,
            new_resource_spec=None,
            page_refs=("P1",),
            source_refs=("S1",),
            ordered_headings=(),
            section_purpose=None,
        )

    def test_final_operation_rejects_discriminator_field_mismatch(self) -> None:
        from foreign_trade_geo_agent.core.change_plan import ChangeOperation

        operation = ChangeOperation(
            change_id="C1",
            opportunity_ref="R1",
            source_action_code=ContentOpportunityActionCode.EXPAND_PAGE_SECTION,
            operation_type=ChangeOperationType.EXPAND_SECTION,
            target_kind=ChangeTargetKind.MODIFY_EXISTING_PAGE,
            locator=SectionLocator(SectionLocatorKind.PAGE_LEVEL, "P1", None, None, None),
            proposed_heading=None,
            content_points=(ContentPoint(ContentPointIntent.EXPLAIN, "compatibility"),),
            comparison_table_spec=None,
            internal_link_spec=None,
            new_resource_spec=None,
            page_refs=("P1",),
            source_refs=("S1",),
            ordered_headings=(),
            section_purpose=None,
        )
        with self.assertRaises(ValueError):
            replace(operation, operation_type=ChangeOperationType.ADD_INTERNAL_LINK)
        with self.assertRaises(ValueError):
            replace(operation, proposed_heading="Unexpected")

    def test_operation_compatibility_is_fixed_and_immutable(self) -> None:
        self.assertEqual(
            CHANGE_OPERATION_COMPATIBILITY[
                ContentOpportunityActionCode.EXPAND_PAGE_SECTION
            ],
            frozenset({ChangeOperationType.EXPAND_SECTION}),
        )
        self.assertEqual(
            CHANGE_OPERATION_COMPATIBILITY[
                ContentOpportunityActionCode.ADD_BUYER_GUIDANCE
            ],
            frozenset(
                {
                    ChangeOperationType.ADD_SECTION,
                    ChangeOperationType.CREATE_NEW_RESOURCE,
                }
            ),
        )
        with self.assertRaises(TypeError):
            CHANGE_OPERATION_COMPATIBILITY[
                ContentOpportunityActionCode.EXPAND_PAGE_SECTION
            ] = frozenset()  # type: ignore[index]

    def test_new_resource_purpose_mapping_is_fixed_and_immutable(self) -> None:
        self.assertEqual(
            NEW_RESOURCE_PURPOSE_BY_ACTION[
                ContentOpportunityActionCode.ADD_TECHNICAL_DOCUMENTATION
            ],
            NewResourcePurpose.TECHNICAL_DOCUMENTATION,
        )
        self.assertEqual(
            NEW_RESOURCE_PURPOSE_BY_ACTION[
                ContentOpportunityActionCode.ADD_BUYER_GUIDANCE
            ],
            NewResourcePurpose.BUYER_GUIDANCE,
        )
        with self.assertRaises(TypeError):
            NEW_RESOURCE_PURPOSE_BY_ACTION[
                ContentOpportunityActionCode.ADD_BUYER_GUIDANCE
            ] = NewResourcePurpose.TECHNICAL_DOCUMENTATION  # type: ignore[index]

    def test_locator_shape_invariants(self) -> None:
        page = SectionLocator(
            SectionLocatorKind.PAGE_LEVEL, "P1", None, None, None
        )
        heading = SectionLocator(
            SectionLocatorKind.EXACT_OBSERVED_HEADING,
            "P1",
            "Performance",
            ObservedHeadingKind.H2,
            "Observed performance context.",
        )
        new_page = SectionLocator(
            SectionLocatorKind.NEW_PAGE, None, None, None, None
        )
        self.assertEqual(page.page_ref, "P1")
        self.assertEqual(heading.observed_heading_kind, ObservedHeadingKind.H2)
        self.assertIsNone(new_page.page_ref)
        with self.assertRaises(ValueError):
            replace(page, observed_heading="invented")
        with self.assertRaises(ValueError):
            replace(new_page, page_ref="P1")

    def test_exact_locator_context_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            SectionLocator(
                SectionLocatorKind.EXACT_OBSERVED_HEADING,
                "P1",
                "Heading",
                ObservedHeadingKind.H1,
                "x" * 241,
            )

    def test_content_point_rejects_paragraph_length_and_non_enum_intent(self) -> None:
        with self.assertRaises(ValueError):
            ContentPoint(ContentPointIntent.EXPLAIN, "x" * 121)
        with self.assertRaises(ValueError):
            ContentPoint("EXPLAIN", "compatibility")  # type: ignore[arg-type]

    def test_comparison_table_brief_enforces_counts_uniqueness_and_lengths(self) -> None:
        valid = ComparisonTableSpec(
            ("material", "port size"), ("application",)
        )
        self.assertEqual(valid.row_dimensions, ("application",))
        invalid = (
            (("material",), ("application",)),
            (("material", "material"), ("application",)),
            (("material", "port size"), ()),
            (("x" * 81, "port size"), ("application",)),
        )
        for columns, rows in invalid:
            with self.subTest(columns=columns, rows=rows):
                with self.assertRaises(ValueError):
                    ComparisonTableSpec(columns, rows)

    def test_internal_link_final_model_requires_distinct_observed_refs(self) -> None:
        valid = InternalLinkSpec(
            "P1",
            "P2",
            "https://example.com/one",
            "https://example.com/two",
            "chemical compatibility",
        )
        self.assertEqual(valid.target_page_ref, "P2")
        with self.assertRaises(ValueError):
            replace(valid, target_page_ref="P1")

    def test_new_resource_final_model_has_no_url_slug_or_publish_metadata(self) -> None:
        resource = NewResourceSpec(
            resource_purpose=NewResourcePurpose.SUPPORTING_RESOURCE,
            proposed_title="Chemical Compatibility Guide",
            outline_headings=("Material Selection", "Application"),
            content_points=(
                ContentPoint(ContentPointIntent.EXPLAIN, "chemical compatibility"),
            ),
            suggested_source_page_refs=("P1",),
            comparison_table_spec=None,
        )
        for field in ("slug", "final_url", "post_type", "taxonomy", "risk"):
            self.assertFalse(hasattr(resource, field))

    def test_new_resource_final_model_enforces_outline_and_point_bounds(self) -> None:
        point = ContentPoint(ContentPointIntent.EXPLAIN, "chemical compatibility")
        with self.assertRaises(ValueError):
            NewResourceSpec(NewResourcePurpose.SUPPORTING_RESOURCE, "title", ("one",), (point,), (), None)
        with self.assertRaises(ValueError):
            NewResourceSpec(
                NewResourcePurpose.SUPPORTING_RESOURCE, "title", ("one", "two"), (), (), None
            )

    def test_lexical_grounding_normalizes_unicode_case_whitespace_and_common_terms(self) -> None:
        cases = (
            ("ＡＯＤＤ", ("AODD pump",)),
            ("chemical compatibility", ("Chemical   Compatibility",)),
            ("AIR-OPERATED / aodd", ("air-operated / AODD pump",)),
            ("化学兼容性", ("泵的化学兼容性指南",)),
        )
        for phrase, evidence in cases:
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase_is_grounded(phrase, evidence))
        self.assertTrue(
            proposed_label_is_grounded(
                "Air-Operated AODD Guide",
                ("AIR-OPERATED AODD pump",),
            )
        )

    def test_taxonomy_contains_no_risk_approval_or_slug_state(self) -> None:
        names = {
            name
            for enum_type in (
                ChangePlanStatus,
                ChangePlanGenerationStatus,
                ChangeOperationType,
                ChangeTargetKind,
                SectionLocatorKind,
                ObservedHeadingKind,
                ContentPointIntent,
            )
            for name in enum_type.__members__
        }
        self.assertTrue({"SUCCESS", "INVALID_OUTPUT", "WORKFLOW_TIMEOUT"} <= names)
        self.assertTrue({"PAGE_LEVEL", "EXACT_OBSERVED_HEADING", "NEW_PAGE"} <= names)
        self.assertFalse({"LOW", "MEDIUM", "HIGH", "APPROVED", "APPLIED"} & names)


if __name__ == "__main__":
    unittest.main()
    MAX_OPERATIONS,
    MAX_OPERATIONS_PER_OPPORTUNITY,
    ChangeOperation,
