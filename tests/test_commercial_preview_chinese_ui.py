"""Chinese customer view against fictional saved pages and temporary SQLite only."""
import asyncio
from copy import deepcopy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from foreign_trade_geo_agent.commercial_preview_runtime import build_preview_runtime
from foreign_trade_geo_agent.core.commercial_preview import (
    digest, evidence_digest, request_digest, task_from,
)
from foreign_trade_geo_agent.web.commercial_preview import create_preview_app
from foreign_trade_geo_agent.web.commercial_preview_ui import source_display
from tests.test_commercial_preview import Forms


HOME = 'https://novacnc.example/'
PRODUCT = HOME+'products/cnc-milling-machine/'
HOME_QUOTE = ('NovaCNC Machinery is a demonstration catalogue presenting CNC metalworking equipment '
              'information for overseas manufacturers, fabricators, industrial companies, and distribution partners.')
PRODUCT_QUOTE = ('CNC milling machines use rotating cutting tools and controlled axis motion to produce '
                 'flat surfaces, pockets, slots, contours, and drilled features.')
SPEC_QUOTE = ('These values illustrate the fields commonly reviewed during early equipment comparison. '
              'Demonstration specifications Illustrative values for website evaluation only. '
              'Final machine data would depend on the selected model and configuration.')
TRANSCRIPT_LABEL = ('REAL crawl snapshot transcript: Sample Technical Specifications '
                    '(automatic preparation; no human review)')
TASK = dict(
    title='NovaCNC Demonstration Catalogue: CNC Milling Machines — A Factual Overview',
    reader_question='What does the NovaCNC demonstration catalogue say about CNC milling machines, and what does this sample establish?',
    required_facts=(
        'Identify NovaCNC Machinery as a demonstration catalogue of CNC metalworking equipment information.',
        "Describe the catalogue's CNC milling process: rotating cutting tools and controlled axis motion producing flat surfaces, pockets, slots, contours and drilled features.",
    ),
    scope='A factual description of the CNC milling category in the NovaCNC demonstration catalogue, based only on the selected current website samples and reviewed exact fragments.',
    limitations='Demonstration information only. Do not present illustrative specifications as current production-model facts or claim verified manufacturing capability, certifications, delivery commitments or suitability for a specific installation.',
)
COPY = {
    'reader-question': (
        '这篇文章要回答什么问题？',
        'NovaCNC 的演示目录如何介绍 CNC 铣床？这些网页内容能够说明什么，又不能证明什么？',
        '请检查引用内容是否足以支持这篇文章的介绍。网站上的描述只能证明网页如此陈述，不代表相关企业能力已获得独立验证。',
    ),
    'fact-1': (
        '网站介绍的是什么？',
        '说明 NovaCNC Machinery 是一个介绍 CNC 金属加工设备信息的演示目录。',
        '可以根据首页原文介绍目录的性质，但不能将它描述成已经认证的真实制造商。',
    ),
    'fact-2': (
        '网站如何描述铣床的工作原理？',
        '介绍目录中关于 CNC 铣削的描述，包括旋转刀具、受控轴运动，以及平面、凹槽、槽口、轮廓和钻孔特征等加工内容。',
        '这里只核对网站对铣床类别的描述，不代表某个具体型号的实测性能。',
    ),
    'scope': (
        '这篇文章的介绍范围是什么？',
        '文章只介绍 NovaCNC 演示目录中的 CNC 铣床类别，并且只依据本次选定的网页样本和引用片段。',
        '每条引用都需要实际核对。不能将通用类别介绍扩展成具体型号能力、安装适用性或其他未经证实的承诺。',
    ),
    'limitations': (
        '哪些内容不能当作已验证的事实？',
        '文章只能介绍演示资料。不能把示例规格写成当前量产型号的真实参数，也不能声称制造能力、认证、交付承诺或特定安装适用性已经得到验证。',
        '示例参数应明确标注。只有获得相应资料支持并完成必要核对后，才考虑加入其他具体承诺。',
    ),
}


class Element:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find_all(self, tag=None, **attrs):
        found = []
        if (tag is None or self.tag == tag) and all(self.attrs.get(k) == v for k, v in attrs.items()):
            found.append(self)
        for child in self.children:
            if isinstance(child, Element):
                found.extend(child.find_all(tag, **attrs))
        return found

    def text(self, *, visible=False):
        if visible and (self.tag in {'style', 'script', 'template'} or 'hidden' in self.attrs):
            return ''
        children = self.children
        if visible and self.tag == 'details' and 'open' not in self.attrs:
            children = [c for c in children if isinstance(c, Element) and c.tag == 'summary'][:1]
        return ' '.join(c.text(visible=visible) if isinstance(c, Element) else c for c in children)


