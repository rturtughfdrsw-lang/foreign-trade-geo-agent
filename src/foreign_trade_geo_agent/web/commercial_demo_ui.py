"""Read-only presentation. Navigation never submits, stores or reviews anything."""
import base64
import hashlib

from foreign_trade_geo_agent.core.commercial_preview import digest, sha, task_from
from foreign_trade_geo_agent.web.commercial_preview_ui import (
    STATUSES, details, esc, obligation_copy, source_display,
)


NOTICE = '当前为只读演示环境，使用虚构资料；真实分析、保存和发布功能尚未开放。'

# Exact requirements and exact quote hashes guard display translations. These
# strings are never supplied to the workflow or used to decide evidence support.
COPY = {
    'reader-question': (
        'What does Aster supply and what must a buyer confirm?',
        '这篇文章要回答什么问题？',
        'Aster 提供什么产品？采购前还需要确认哪些事项？',
        '核对产品介绍与采购条件，避免把供应商描述当作项目适用性的证明。',
        '7ce10e50f482d6c4f43688a0a43b0e3ec8207af128b95bd5fd642c89cf1448d8',
        '资料介绍了用于工业设备项目的不锈钢外壳，以及按客户图纸讨论加工范围的方式。具体设计、用途和项目适用性仍需另行确认。',
    ),
    'fact-1': (
        'Describe the enclosure product.', '产品是什么？',
        '介绍不锈钢外壳本身，不把它写成整套设备。',
        '核对材料与产品边界；产品介绍不等于周边设备已获认可。',
        'c26c2d0e2091a9d02fb70853e6dfab1845db49339fc73707e1559c0d39d3a2d1',
        '资料描述的是不锈钢制成的外壳，加工范围取决于客户图纸和双方约定；它并不是完整的已安装设备系统。',
    ),
    'fact-2': (
        'Describe the fabrication capability.', '资料描述了哪些加工能力？',
        '核对切割、折弯和焊接的描述及其适用范围。',
        '不要据此推断加工精度、产能、认证或交付承诺。',
        'e51faff02b4e95fd326396d1e77554d25553e5443e619883a2567c308e53e3f9',
        '资料列出不锈钢板材的切割、折弯与焊接，按已审阅的图纸讨论加工范围；没有证实公差、产能、检验认证或交期。',
    ),
    'scope': (
        'Aster stainless steel enclosure fabrication for reviewed industrial equipment drawings.',
        '这篇文章的介绍范围是什么？',
        '仅介绍依据已审阅客户图纸进行的不锈钢外壳加工。',
        '区分外壳加工与设备设计、电气装配、安装和整机验证。',
        '3be01b0e5940dc91c711b1f28e031b7dd25b2b89f53a5189ab51e7763f560255',
        '资料范围限于工业设备项目的外壳与加工活动，不包括设备设计批准、电气装配、安装或成品设备验证。',
    ),
    'limitations': (
        'Project-specific suitability, ratings and delivery must be separately confirmed.',
        '哪些事项仍需另外确认？',
        '项目适用性、等级要求和交付安排需要另行确认。',
        '保留这些限制，不把未获证实的条件写成承诺。',
        'd69f11c239d38a97fbc6097cf9608ac93654202e63738f90fd6992e34e41cbb2',
        '现有资料未证实环境等级、法规认证、特定安装适用性、交付时间或性能保证，需要相应项目文件另行确认。',
    ),
}

