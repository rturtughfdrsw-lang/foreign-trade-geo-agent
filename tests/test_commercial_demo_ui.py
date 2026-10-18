"""Read-only UI contracts against the real Render app and synthetic SQLite."""
from copy import deepcopy
import base64
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from foreign_trade_geo_agent.web import commercial_demo_ui as ui
from tests.test_commercial_preview_chinese_ui import Document
from tests import test_render_demo


class DemoPresentationTests(unittest.TestCase):
    setUp = test_render_demo.RenderDemoTests.setUp

    def state(self):
        flow = self.app.state.workflow
        return flow.store.read(flow.store.list_runs()[0])

    def page(self):
        return self.client.get('/runs/'+self.state()['run_id'], auth=self.auth)

    def test_home_has_one_real_primary_action_and_no_unavailable_controls(self):
        response = self.client.get('/', auth=self.auth)
        root = Document(response.text).root
        self.assertEqual([h.text() for h in root.find_all('h1')], ['SEO 内容工作台'])
        primary = root.find_all('a', **{'class': 'primary'})
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0].text(), '体验演示任务')
        self.assertEqual(primary[0].attrs['href'], '/runs/'+self.state()['run_id'])
        self.assertEqual(self.client.get(primary[0].attrs['href'], auth=self.auth).status_code, 200)
        self.assertEqual(root.text(visible=True).count(ui.NOTICE), 1)
        self.assertNotIn('开始新分析', response.text)
        self.assertEqual(root.find_all('form'), [])
        self.assertEqual(root.find_all('input'), [])

    def test_all_real_obligations_and_exact_evidence_are_retained(self):
        state = self.state()
        root = Document(self.page().text).root
        items = root.find_all('section', **{'class': 'review-item'})
        self.assertEqual([item.attrs['id'] for item in items], ['review-'+key for key in ui.COPY])
        for item, (key, copy) in zip(items, ui.COPY.items()):
            self.assertIn(copy[1], item.text(visible=True))
            self.assertIn(copy[5], item.text(visible=True))
            self.assertIn('尚未核对', item.text(visible=True))
            self.assertIn('是否足以支持这项写法，仍需人工判断', item.text(visible=True))
            for span in [s for s in state['spans'] if s['obligation_id'] == key]:
                self.assertIn(span['quote'], item.text())
                self.assertIn(span['span_id'], item.text())
                self.assertIn(span['source_id'], item.text())
        self.assertTrue(all('open' not in d.attrs for d in root.find_all('details')))
        self.assertEqual(root.find_all('form'), [])
        self.assertEqual(root.find_all('select'), [])
        self.assertEqual(root.find_all('textarea'), [])
        self.assertEqual(sum('data-previous' in b.attrs for b in root.find_all('button')), 1)
        self.assertIn('浏览进度不代表已完成审核', root.text(visible=True))

    def test_page_and_navigation_reads_never_write_or_call_writer(self):
        state = deepcopy(self.state())
        folder = Path(self.app.state.data_dir)
        hashes = lambda: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.sqlite3')}
        before = hashes()
        with patch.object(self.app.state.workflow.store, 'save', side_effect=AssertionError('GET must not save')):
            for _ in range(3):
                self.client.get('/', auth=self.auth)
                self.assertEqual(self.page().status_code, 200)
        self.assertEqual(self.state(), state)
        self.assertEqual(hashes(), before)
        self.assertEqual(state['reviews'], [])
        self.assertIsNone(state['confirmation'])
        self.assertFalse(state['production_authorized'])
        self.assertEqual(self.app.state.workflow.writer.calls, 0)

    def test_csp_allows_only_exact_navigation_script_and_forbids_forms(self):
        for response in (self.client.get('/', auth=self.auth), self.page(), self.client.get('/')):
            csp = response.headers['content-security-policy']
            self.assertIn("default-src 'none'", csp)
            self.assertIn("form-action 'none'", csp)
            script_policy = next(p for p in csp.split(';') if p.strip().startswith('script-src'))
            self.assertNotIn('unsafe-inline', script_policy)
            self.assertNotIn('unsafe-eval', script_policy)
            self.assertNotIn("'self'", script_policy)
        script = Document(self.page().text).root.find_all('script')
        self.assertEqual(len(script), 1)
        actual = base64.b64encode(hashlib.sha256(script[0].text().encode()).digest()).decode()
        self.assertEqual(actual, ui.SCRIPT_HASH)

    def test_all_write_routes_methods_and_unknown_routes_are_rejected(self):
        url = '/runs/'+self.state()['run_id']
        paths = ['/', '/analyze', '/future-api', '/healthz', '/status']
        paths += [url+'/'+a for a in ('task', 'review', 'evidence', 'bind-page', 'remove-source', 'confirm', 'generate', 'feedback')]
        before = deepcopy(self.state())
        for path in paths:
            for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.client.request(method, path, auth=self.auth).status_code, 403)
        self.assertEqual(self.state(), before)
        for path in ('/', url, '/status', '/static/demo.js'):
            for method in ('GET', 'HEAD', 'POST'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.client.request(method, path).status_code, 401)

    def test_no_article_is_fabricated_when_seed_has_no_generated_result(self):
        root = Document(self.page().text).root
        self.assertEqual(root.find_all('article'), [])
        self.assertIn('此演示任务尚无文章正文', root.text())
        self.assertIn(self.state()['task']['title'], root.text())
        self.assertIn('演示环境不执行文章生成', root.text())

    def test_existing_article_text_and_bindings_stay_readable_and_escaped(self):
        state = self.state()
        span = state['spans'][0]
        article = dict(title='Original <title>', paragraphs=[dict(heading='Original heading',
            text='Exact original text <script> and & punctuation.', source_ids=[span['source_id']],
            obligation_ids=[span['obligation_id']])])
        attempt = dict(freshness='STALE', attempt_id='test-only', material={'spans': state['spans']},
                       result={'article': article, 'provider': {'raw_response': 'DO_NOT_DISPLAY_PROVIDER'}})
        with patch.object(self.app.state.workflow, 'result', return_value=attempt):
            root = Document(self.page().text).root
        body = root.find_all('article')[0]
        self.assertIn(article['title'], body.text(visible=True))
        self.assertIn(article['paragraphs'][0]['text'], body.text(visible=True))
        self.assertIn(span['source_id'], body.text())
        self.assertIn(span['obligation_id'], body.text())
        self.assertIn('资料已变化', root.text())
        self.assertNotIn('DO_NOT_DISPLAY_PROVIDER', root.text())
        self.assertEqual(body.find_all('script'), [])
        self.assertTrue(all('open' not in d.attrs for d in body.find_all('details')))

    def test_changed_requirements_and_quotes_cannot_reuse_demo_translation(self):
        state = deepcopy(self.state())
        state['task']['required_facts'][0] = 'A different requirement <script>'
        span = next(s for s in state['spans'] if s['obligation_id'] == 'fact-1')
        span['quote'] = 'Different supplied evidence <script>'
        root = Document(ui.task_view(state, None)).root
        item = root.find_all('section', id='review-fact-1')[0]
        self.assertNotIn(ui.COPY['fact-1'][2], item.text())
        self.assertNotIn(ui.COPY['fact-1'][5], item.text())
        self.assertIn(span['quote'], item.text())
        self.assertEqual(item.find_all('script'), [])

    def test_empty_and_unconfigured_states_have_no_fake_navigation_or_actions(self):
        self.assertIn('暂无演示任务', ui.home([]))
        self.assertNotIn('体验演示任务', ui.home([]))
        state = deepcopy(self.state())
        state['task'] = None
        self.assertIn('暂时没有可核对事项', ui.task_view(state, None))
        self.assertNotIn('data-next', ui.task_view(state, None))

    def test_different_item_counts_and_missing_evidence_use_actual_state(self):
        state = deepcopy(self.state())
        state['task']['required_facts'] = state['task']['required_facts'][:1]
        state['spans'] = []
        root = Document(ui.task_view(state, None)).root
        self.assertEqual(len(root.find_all('section', **{'class': 'review-item'})), 4)
        self.assertEqual(root.text().count('暂无引用资料，无法判断是否支持'), 4)
        self.assertNotIn('1 / 5', root.text())


if __name__ == '__main__':
    unittest.main()
