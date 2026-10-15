"""Full offline business chain and independent NOT AUTHORIZED freeze."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.accept_draft_prompt_contract import prepare


class DraftPromptContractAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / 'case'
        cls.result = prepare(cls.root)

    def test_complete_native_candidate_review_retention_chain_and_low_block(self):
        r = self.result
        self.assertEqual((r['documents'], r['facts'], r['sections'], r['input_interpretations']), (7, 43, 6, 0))
        self.assertEqual((r['low_status'], r['low_writer_calls']), ('BLOCKED', 0))
        self.assertEqual(r['candidate_state'], 'PENDING_SEMANTIC_REVIEW')
        self.assertEqual(r['mock_proposals'], 14)
        self.assertEqual(r['parser_validator_review_test_revalidation_sqlite_markdown_web'], 'PASS')
        self.assertEqual((r['real_requests'], r['wordpress_requests']), (0, 0))
        self.assertFalse(r['production_authorized'] or r['authenticated_human_signoff'])
        response = json.loads((self.root/'native/B-rich-evidence/mock-response.json').read_bytes())
        paragraphs = [sum(len(c['text']) for c in b['claims']) for s in response['draft']['sections'] for b in s['blocks']]
        self.assertGreater(max(paragraphs)-min(paragraphs), 400)
        offline = json.loads((self.root/'offline-result.json').read_bytes())
        self.assertEqual(offline['test_review_replay']['native_status'], 'success')
        self.assertEqual(offline['budgets']['claims'], 21)
        self.assertEqual(offline['budgets']['blocks'], 15)
        replay = json.loads((self.root/'historical-failure-replay.json').read_bytes())
        self.assertEqual((replay['parser'], replay['validator']), ('PASS', 'DETERMINISTICALLY_REJECTED'))
        self.assertEqual((replay['customer_ref_repairs'], replay['proposal_repairs']), (0, 0))

    def test_final_request_hashes_contract_and_readiness_are_independent_and_fail_closed(self):
        root = self.root
        manifest = json.loads((root/'artifact-sha256.json').read_bytes())
        self.assertTrue(all(hashlib.sha256((root/name).read_bytes()).hexdigest() == value for name,value in manifest.items()))
        self.assertEqual((root/'bundle.sha256').read_text().strip(), hashlib.sha256((root/'artifact-sha256.json').read_bytes()).hexdigest())
        raw = (root/'request.FROZEN-NOT-AUTHORIZED.json').read_bytes()
        request = json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.result['request_sha256'])
        self.assertEqual(request['messages'][0]['content'], (root/'system-prompt.txt').read_text())
        self.assertEqual(json.loads(request['messages'][1]['content']), json.loads((root/'user-material.json').read_bytes()))
        p = json.loads((root/'real-request-preflight.json').read_bytes())
        self.assertFalse(p['authorization']['issued'])
        self.assertIsNone(p['authorization']['expires_at'])
        self.assertEqual(p['authorization']['actual_spending_authorized'], 0)
        self.assertEqual((p['max_requests'], p['retries'], p['timeout_seconds']), (1, 0, 60))
        self.assertTrue(p['status'].startswith('BLOCKED'))
        self.assertIsNone(p['token_budget']['exact_tokenizer'])
        self.assertFalse(p['cost']['current_price_verified'])
        self.assertIn('PROMPT_CONTRACT_CONFLICT_FIXED', self.result['statuses'])
        self.assertIn('REAL_WRITING_QUALITY_UNTESTED', self.result['statuses'])
        self.assertEqual(len(json.loads((root/'prompt-conflict-audit.json').read_bytes())['conflicts']), 4)

    def test_frozen_contract_preserves_native_fact_selection_without_an_all_ref_quota(self):
        # A stale freeze must not reintroduce the enumeration requirement that
        # the actual structured-E input no longer has.
        root = self.root
        contract = json.loads((root/'output-contract.json').read_bytes())
        self.assertIsInstance(contract['coverage'], dict)
        self.assertEqual(contract['coverage']['structured_fact_bank'], 'NONEMPTY_VALID_SUBSET')
        self.assertEqual(contract['coverage']['legacy_or_mixed'], 'ALL_CUSTOMER_REFS')
        self.assertTrue(contract['coverage']['section_requirements_preserved'])
        material = json.loads((root/'user-material.json').read_bytes())
        self.assertEqual(contract['coverage']['current_instruction'], material['contract']['customer_coverage_rule'])
        audit = json.loads((root/'prompt-conflict-audit.json').read_bytes())
        self.assertEqual(audit['coverage'], contract['coverage'])

    def test_offline_freeze_does_not_invent_a_public_verification_attempt(self):
        preflight = json.loads((self.root/'real-request-preflight.json').read_bytes())
        public = preflight['public_verification']
        self.assertEqual(public['status'], 'NOT_CHECKED_IN_THIS_OFFLINE_RUN')
        self.assertIsNone(public['checked_at'])
        self.assertIn('unverified', public['result'])
        self.assertFalse(preflight['authorization']['issued'])


if __name__ == '__main__':
    unittest.main()