STYLE = '''
:root{color-scheme:light;--ink:#1c302c;--muted:#566761;--line:#dce4e0;--accent:#176654}
*{box-sizing:border-box}body{margin:0;background:#f6f8f7;color:var(--ink);font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}
[hidden]{display:none!important}a{color:var(--accent);text-underline-offset:4px}h1,h2,h3,p,summary,a,blockquote,pre{overflow-wrap:anywhere}
h1{font-size:32px;line-height:1.3;letter-spacing:-.6px;margin:0 0 14px}h2{font-size:22px;line-height:1.5;margin:0 0 12px}h3{font-size:17px;margin:0 0 8px}p{margin:0 0 14px}
.shell{max-width:1100px;margin:auto;padding:0 40px}.topbar{background:white;border-bottom:1px solid var(--line)}.topbar .shell{display:flex;align-items:center;justify-content:space-between;gap:24px;min-height:72px}
.brand{font-weight:650;color:var(--ink);text-decoration:none}.topbar nav{display:flex;gap:24px;align-items:center}.mode,.muted{color:var(--muted)}.mode{font-size:14px}
main{min-height:calc(100svh - 180px);padding-top:36px!important;padding-bottom:40px!important}.hero{padding:40px 0 36px;max-width:750px}.lead{font-size:18px;color:var(--muted)}.eyebrow{color:var(--muted);font-size:14px;margin-bottom:10px}
.demo-task{background:white;border:1px solid var(--line);border-radius:8px;padding:28px 32px;display:flex;justify-content:space-between;align-items:center;gap:32px}.demo-task p:last-child{margin:0}.demo-task h2{font-size:21px}.demo-task .primary{flex-shrink:0}
.primary,button{font:inherit;border-radius:5px;padding:10px 20px;cursor:pointer;text-decoration:none;display:inline-block;line-height:1.5}.primary{color:white;background:var(--accent);border:1px solid var(--accent);font-weight:600}.primary:hover{background:#104c3e}
button{color:var(--ink);background:white;border:1px solid #bacac2}button:hover:not(:disabled){background:#edf4f0}button:disabled{cursor:default;color:#65736e;background:#f1f4f2;border-color:#dce4e0}
:focus-visible{outline:3px solid #2472ba;outline-offset:4px}.skip{position:absolute;left:16px;top:-100px;background:white;padding:10px;z-index:2}.skip:focus{top:12px}
.footer{border-top:1px solid var(--line);padding-top:18px;padding-bottom:22px;color:var(--muted);font-size:14px}.footer p{margin-bottom:0}.footer details{margin:4px 0 0}.footer summary{font-size:13px}
.task-heading h1{font-size:28px;margin-bottom:8px}.task-heading p{margin-bottom:18px}.tabs{display:flex;gap:24px;border-bottom:1px solid var(--line);margin:22px 0 24px}.tabs button{border:0;border-radius:0;background:transparent;padding:10px 0;color:var(--muted)}.tabs [aria-selected=true]{color:var(--accent);border-bottom:3px solid var(--accent);font-weight:650}
.review-workspace{max-width:880px;margin:0 auto}.review-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:16px}.review-toolbar h2{font-size:18px;margin:0}.paging{display:flex;align-items:center;gap:14px}.paging button{padding:8px 16px;min-height:44px}.paging output{font-variant-numeric:tabular-nums;white-space:nowrap;min-width:48px;text-align:center}
.review-item{background:white;border:1px solid var(--line);border-radius:8px;padding:28px 32px;min-height:350px}.item-top{display:flex;justify-content:space-between;align-items:start;gap:20px;margin-bottom:12px}.item-top h3{font-size:23px;line-height:1.5;margin:0}.status{font-size:14px;color:var(--muted);flex-shrink:0;padding-top:4px}.tip{font-size:14px;color:var(--muted);margin-bottom:22px}.support{border-top:1px solid var(--line);padding-top:18px}.support strong{font-weight:600}.support p{margin:8px 0 12px}
details{margin:12px 0}summary{color:var(--accent);cursor:pointer;padding:5px 0}details[open]>summary{margin-bottom:12px}.evidence{border-left:2px solid var(--line);padding-left:18px;margin:14px 0 20px}.evidence p{margin:6px 0 12px}blockquote{margin:12px 0;white-space:pre-wrap}pre{font:13px/1.65 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7f5;padding:16px}small{font-size:14px}.review-note{font-size:14px;color:var(--muted);margin:14px 0 0}
.reading{max-width:760px;margin:0 auto;background:white;padding:30px 36px;border:1px solid var(--line);border-radius:8px}.reading h2{font-size:27px;line-height:1.4}.reading h3{font-size:20px;margin-top:26px}.reading p{line-height:1.9}.reading article{font-size:18px}.reading article h3{margin-top:32px}.empty{padding:12px 0}.technical{max-width:880px;margin:24px auto 0;font-size:14px}.source-label{font-size:14px;color:var(--muted)}
@media(max-width:640px){.shell{padding-left:20px;padding-right:20px}.topbar .shell{min-height:62px;gap:12px}.topbar nav{gap:16px}.hero{padding:16px 0 24px}h1{font-size:28px}.lead{font-size:16px}.demo-task{padding:22px;display:block}.demo-task .primary{margin-top:22px;width:100%;text-align:center}.task-heading h1{font-size:25px}main{padding-top:24px!important}.review-toolbar{align-items:start;flex-direction:column;gap:12px}.paging{width:100%;justify-content:space-between;gap:8px}.review-item{padding:22px 20px;min-height:350px}.item-top{flex-direction:column;gap:6px}.item-top h3{font-size:21px}.status{padding:0}.reading{padding:24px 20px}.reading h2{font-size:24px}.tabs{margin-top:16px}.footer{font-size:13px}}
'''

