"""Read-only development inspection without models, writers or deliveries."""
from datetime import UTC, datetime
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from foreign_trade_geo_agent.core.history import WorkflowRun, RunStatus, site_key_from_url
from foreign_trade_geo_agent.storage.sqlite import SQLiteHistoryStore


class CommercialInspectorTests(unittest.TestCase):
    def setUp(self):
        source=Path(__file__).resolve().parents[1]/'src/foreign_trade_geo_agent/web/commercial_inspector.py'
        self.assertTrue(source.is_file(),'Read-only development inspector is missing')
        spec=importlib.util.spec_from_file_location('commercial_inspector_test',source)
        self.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp=self.enterContext(TemporaryDirectory())
        self.root=Path(self.temp)
        self.db=self.root/'.data/seo-mvp/candidate/history.sqlite3'
        self.db.parent.mkdir(parents=True)
        store=SQLiteHistoryStore(self.db)
        self.run=str(uuid4())
        store.create_run(WorkflowRun(self.run,site_key_from_url('https://example.com'),'offline-test',datetime.now(UTC),None,
            RunStatus.RUNNING,None,None))
        self.report=self.root/'docs/draft-claim-audit-phase7b/report.md'
        self.report.parent.mkdir(parents=True)
        self.report.write_text('TEST ONLY: REJECTED <script>bad()</script>\nproduction_authorized=false',encoding='utf-8')
        self.before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        app=self.module.create_commercial_app(self.root,worktrees_root=self.root/'related',instance='offline')
        self.client=self.enterContext(TestClient(app,base_url='http://127.0.0.1'))

    def test_pages_show_real_records_and_production_denial(self):
        homepage=self.client.get('/')
        self.assertEqual(homepage.status_code,200)
        self.assertIn('DRAFT_EXECUTION_AUTHORIZATION_REQUIRED',homepage.text)
        self.assertIn('NOT_IMPLEMENTED',homepage.text)
        history=self.client.get('/history')
        self.assertIn(self.run,history.text)
        self.assertIn('offline-test',self.client.get('/runs/candidate/'+self.run).text)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)

    def test_reports_escape_content_and_do_not_execute_it(self):
        response=self.client.get('/reports/claim-audit')
        self.assertEqual(response.status_code,200)
        self.assertIn('&lt;script&gt;',response.text)
        self.assertNotIn('<script>',response.text)
        self.assertIn('REJECTED',response.text)

    def test_missing_records_are_explicit_and_no_database_is_created(self):
        self.assertIn('NOT_AVAILABLE',self.client.get('/intake').text)
        self.assertIn('NOT_AVAILABLE',self.client.get('/reports/phase7-admission').text)
        self.assertFalse((self.root/'.data/live-ui/history.sqlite3').exists())

    def test_no_mutation_routes_or_arbitrary_file_access(self):
        self.assertEqual(self.client.post('/').status_code,405)
        self.assertEqual(self.client.post('/intake').status_code,405)
        self.assertEqual(self.client.get('/reports/.env').status_code,404)
        self.assertEqual(self.client.get('/history?db=../../vdemo').status_code,404)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)

    def test_health_reports_commercial_read_only_identity(self):
        status=self.client.get('/_desktop/status').json()
        self.assertEqual(status['profile'],'commercial')
        # The app resolves the project root, including Windows short-name aliases.
        self.assertEqual(status['database'],str(self.db.resolve()))
        self.assertFalse(status['live_model_enabled'])
        self.assertFalse(status['paid_confirmation_required'])

    def test_oversize_report_is_refused(self):
        self.report.write_bytes(b'x'*(256*1024+1))
        self.assertIn('NOT_AVAILABLE',self.client.get('/reports/claim-audit').text)
