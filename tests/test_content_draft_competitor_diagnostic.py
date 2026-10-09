"""Competitor diagnostics remain transient, bounded, and text-free."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from dataclasses import asdict, fields, replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.cli import _plan_validation_diagnostic
from foreign_trade_geo_agent.core.content_draft import (
    CompetitorMentionViolation, ContentDraftSpecification, ContentDraftType,
    NewResourceSectionSpecification, build_content_draft_prompt, describe_competitor_mention,
)
from foreign_trade_geo_agent.core.history import ArtifactType, RunStatus
from foreign_trade_geo_agent.core.orchestration import EndToEndStage
from foreign_trade_geo_agent.storage.serialization import encode_artifact, decode_artifact
from foreign_trade_geo_agent.workflows.content_draft import ContentDraftWorkflow
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification
from foreign_trade_geo_agent.workflows.run_diagnostics import RunDiagnosticContext
from tests.test_content_draft_workflow import (
    _DraftFakeWriter, _expand_input, _generation, _section_text,
)


def response(text='Compared with Rival Pumps, this unit is compact.'):
    raw = json.loads(_section_text())
    raw['draft']['blocks'][0]['claims'][0].update(
        text=text, claim_type='COMPARATIVE_CONTEXT', page_refs=[], source_refs=['S1'])
    return _generation(json.dumps(raw))


class CompetitorDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_mention_has_exact_text_free_descriptor(self):
        value = await _expand_input()
        writer = _DraftFakeWriter([response()])
        workflow = ContentDraftWorkflow(writer)
        report = await workflow.run(value)
        self.assertEqual(report.error, 'COMPETITOR_MENTION')
        self.assertEqual(writer.calls, 1)
        diagnostic = workflow.last_competitor_mention_violation
        self.assertEqual(diagnostic.field_path, 'draft.blocks[0].claims[0].text')
        self.assertEqual(diagnostic.change_ref, 'C1')
        self.assertEqual(diagnostic.draft_item_index, 0)
        self.assertEqual(diagnostic.match_kind, 'TITLE_CASE_HEURISTIC')
        self.assertEqual(diagnostic.mention_count, 1)
        encoded = json.dumps(asdict(diagnostic))
        self.assertNotIn('Rival', encoded)
        self.assertNotIn('compact', encoded)
        self.assertEqual([f.name for f in fields(report)],
            ['status', 'drafts', 'limitations', 'error', 'requires_human_review'])
        artifact = encode_artifact(ArtifactType.CONTENT_DRAFT, report)
        self.assertNotIn('competitor_mention_violation', artifact)
        self.assertEqual(decode_artifact(ArtifactType.CONTENT_DRAFT, 1, artifact), report)

    async def test_success_and_other_final_categories_clear_stale_diagnostic(self):
        value = await _expand_input()
        writer = _DraftFakeWriter([response(), _generation(_section_text()), response(), _generation('{}')])
        workflow = ContentDraftWorkflow(writer)
        await workflow.run(value)
        self.assertIsNotNone(workflow.last_competitor_mention_violation)
        self.assertIsNone((await workflow.run(value)).error)
        self.assertIsNone(workflow.last_competitor_mention_violation)
        await workflow.run(value)
        self.assertIsNotNone(workflow.last_competitor_mention_violation)
        self.assertEqual((await workflow.run(value)).error, 'FIELD_CONTRACT')
        self.assertIsNone(workflow.last_competitor_mention_violation)
        await workflow.run(object())
        self.assertIsNone(workflow.last_competitor_mention_violation)

    async def test_origin_uses_provider_visible_projection_and_preserves_input(self):
        value = await _expand_input()
        source = replace(value.opportunity_report.source_materials[0],
            content='Rival Pumps describes chemical compatibility and material selection.')
        value = replace(value, opportunity_report=replace(value.opportunity_report, source_materials=(source,)))
        before = asdict(value)
        workflow = ContentDraftWorkflow(_DraftFakeWriter([response()]))
        await workflow.run(value)
        self.assertEqual(workflow.last_competitor_mention_violation.source_origin, 'INDUSTRY_RESEARCH')
        self.assertEqual(asdict(value), before)
        workflow = ContentDraftWorkflow(_DraftFakeWriter([response()]))
        await workflow.run(await _expand_input())
        # The workflow cannot inspect arbitrary provider system instructions.
        self.assertEqual(workflow.last_competitor_mention_violation.source_origin, 'UNKNOWN')

    async def test_precise_bullet_path_count_and_validation_precedence(self):
        value = await _expand_input()
        raw = json.loads(response().text)
        claim = raw['draft']['blocks'][0]['claims'][0]
        claim['text'] = 'Rival Pumps and Rival Pumps describe compatibility.'
        raw['draft']['blocks'] = [{'kind': 'BULLET_LIST', 'items': [claim]}]
        workflow = ContentDraftWorkflow(_DraftFakeWriter([_generation(json.dumps(raw))]))
        await workflow.run(value)
        diagnostic = workflow.last_competitor_mention_violation
        self.assertEqual(diagnostic.field_path, 'draft.blocks[0].items[0].text')
        self.assertEqual(diagnostic.mention_count, 2)
        claim['source_refs'] = ['S99']
        workflow = ContentDraftWorkflow(_DraftFakeWriter([_generation(json.dumps(raw))]))
        self.assertEqual((await workflow.run(value)).error, 'UNKNOWN_SOURCE_REFERENCE')
        self.assertIsNone(workflow.last_competitor_mention_violation)

    async def test_cli_only_emits_allowlisted_descriptor_for_matching_failure(self):
        workflow = ContentDraftWorkflow(_DraftFakeWriter([response()]))
        report = await workflow.run(await _expand_input())
        context = RunDiagnosticContext()
        context.competitor_mention_violation = workflow.last_competitor_mention_violation
        outer = SimpleNamespace(run_diagnostics=context)
        result = SimpleNamespace(run=SimpleNamespace(status=RunStatus.FAILED),
            stopped_stage=EndToEndStage.CONTENT_DRAFT, terminal_report=report)
        diagnostic = _plan_validation_diagnostic(result, outer)
        self.assertEqual(diagnostic['field_path'], 'draft.blocks[0].claims[0].text')
        self.assertNotIn('Rival', json.dumps(diagnostic))
        result.terminal_report = replace(report, error='CLAIM_BUDGET')
        self.assertEqual(_plan_validation_diagnostic(result, outer), {'category': 'CLAIM_BUDGET'})
        context.clear()
        self.assertIsNone(context.competitor_mention_violation)

    async def test_nested_resource_and_internal_link_paths(self):
        value = await _expand_input()
        prompt = build_content_draft_prompt(value, 'C1')
        section = _parse_specification(response().text, expected_change_ref='C1')
        resource = ContentDraftSpecification('C1', ContentDraftType.NEW_RESOURCE_DRAFT,
            sections=(NewResourceSectionSpecification('Guidance', section.blocks),))
        descriptor = describe_competitor_mention(1, resource, prompt)
        self.assertEqual(descriptor.field_path, 'draft.sections[0].blocks[0].claims[0].text')
        self.assertEqual(descriptor.section_index, 0)
        link = ContentDraftSpecification('C1', ContentDraftType.INTERNAL_LINK_DRAFT,
            anchor_text='Read guidance', insertion_claims=section.blocks[0].claims)
        descriptor = describe_competitor_mention(1, link, prompt)
        self.assertEqual(descriptor.field_path, 'draft.insertion_claims[0].text')

    async def test_descriptor_rejects_untrusted_values(self):
        workflow = ContentDraftWorkflow(_DraftFakeWriter([response()]))
        await workflow.run(await _expand_input())
        descriptor = workflow.last_competitor_mention_violation
        for field, value in [('field_path', 'Rival Pumps'), ('change_ref', 'secret'),
                             ('match_kind', 'provider prose'), ('source_origin', 'raw evidence'),
                             ('mention_count', 0), ('competitor_index', -1), ('draft_item_index', 8)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(descriptor, **{field: value})


class ComposedCompetitorDiagnosticTests(unittest.TestCase):
    def test_real_cli_composition_carries_transient_diagnostic_without_sqlite_leak(self):
        from foreign_trade_geo_agent.runtime import build_isolated_test_planning_workflow
        from tests.test_cli import invoke_main
        from tests.test_mvp_composed_flow import (
            SITE_URL, _FixtureChangePlanWriter, _FixtureFetcher, _FixtureOpportunityWriter,
            _FixtureResearchWriter, _FixtureSearchProvider,
        )
        holders = []

        def factory(path):
            workflow = build_isolated_test_planning_workflow(path, fetcher=_FixtureFetcher(),
                search_provider=_FixtureSearchProvider(), research_writer=_FixtureResearchWriter(),
                content_opportunity_writer=_FixtureOpportunityWriter(),
                change_plan_writer=_FixtureChangePlanWriter(), content_draft_writer=_DraftFakeWriter([response()]))
            holders.append(workflow)
            return workflow

        with TemporaryDirectory() as temporary, patch.dict(os.environ,
                {'DEEPSEEK_API_KEY': 'dummy', 'TAVILY_API_KEY': 'dummy'}, clear=True):
            db = Path(temporary) / 'history.sqlite3'
            code, stdout, stderr = invoke_main(['plan', '--site', SITE_URL, '--question', 'SEO coverage',
                '--db', str(db)], planning_factory=factory, cwd=Path(temporary))
            self.assertEqual((code, stderr), (1, ''))
            payload = json.loads(stdout)
            self.assertEqual(payload['validation_diagnostic']['field_path'], 'draft.blocks[0].claims[0].text')
            self.assertEqual(payload['validation_diagnostic']['category'], 'COMPETITOR_MENTION')
            self.assertIsInstance(holders[0].run_diagnostics.competitor_mention_violation, CompetitorMentionViolation)
            with closing(sqlite3.connect(db)) as connection:
                dump = '\n'.join(connection.iterdump())
                self.assertEqual(connection.execute('SELECT count(*) FROM artifacts').fetchone()[0], 5)
                self.assertEqual(connection.execute('SELECT count(*) FROM wordpress_draft_attempts').fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT count(*) FROM wordpress_draft_verifications').fetchone()[0], 0)
            for forbidden in ['Rival', 'compact', 'TITLE_CASE_HEURISTIC', 'draft.blocks[0].claims[0].text', 'competitor_mention_violation']:
                self.assertNotIn(forbidden, dump)


if __name__ == '__main__':
    unittest.main()