# A single constant script is allowed by its exact CSP hash. No network calls,
# URL mutations, storage, inline event handlers or task data interpolation.
SCRIPT = '''(() => {
  const workspace = document.querySelector('[data-review-workspace]');
  if (workspace) {
    const items = Array.from(workspace.querySelectorAll('[data-review-item]'));
    const toolbar = workspace.querySelector('[data-paging]');
    const previous = workspace.querySelector('[data-previous]');
    const next = workspace.querySelector('[data-next]');
    const position = workspace.querySelector('output');
    let current = 0;
    const show = (index) => {
      current = Math.max(0, Math.min(items.length - 1, index));
      items.forEach((item, i) => {
        item.hidden = i !== current;
        if (i !== current) item.querySelectorAll('details[open]').forEach(d => d.open = false);
      });
      position.textContent = `${current + 1} / ${items.length}`;
      position.setAttribute('aria-label', `第 ${current + 1} 项，共 ${items.length} 项：${items[current].querySelector('h3').textContent}`);
      previous.disabled = current === 0;
      next.disabled = current === items.length - 1;
      const active = document.activeElement;
      if (active === previous && previous.disabled && !next.disabled) next.focus({preventScroll: true});
      if (active === next && next.disabled && !previous.disabled) previous.focus({preventScroll: true});
    };
    if (items.length) {
      toolbar.hidden = false;
      previous.addEventListener('click', () => show(current - 1));
      next.addEventListener('click', () => show(current + 1));
      show(0);
    }
  }
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const activate = (tab) => {
    tabs.forEach(t => {
      const selected = t === tab;
      t.setAttribute('aria-selected', String(selected));
      t.tabIndex = selected ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !selected;
    });
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', event => {
      let target;
      if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
      if (event.key === 'ArrowLeft') target = tabs[(index + tabs.length - 1) % tabs.length];
      if (event.key === 'Home') target = tabs[0];
      if (event.key === 'End') target = tabs[tabs.length - 1];
      if (target) { event.preventDefault(); activate(target); target.focus({preventScroll: true}); }
    });
  });
  if (tabs.length) {
    document.querySelector('[role="tablist"]').hidden = false;
    activate(tabs[0]);
  }
})();'''

SCRIPT_HASH = base64.b64encode(hashlib.sha256(SCRIPT.encode('utf-8')).digest()).decode('ascii')
CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-" + SCRIPT_HASH
       + "'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")


def page(body, root=''):
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>SEO 内容工作台 · 只读演示</title><style>'+STYLE+'</style></head><body>'
            '<a class="skip" href="#main">跳到主要内容</a><header class="topbar"><div class="shell">'
            '<a class="brand" href="'+esc(root+'/')+'">外贸 SEO</a>'
            '<nav aria-label="主导航"><a href="'+esc(root+'/')+'">工作台</a><span class="mode">只读演示</span></nav>'
            '</div></header><main class="shell" id="main">'+body+'</main>'
            '<footer class="shell footer"><p>'+NOTICE+'</p><details><summary>环境说明</summary>'
            '<p>演示资料会在重启、休眠或重新部署后重建，不会永久保存。</p></details></footer>'
            '<script>'+SCRIPT+'</script></body></html>')