class Document(HTMLParser):
    """Read actual HTML including which text is hidden inside native details."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.root = Element('document')
        self.stack = [self.root]
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


class ChineseReviewUITests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.flow = build_preview_runtime(self.directory)
        # REAL is a contract fixture value here, never a request to a live website.
        pages = [
            dict(title='CNC Machinery for Global Manufacturing | NovaCNC Machinery', final_url=HOME,
                 body_text=HOME_QUOTE, structured_content=[]),
            dict(title='CNC Milling Machines | NovaCNC Machinery', final_url=PRODUCT,
                 body_text=PRODUCT_QUOTE, structured_content=[dict(kind='section',
                     heading='Sample Technical Specifications', text=SPEC_QUOTE, rows=[], pairs=[], items=[])]),
        ]
        analysis = dict(website=PRODUCT, data_kind='REAL', research='NOT_RUN', serp='NOT_RUN',
            topic=dict(title=TASK['title'], subject='CNC Milling Machines'), no_topic_reason='',
            content=dict(pages=pages), crawl=dict(pages=[]), audit='Fictional offline page fixture.')
        with patch.object(self.flow.analyzer, 'analyze', new=AsyncMock(return_value=analysis)):
            state = asyncio.run(self.flow.analyze(PRODUCT))
        state = self.flow.confirm_task(*self.args(state), **TASK)
        sources = {s['locator']: s['source_id'] for s in state['sources']}
        for key, url, quote in (
            ('reader-question', HOME, HOME_QUOTE), ('reader-question', PRODUCT, PRODUCT_QUOTE),
            ('fact-1', HOME, HOME_QUOTE), ('fact-2', PRODUCT, PRODUCT_QUOTE),
            ('scope', HOME, HOME_QUOTE), ('scope', PRODUCT, PRODUCT_QUOTE),
        ):
            state = self.flow.bind_page(*self.args(state), source_id=sources[url], obligation_id=key, quote=quote)
        state = self.flow.supplement(*self.args(state), obligation_id='limitations', content=SPEC_QUOTE,
                                     label=TRANSCRIPT_LABEL, locator=PRODUCT)
        self.run = state['run_id']
        self.url = '/runs/'+self.run
        self.client = self.enterContext(TestClient(create_preview_app(self.flow), base_url='http://127.0.0.1:8017'))

    @staticmethod
    def args(state):
        return state['run_id'], state['revision'], digest(state)

    def state(self):
        return self.flow.store.read(self.run)

    def page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response, Document(response.text).root

    def card(self, root, key):
        cards = root.find_all('section', id='review-'+key)
        self.assertEqual(len(cards), 1)
        return cards[0]

    def submit(self, key='reader-question', verdict='SUPPORTED', **overrides):
        fields = Forms(self.client.get(self.url).text).forms[self.url+'/review']
        fields.update(obligation_id=key, verdict=verdict, note='已核对两段原文 <script> & 适用范围',
            review_ack='LOCAL_PREVIEW_REVIEW',
            span_id=[s['span_id'] for s in self.state()['spans'] if s['obligation_id'] == key])
        fields.update(overrides)
        return self.client.post(self.url+'/review', data=fields, follow_redirects=False)

    def test_five_customer_questions_explanations_and_instructions(self):
        _, root = self.page()
        for key, expected in COPY.items():
            with self.subTest(key=key):
                text = self.card(root, key).text(visible=True)
                for sentence in expected:
                    self.assertIn(sentence, text)
        visible = root.text(visible=True)
        self.assertIn('目标文章语言：英文', visible)
        self.assertIn('当前阶段：资料与事实核对', visible)
        self.assertIn('已核对 0/5 项', visible)
        self.assertIn('阅读引用', visible)
        self.assertIn('单独确认', visible)

    def test_original_english_is_exact_and_only_in_closed_traceability(self):
        _, root = self.page()
        for key, original in task_from(self.state()['task']).obligations.items():
            with self.subTest(key=key):
                card = self.card(root, key)
                blocks = [node for node in card.find_all('details')
                          if any(s.text() == '查看原始英文要求' for s in node.find_all('summary'))]
                self.assertEqual(len(blocks), 1)
                self.assertNotIn('open', blocks[0].attrs)
                self.assertIn(original, blocks[0].text())
                self.assertNotIn(original, card.text(visible=True))

    def test_customer_default_hides_internal_terms_but_retains_metadata(self):
        response, root = self.page()
        visible = root.text(visible=True)
        for token in ('reader-question', 'fact-1', 'fact-2', 'SUPPORTED_CANDIDATE', 'UNREVIEWED',
                      'LOCAL_DOCUMENT', 'REAL crawl snapshot', 'span_id', 'evidence_digest',
                      'revision', 'LOCAL_PREVIEW_REVIEW', 'production_authorized'):
            with self.subTest(token=token):
                self.assertNotIn(token, visible)
        for token in ('scope', 'limitations', 'SUPPORTED', 'REAL'):
            self.assertNotRegex(visible, r'\b'+token+r'\b')
        state = self.state()
        for value in (state['run_id'], state['task']['task_id'], digest(state), evidence_digest(state),
                      *(s['source_id'] for s in state['sources']), *(s['span_id'] for s in state['spans'])):
            self.assertNotIn(value, visible)
            self.assertIn(value, response.text)
        for label in ('资料与来源管理', '补充资料', '任务设置', '技术详情'):
            self.assertTrue(any(label in node.text() for node in root.find_all('summary')), label)

    def test_crawl_source_names_urls_preview_and_exact_full_original(self):
        _, root = self.page()
        reader = self.card(root, 'reader-question')
        limitations = self.card(root, 'limitations')
        self.assertIn('网站首页介绍', reader.text(visible=True))
        self.assertIn('CNC 铣床产品页原文', reader.text(visible=True))
        self.assertEqual({a.attrs['href'] for a in reader.find_all('a')}, {HOME, PRODUCT})
        self.assertIn('产品页规格说明摘录（来自本次网页抓取）', limitations.text(visible=True))
        provenance = limitations.text(visible=True)
        for phrase in ('本地文本摘录', '同一次', '不是独立'):
            self.assertIn(phrase, provenance)
        self.assertIn(PRODUCT, {a.attrs.get('href') for a in limitations.find_all('a')})
        for card, quotes in ((reader, (HOME_QUOTE, PRODUCT_QUOTE)), (limitations, (SPEC_QUOTE,))):
            blocks = [node for node in card.find_all('details')
                      if any(s.text() == '查看完整原文' for s in node.find_all('summary'))]
            for quote in quotes:
                self.assertTrue(any(quote in b.text() for b in blocks))
                self.assertIn(quote[:100], card.text(visible=True))
            self.assertTrue(all('open' not in b.attrs for b in blocks))

    def test_ordinary_local_document_cannot_claim_same_crawl_from_label_and_url(self):
        state = self.state()
        self.flow.supplement(*self.args(state), obligation_id='fact-1',
            content='A separately supplied note with no matching text in the saved website sample.',
            label=TRANSCRIPT_LABEL, locator=PRODUCT)
        _, root = self.page()
        card = self.card(root, 'fact-1')
        self.assertNotIn('产品页规格说明摘录（来自本次网页抓取）', card.text(visible=True))
        self.assertNotIn('同一次网页抓取中保存', card.text(visible=True))
        self.assertIn('补充资料', card.text(visible=True))

    def test_matching_text_without_crawl_record_label_remains_supplied_material(self):
        state = self.state()
        self.flow.supplement(*self.args(state), obligation_id='fact-1', content=SPEC_QUOTE,
                             label='Owner supplied comparison note', locator=PRODUCT)
        _, root = self.page()
        card = self.card(root, 'fact-1')
        self.assertIn('本地补充资料', card.text(visible=True))
        self.assertNotIn('产品页规格说明摘录（来自本次网页抓取）', card.text(visible=True))
        self.assertIn(SPEC_QUOTE, card.text())

    def test_milling_title_on_blog_page_does_not_claim_product_page_provenance(self):
        state = self.state()
        source = deepcopy(next(s for s in state['sources'] if s['locator'] == PRODUCT))
        for path in ('blog/cnc-milling-machines/', 'guides/cnc-milling-machines/'):
            with self.subTest(path=path):
                source['locator'] = HOME+path
                before = deepcopy(source)
                display = source_display(state, source)
                self.assertEqual(display['label'], '网站页面原文')
                self.assertEqual(display['url'], source['locator'])
                self.assertNotIn('产品页', display['label'])
                self.assertEqual(source, before)

    def test_each_removal_form_has_matching_original_source_details(self):
        state = self.state()
        for name in ('first', 'second'):
            state = self.flow.supplement(*self.args(state), obligation_id='fact-1',
                content='Offline supplied document '+name, label='Original source '+name,
                locator='local://'+name)
        sources = {s['source_id']: s for s in state['sources']}
        _, root = self.page()
        removals = root.find_all('details', **{'class': 'danger'})
        self.assertEqual(len(removals), len(sources))
        matched = set()
        for disclosure in removals:
            self.assertNotIn('open', disclosure.attrs)
            forms = disclosure.find_all('form', action=self.url+'/remove-source')
            self.assertEqual(len(forms), 1)
            source_fields = forms[0].find_all('input', name='source_id')
            self.assertEqual(len(source_fields), 1)
            source_id = source_fields[0].attrs['value']
            self.assertNotIn(source_id, matched)
            matched.add(source_id)
            source = sources[source_id]
            technical = [node for node in disclosure.find_all('details')
                         if any(isinstance(c, Element) and c.tag == 'summary'
                                and c.text() == '技术详情：待移除来源' for c in node.children)]
            self.assertEqual(len(technical), 1)
            self.assertNotIn('open', technical[0].attrs)
            self.assertEqual(json.loads(technical[0].find_all('pre')[0].text()), source)
            for field in ('label', 'locator', 'source_id'):
                self.assertIn(source[field], technical[0].text())
        self.assertEqual(matched, set(sources))
        self.assertEqual(self.state(), state)

    def test_saved_verdict_note_and_both_selections_restore_without_implicit_ack(self):
        for verdict, label in (
            ('SUPPORTED', '已核对：证据支持这项写法'),
            ('CONFLICT', '已核对：发现证据冲突'),
            ('UNRESOLVED', '已核对：暂时无法判断'),
        ):
            with self.subTest(verdict=verdict):
                response = self.submit(verdict=verdict)
                self.assertEqual(response.status_code, 303)
                page = self.client.get(response.headers['location'])
                root = Document(page.text).root
                card = self.card(root, 'reader-question')
                self.assertIn('已保存本项核对。', root.text(visible=True))
                self.assertIn(label, card.text(visible=True))
                selected = [o.attrs['value'] for o in card.find_all('option') if 'selected' in o.attrs]
                self.assertEqual(selected, [verdict])
                spans = card.find_all('input', name='span_id')
                self.assertEqual({s.attrs['value'] for s in spans if 'checked' in s.attrs},
                                 {s['span_id'] for s in self.state()['spans'] if s['obligation_id'] == 'reader-question'})
                self.assertEqual(len(spans), 2)
                self.assertIn('已核对两段原文 <script> & 适用范围', card.find_all('textarea', name='note')[0].text())
                self.assertEqual(card.find_all('script'), [])
                self.assertTrue(all('checked' not in n.attrs for n in card.find_all('input', name='review_ack')))
                self.assertIn('更新本项核对', card.text(visible=True))
                self.assertIn('已核对 1/5 项', root.text(visible=True))

    def test_unreviewed_items_are_first_and_never_default_to_supported(self):
        self.assertEqual(self.submit().status_code, 303)
        _, root = self.page()
        cards = [node for node in root.find_all('section') if node.attrs.get('id', '').startswith('review-')]
        self.assertEqual([c.attrs['id'] for c in cards],
                         ['review-fact-1', 'review-fact-2', 'review-scope', 'review-limitations', 'review-reader-question'])
        for key in ('fact-1', 'fact-2', 'scope', 'limitations'):
            with self.subTest(key=key):
                card = self.card(root, key)
                self.assertIn('尚未核对', card.text(visible=True))
                self.assertIn('保存本项核对', card.text(visible=True))
                self.assertFalse(any('checked' in n.attrs for n in card.find_all('input')))
                self.assertFalse(any(o.attrs.get('value') in {'SUPPORTED', 'CONFLICT', 'UNRESOLVED'}
                                     and 'selected' in o.attrs for o in card.find_all('option')))

    def test_every_verdict_has_customer_explanation(self):
        _, root = self.page()
        card = self.card(root, 'fact-1')
        options = {o.attrs.get('value'): o.text() for o in card.find_all('option')}
        for value, label in (('SUPPORTED', '证据支持这项写法'), ('CONFLICT', '发现证据冲突'),
                             ('UNRESOLVED', '暂时无法判断')):
            self.assertIn(label, options[value])
        for explanation in ('引用内容足以支持当前限定范围内的表述',
                            '不同来源相互矛盾，或者来源与拟写内容冲突',
                            '证据不足、含义不清或仍需要补充材料'):
            self.assertIn(explanation, card.text(visible=True))

    def test_failed_save_gives_reason_without_success_or_changed_review(self):
        self.assertEqual(self.submit().status_code, 303)
        before = self.state()
        cases = (
            (dict(span_id=[]), '全部'),
            (dict(review_ack=''), '勾选'),
            (dict(note=''), '意见'),
            (dict(state_digest='0'*64), '过期'),
        )
        for fields, reason in cases:
            with self.subTest(fields=fields):
                response = self.submit(**fields)
                self.assertEqual(response.status_code, 409)
                visible = Document(response.text).root.text(visible=True)
                self.assertIn('未保存', visible)
                self.assertIn(reason, visible)
                self.assertNotIn('已保存本项核对。', visible)
                self.assertNotIn('PREVIEW_', visible)
                self.assertEqual(self.state(), before)
        with patch.object(self.flow.store, 'save', side_effect=OSError('private secret-bearing path')):
            response = self.submit()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private secret-bearing path', response.text)
        self.assertNotIn('已保存本项核对。', response.text)
        self.assertIn('未确认', Document(response.text).root.text(visible=True))
        self.assertEqual(self.state(), before)

    def test_render_does_not_change_task_evidence_request_review_or_database(self):
        self.assertEqual(self.submit().status_code, 303)
        before = deepcopy(self.state())
        before_hash = hashlib.sha256(self.flow.store.path.read_bytes()).hexdigest()
        bindings = (digest(before['task']), evidence_digest(before), request_digest(before), digest(before))
        with patch.object(self.flow.store, 'save', side_effect=AssertionError('GET must not save')):
            for _ in range(2):
                self.page()
        after = self.state()
        self.assertEqual(after, before)
        self.assertEqual((digest(after['task']), evidence_digest(after), request_digest(after), digest(after)), bindings)
        self.assertEqual(hashlib.sha256(self.flow.store.path.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(after['reviews'][0]['verdict'], 'SUPPORTED')
        self.assertEqual(len(after['reviews']), 1)
        self.assertFalse(after['production_authorized'])
        self.assertIsNone(after['confirmation'])
        self.assertEqual(self.flow.writer.calls, 0)

    def test_all_reviewed_still_requires_new_execution_ack_and_has_no_authority(self):
        for key in COPY:
            self.assertEqual(self.submit(key).status_code, 303)
        response, root = self.page()
        self.assertIn('已核对 5/5 项', root.text(visible=True))
        confirms = root.find_all('form', action=self.url+'/confirm')
        self.assertEqual(len(confirms), 1)
        checkboxes = confirms[0].find_all('input', name='execution_ack')
        self.assertEqual(len(checkboxes), 1)
        self.assertNotIn('checked', checkboxes[0].attrs)
        fields = Forms(response.text).forms[self.url+'/confirm']
        blocked = self.client.post(self.url+'/confirm', data=fields)
        self.assertEqual(blocked.status_code, 409)
        self.assertIsNone(self.state()['confirmation'])
        self.assertFalse(self.state()['production_authorized'])
        self.assertEqual(self.flow.writer.calls, 0)

    def test_generated_preview_statuses_stay_chinese_and_unauthorized(self):
        attempt = dict(attempt_id='offline-presentation-fixture', freshness='CURRENT', material={},
            result=dict(TECHNICAL='SUCCEEDED', EVIDENCE='NEEDS_REVIEW', EDITORIAL_REVIEW='NEEDS_REVIEW',
                        PRODUCTION_AUTHORIZATION='NOT_AUTHORIZED', production_authorized=False))
        with patch.object(self.flow, 'result', return_value=attempt):
            _, root = self.page()
        # The generation section is secondary; opening it must still present
        # customer language while its raw execution metadata stays folded.
        for node in root.find_all('details'):
            if any(isinstance(c, Element) and c.tag == 'summary'
                   and c.text() == '下一步：生成英文预览草稿' for c in node.children):
                node.attrs['open'] = ''
        visible = root.text(visible=True)
        self.assertIn('仍需人工核对', visible)
        self.assertIn('尚未获得生产发布授权', visible)
        self.assertNotIn('NEEDS_REVIEW', visible)
        self.assertNotIn('NOT_AUTHORIZED', visible)
        self.assertFalse(self.state()['production_authorized'])
        self.assertEqual(self.flow.writer.calls, 0)

    def test_changed_task_does_not_reuse_novacnc_translation_as_a_false_claim(self):
        state = self.state()
        changed = dict(TASK, required_facts=('Describe a newly supplied steel casting fact.', TASK['required_facts'][1]))
        self.flow.confirm_task(*self.args(state), **changed)
        _, root = self.page()
        card = self.card(root, 'fact-1')
        self.assertNotIn(COPY['fact-1'][1], card.text(visible=True))
        self.assertIn(changed['required_facts'][0], card.text())
        self.assertFalse(self.state()['production_authorized'])
