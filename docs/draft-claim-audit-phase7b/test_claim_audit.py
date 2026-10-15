import unittest
from dataclasses import replace
from claim_audit import Claim, Scope, Status, audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.scope = Scope('configuration', 'ACURA')
        self.scopes = (self.scope, Scope('configuration', 'TILTENTA'))
        self.claims = (Claim('a', 'ACURA is described.', self.scope, ('E1',)),
                       Claim('t', 'TILTENTA is described.', self.scopes[1], ('E2',)))

    def check(self, article, status, claims=None):
        result = audit(claims or self.claims, self.scopes, article)
        self.assertEqual(result.status, status, result.findings)
        self.assertFalse(result.semantic_approved or result.production_authorized or result.live_execution_authorized)
        return result

    def test_case1(self):
        self.check('Two configurations are described.', Status.REJECTED)

    def test_case2(self):
        c = (replace(self.claims[0], claim_text='Five-axis machining'),)
        self.check('ACURA supports five-axis machining.', Status.PASS, c)

    def test_case3(self):
        c = (replace(self.claims[0], claim_text='selected configurations'),)
        self.check('All configurations support automation.', Status.REJECTED, c)

    def test_case4(self):
        self.check('ACURA and TILTENTA are described separately.', Status.PASS)

    def test_requested_patterns(self):
        for phrase in ('three products', 'multiple solutions', 'all products', 'every case', 'complete coverage', 'totals', 'counts'):
            with self.subTest(phrase=phrase):
                self.check(phrase + ' are documented.', Status.REJECTED)

    def test_exact_explicit_claim_exception(self):
        for text in ('ACURA has three products.', 'All products in ACURA support automation.', 'ACURA has complete coverage.'):
            self.check(text, Status.PASS, (replace(self.claims[0], claim_text=text),))

    def test_exact_text_without_scope_anchor_needs_review(self):
        text='All products support automation.'
        self.check(text, Status.NEEDS_REVIEW, (replace(self.claims[0],claim_text=text),))

    def test_scope_mismatch_cannot_pass(self):
        c = (replace(self.claims[0], claim_text='ACURA includes three products.'),)
        self.check('TILTENTA includes three products.', Status.NEEDS_REVIEW, c)

    def test_qualifier_loss_cannot_pass(self):
        c = (replace(self.claims[0], claim_text='For selected uses, three products are documented.'),)
        self.check('Three products are documented.', Status.NEEDS_REVIEW, c)

    def test_negation_question_and_quote_need_review(self):
        for text in ('Not all products support automation.', 'Are two configurations documented?', 'The phrase "two configurations" is unsupported.'):
            self.check(text, Status.NEEDS_REVIEW)

    def test_format_variants(self):
        for text in ('TWO\nconfigurations are described.', '２ configurations are described.', '2 configurations are described.'):
            self.assertNotEqual(audit(self.claims,self.scopes,text).status, Status.PASS)

    def test_no_cross_claim_aggregation(self):
        self.check('Both products are described.', Status.REJECTED)

    def test_bad_inputs_fail_closed(self):
        for claims, scopes, article in (((),self.scopes,'text'),(self.claims,(), 'text'),
            (self.claims,self.scopes,''),(self.claims,self.scopes,'x'*65537),
            (self.claims,self.scopes,42),(self.claims,self.scopes,'\x00'),
            (self.claims+self.claims,self.scopes,'text'),(self.claims,(self.scope,), 'text')):
            self.assertEqual(audit(claims,scopes,article).status, Status.REJECTED)

    def test_non_english_needs_review(self):
        self.check('所有产品均支持自动化。', Status.NEEDS_REVIEW)

    def test_binding_and_no_mutation(self):
        text='Two configurations are described.'
        before=repr(self.claims)
        a=self.check(text,Status.REJECTED)
        self.assertEqual(a, audit(self.claims,self.scopes,text))
        self.assertNotEqual(a.input_sha256, audit(self.claims,self.scopes,text+' ').input_sha256)
        self.assertEqual(repr(self.claims),before)
        self.assertFalse(hasattr(a,'article'))

    def test_findings_bounded(self):
        r=self.check(('Two configurations exist.\n\n')*150,Status.REJECTED)
        self.assertLessEqual(len(r.findings),128)
        self.assertEqual(r.findings[-1].code,'FINDING_BUDGET')