def task_title(state):
    title = (state.get('task') or state['analysis'].get('topic') or {}).get('title', '尚未选择文章主题')
    if title == 'Aster Stainless Steel Enclosures: A Factual Overview':
        return 'Aster 不锈钢外壳：产品与加工介绍'
    return title


def home(states, root=''):
    content = ('<div class="hero"><p class="eyebrow">面向外贸企业的内容准备与审核</p>'
               '<h1>SEO 内容工作台</h1><p class="lead">整理网站资料，逐项核对事实，为英文 SEO 文章做好准备。</p></div>')
    if not states:
        return content+'<h2>暂无演示任务</h2><p>演示资料尚未准备好，请稍后刷新页面。</p>'
    for index, state in enumerate(states):
        content += ('<section class="demo-task"><div><p class="eyebrow">演示任务 · 虚构企业资料</p>'
                    '<h2>'+esc(task_title(state))+'</h2><p class="muted">查看文章要求与引用资料，体验逐项事实核对。</p></div>'
                    '<a class="'+('primary' if index == 0 else 'secondary')+'" href="'
                    +esc(root+'/runs/'+state['run_id'])+'">'+('体验演示任务' if index == 0 else '查看此任务')+'</a></section>')
    return content


def display_copy(task, key):
    copy = COPY.get(key)
    if copy and task.obligations[key] == copy[0]:
        return dict(title=copy[1], description=copy[2], tip=copy[3])
    return obligation_copy(task, key)


def evidence(state, key, selected):
    content = ''
    for number, span in enumerate(selected, 1):
        source = next(s for s in state['sources'] if s['source_id'] == span['source_id'])
        copy = COPY.get(key)
        summary = copy[5] if copy and sha(span['quote']) == copy[4] else span['quote'][:180]+('…' if len(span['quote']) > 180 else '')
        display = source_display(state, source)
        label = '虚构演示资料' if source['data_kind'] == 'SYNTHETIC' else display['label']
        content += ('<div class="evidence"><span class="source-label">证据 '+str(number)+' · '+esc(label)+'</span>'
                    '<p>'+esc(summary)+'</p><details><summary>查看完整原文与来源</summary>'
                    '<h3>本项引用</h3><blockquote lang="en">'+esc(span['quote'])+'</blockquote>'
                    '<p>来源：'+esc(source['label'])+'<br>原始位置：'+esc(source['locator'])+'</p>')
        if display['url']:
            content += '<a href="'+esc(display['url'])+'" target="_blank" rel="noopener noreferrer">打开来源页面（新窗口）</a>'
        content += ('<details><summary>查看保存的来源全文</summary><blockquote>'+esc(source['content'])+'</blockquote></details>'
                    +details('引用关系与技术详情', dict(source=source, span=span))+'</details></div>')
    return content


