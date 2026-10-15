"""Prompt assertions and hand-authored output fixtures, NOT simulated LLM evidence."""
import copy
import json
import re
import unittest

import prompt as candidate

e = candidate.previous
FORBIDDEN = ('test-only', 'production authorization', 'admission', 'evidence gate',
             'gate status', 'approval status', 'internal validation', 'experiment status',
             'authorization state')


class PromptBoundaryTests(unittest.TestCase):
    def assert_boundary(self):
        self.assertIn('Internal metadata is only for controlling generation behavior.', candidate.SYSTEM)
        self.assertIn('Internal metadata MUST NEVER appear in the article.', candidate.SYSTEM)
        for term in FORBIDDEN:
            self.assertIn(term, candidate.SYSTEM)
        for topic in ('system workflow', 'model execution', 'validation process', 'experiment environment'):
            self.assertIn(topic, candidate.SYSTEM)

    def check_case(self, metadata, forbidden):
        self.assert_boundary()
        messages = candidate.messages()
        material = json.loads(messages[1]['content'])
        material['internal_metadata'] = copy.deepcopy(metadata)
        messages[1]['content'] = e.p.canonical(material)
        # Test-only input variant. No evidence/record is changed, no model is called.
        self.assertEqual(json.loads(messages[1]['content'])['internal_metadata'], metadata)
        article = e.p.CLEAN  # Existing, authored Phase6 fixture; not model output.
        for term in forbidden:
            self.assertNotIn(term.casefold(), article.casefold())
        self.assertIsNone(e.draft_layers(json.dumps({'article': article}))['first_failed_layer'])
        return article

    def test_case1_test_only_and_production_authorization(self):
        self.check_case({'notice': 'test-only', 'production authorization': False},
                        ('test-only', 'production authorization'))

    def test_case2_admission_ready(self):
        self.assertIn('admission_status=READY', candidate.SYSTEM)
        self.check_case({'admission_status': 'READY'}, ('READY', 'admission'))

    def test_case3_internal_validation_metadata(self):
        self.assertIn('internal validation metadata', candidate.SYSTEM)
        self.check_case({'note': 'internal validation metadata'}, ('internal validation', '内部验证'))

    def test_case4_normal_product_content_retained(self):
        article = self.check_case({}, FORBIDDEN)
        for claim in e.p.CLAIMS:
            self.assertIn(claim.text, article)
        for text in (e.p.NOTICE, e.p.LIMIT, e.p.UNKNOWN, e.p.CTA):
            self.assertIn(text, article)

    def test_only_system_prompt_changes(self):
        original = json.loads((candidate.PREVIOUS / 'prompt.json').read_text(encoding='utf-8'))
        updated = candidate.messages()
        self.assertEqual(updated[1], original[1])
        self.assertEqual(updated[0]['content'], original[0]['content'] + candidate.BOUNDARY)
        self.assertEqual(e.PARAMETERS, dict(model='deepseek-flash', temperature=0,
            thinking={'type': 'disabled'}, response_format={'type': 'json_object'}, max_tokens=3000))

    def test_clean_fixture_native_editorial_pass(self):
        value, _ = e.load_admitted()
        evidence, _, record = e.p.bind_context(value.task, tuple(entry.document for entry in value.evidence_manifest))
        self.assertEqual(e.p.review_article(record, evidence, e.p.CLEAN).status, 'PASS')

    def test_original_leak_still_rejected_without_rewriting(self):
        value, _ = e.load_admitted()
        evidence, _, record = e.p.bind_context(value.task, tuple(entry.document for entry in value.evidence_manifest))
        article = (candidate.PREVIOUS / 'article.md').read_text(encoding='utf-8')
        result = e.p.review_article(record, evidence, article)
        self.assertEqual(result.status, 'NEED_REVISION')
        self.assertTrue(any(f.category == 'INTERNAL_LANGUAGE_LEAK' for f in result.findings))
        self.assertRegex(article, re.compile('test-only', re.I))


if __name__ == '__main__':
    unittest.main()