def article_content(state, task, attempt):
    result = (attempt or {}).get('result') or {}
    article = result.get('article')
    content = '<div class="reading">'
    if article:
        content += '<p class="eyebrow">英文草稿 · 仍需人工核对，尚未获得生产发布授权</p>'
        if attempt['freshness'] == 'STALE':
            content += '<p role="status">资料已变化：以下为保留的旧版草稿，不能视为基于当前资料。</p>'
        content += '<article lang="en"><h2>'+esc(article['title'])+'</h2>'
        for paragraph in article['paragraphs']:
            content += ('<h3>'+esc(paragraph['heading'])+'</h3><p>'+esc(paragraph['text'])+'</p>'
                        +details('查看段落引用关系', dict(source_ids=paragraph['source_ids'], obligation_ids=paragraph['obligation_ids'])))
        content += '</article>'
    else:
        content += ('<h2>文章内容</h2><p class="empty">此演示任务尚无文章正文。</p>'
                    '<p class="muted">当前展示的是写作要求和待核对资料。演示环境不执行文章生成。</p>'
                    '<h3>文章标题</h3><p>'+esc(task.title)+'</p>')
        for key in ('reader-question', 'scope', 'limitations'):
            content += '<h3>'+esc(display_copy(task, key)['title'])+'</h3><p>'+esc(display_copy(task, key)['description'])+'</p>'
    if result.get('raw'):
        content += '<details><summary>查看保留原稿</summary><pre>'+esc(result['raw'])+'</pre></details>'
    if attempt:
        content += details('查看草稿审核与来源记录', {k: v for k, v in attempt.items() if k != 'result'})
        content += details('查看草稿状态', {k: v for k, v in result.items() if k not in {'article', 'raw', 'provider'}})
    return content+'</div>'


def task_view(state, attempt):
    content = '<div class="task-heading"><p class="eyebrow">演示任务 · 虚构企业资料</p><h1>'+esc(task_title(state))+'</h1></div>'
    if not state['task']:
        return content+'<p>此任务尚未设置文章要求，暂时没有可核对事项。</p>'
    task = task_from(state['task'])
    content += ('<div class="tabs" role="tablist" aria-label="任务内容" hidden>'
                '<button type="button" role="tab" id="review-tab" aria-controls="review-panel" aria-selected="true">事实核对</button>'
                '<button type="button" role="tab" id="article-tab" aria-controls="article-panel" aria-selected="false" tabindex="-1">文章内容</button></div>'
                '<noscript><p>浏览器未启用交互，可在下方逐项阅读全部资料。</p></noscript>'
                '<div id="review-panel" role="tabpanel" aria-labelledby="review-tab" tabindex="0">'
                '<div class="review-workspace" data-review-workspace>'
                '<div class="review-toolbar"><h2>逐项核对资料</h2><div class="paging" data-paging hidden>'
                '<button type="button" data-previous disabled>上一项</button>'
                '<output aria-live="polite" aria-atomic="true"></output>'
                '<button type="button" data-next>下一项</button></div></div>')
    reviews = {r['obligation_id']: r for r in state['reviews']}
    for key in task.obligations:
        copy = display_copy(task, key)
        selected = [span for span in state['spans'] if span['obligation_id'] == key]
        review = reviews.get(key)
        status = STATUSES[review['verdict']] if review else '尚未核对'
        content += ('<section class="review-item" data-review-item id="review-'+esc(key)+'" aria-labelledby="question-'+esc(key)+'">'
                    '<div class="item-top"><h3 id="question-'+esc(key)+'">'+esc(copy['title'])+'</h3>'
                    '<span class="status">'+status+'</span></div><p>'+esc(copy['description'])+'</p>'
                    '<p class="tip">'+esc(copy['tip'])+'</p><div class="support"><strong>资料支持情况</strong>'
                    '<p class="muted">'+('已有 '+str(len(selected))+' 条引用资料；是否足以支持这项写法，仍需人工判断。' if selected else '暂无引用资料，无法判断是否支持这项写法。')+'</p>'
                    +evidence(state, key, selected)+'</div><details><summary>查看原始要求与核对记录</summary>'
                    '<blockquote lang="en">'+esc(task.obligations[key])+'</blockquote>'
                    +details('核对记录', review)+'</details></section>')
    content += ('<p class="review-note">可切换事项、展开原文。这里不提交核对结论，浏览进度不代表已完成审核。</p>'
                '</div></div><div id="article-panel" role="tabpanel" aria-labelledby="article-tab" tabindex="0">'
                +article_content(state, task, attempt)+'</div>')
    content += '<div class="technical">'+details('查看任务与资料记录', dict(task=state['task'], revision=state['revision'],
        state_digest=digest(state), production_authorized=state['production_authorized'], analysis=state['analysis'], sources=state['sources']))+'</div>'
    return content
