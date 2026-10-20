"""Presentation-only HTML for the local Preview review workspace."""
import html
import json
from urllib.parse import urlsplit

from foreign_trade_geo_agent.core.commercial_preview import digest, evidence_digest, sha

esc = lambda value: html.escape(str(value), quote=True)
STATUSES = {
    'UNREVIEWED': '尚未核对',
    'SUPPORTED': '已核对：证据支持这项写法',
    'CONFLICT': '已核对：发现证据冲突',
    'UNRESOLVED': '已核对：暂时无法判断',
    'NEEDS_REVIEW': '仍需人工核对',
    'NOT_AUTHORIZED': '尚未获得生产发布授权',
}

# These translations are display copy, never inputs to the task or its digests.
# Match the exact requirement as well as its stable ID: an edited task must not
# inherit an explanation that describes a different claim.
OBLIGATION_COPY = {
    'reader-question': (
        'What does the NovaCNC demonstration catalogue say about CNC milling machines, and what does this sample establish?',
        '这篇文章要回答什么问题？',
        'NovaCNC 的演示目录如何介绍 CNC 铣床？这些网页内容能够说明什么，又不能证明什么？',
        '请检查引用内容是否足以支持这篇文章的介绍。网站上的描述只能证明网页如此陈述，不代表相关企业能力已获得独立验证。',
    ),
    'fact-1': (
        'Identify NovaCNC Machinery as a demonstration catalogue of CNC metalworking equipment information.',
        '网站介绍的是什么？',
        '说明 NovaCNC Machinery 是一个介绍 CNC 金属加工设备信息的演示目录。',
        '可以根据首页原文介绍目录的性质，但不能将它描述成已经认证的真实制造商。',
    ),
    'fact-2': (
        "Describe the catalogue's CNC milling process: rotating cutting tools and controlled axis motion producing flat surfaces, pockets, slots, contours and drilled features.",
        '网站如何描述铣床的工作原理？',
        '介绍目录中关于 CNC 铣削的描述，包括旋转刀具、受控轴运动，以及平面、凹槽、槽口、轮廓和钻孔特征等加工内容。',
        '这里只核对网站对铣床类别的描述，不代表某个具体型号的实测性能。',
    ),
    'scope': (
        'A factual description of the CNC milling category in the NovaCNC demonstration catalogue, based only on the selected current website samples and reviewed exact fragments.',
        '这篇文章的介绍范围是什么？',
        '文章只介绍 NovaCNC 演示目录中的 CNC 铣床类别，并且只依据本次选定的网页样本和引用片段。',
        '每条引用都需要实际核对。不能将通用类别介绍扩展成具体型号能力、安装适用性或其他未经证实的承诺。',
    ),
    'limitations': (
        'Demonstration information only. Do not present illustrative specifications as current production-model facts or claim verified manufacturing capability, certifications, delivery commitments or suitability for a specific installation.',
        '哪些内容不能当作已验证的事实？',
        '文章只能介绍演示资料。不能把示例规格写成当前量产型号的真实参数，也不能声称制造能力、认证、交付承诺或特定安装适用性已经得到验证。',
        '示例参数应明确标注。只有获得相应资料支持并完成必要核对后，才考虑加入其他具体承诺。',
    ),
}

STYLE = '''
:root{color-scheme:light;--ink:#20312f;--muted:#596b68;--line:#d9e2df;--accent:#176756}
*{box-sizing:border-box}body{margin:0;background:#f5f7f6;color:var(--ink);font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:960px;margin:auto;padding:32px 28px 64px}header{border-bottom:1px solid var(--line);padding-bottom:20px}
h1{font-size:28px;margin:12px 0 4px}h2{font-size:22px;margin:32px 0 14px}h3{font-size:18px;margin:0 0 12px}h4{font-size:16px;margin:16px 0 8px}h1,h2,h3,h4,a,p,summary,label{overflow-wrap:anywhere}
p{margin:8px 0 14px}a{color:var(--accent);text-underline-offset:3px}small,.muted{color:var(--muted)}
section{background:white;border:1px solid var(--line);border-radius:10px;padding:24px;margin:16px 0;scroll-margin-top:20px}
section:target,.just-saved{outline:3px solid #7cb4a4;outline-offset:3px}.card-heading{display:flex;justify-content:space-between;gap:16px;align-items:start}
.badge{display:inline-block;border-radius:5px;padding:3px 10px;font-size:14px;background:#edf0ef;max-width:100%}.card-heading>*{min-width:0}
.badge.SUPPORTED{background:#e1f1e9;color:#185b45}.badge.CONFLICT{background:#fff0e8;color:#89401f}
.badge.UNRESOLVED{background:#fff4d9;color:#765620}.fact{font-size:17px;overflow-wrap:anywhere}
.overview{margin:24px 0}.overview h2{margin:8px 0}.flow{display:flex;gap:8px;flex-wrap:wrap;padding:0;list-style:none;font-size:14px}
.flow li{padding:5px 10px;border:1px solid var(--line);border-radius:5px}.flow [aria-current]{background:var(--ink);color:white}
.progress-links{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.progress-links a{font-size:14px}
progress{width:100%;height:10px;accent-color:var(--accent)}.notice{padding:14px 18px;border-left:4px solid var(--accent);background:#e7f3ed;margin:18px 0}
details{margin:12px 0}summary{cursor:pointer;color:var(--accent);padding:6px 0}details[open]>summary{margin-bottom:10px}
.evidence{border-left:3px solid var(--line);padding:4px 16px;margin:18px 0}.evidence p{margin-bottom:8px}
blockquote{margin:8px 0;white-space:pre-wrap;overflow-wrap:anywhere}.excerpt{color:var(--muted);font-size:14px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace;background:#f4f6f5;padding:14px;border-radius:5px;max-height:460px;overflow:auto}input,select,textarea{max-width:100%}.source-note,.review-tip,.verdict-help{font-size:14px;color:var(--muted)}.verdict-help{padding-left:22px}.source-text{max-height:440px;overflow:auto}
label{display:block;margin:12px 0}input,select,textarea,button{font:inherit}textarea,input[type=text],select{border:1px solid #a8b9b2;border-radius:5px;padding:10px;background:white;color:var(--ink)}
textarea,input[type=text]{display:block;width:100%}textarea{min-height:90px;resize:vertical}select{display:block;width:100%;max-width:440px;margin-top:6px}
input[type=checkbox]{accent-color:var(--accent);width:18px;height:18px;vertical-align:middle;margin-right:8px}
button{border:0;border-radius:5px;background:var(--accent);color:white;padding:10px 22px;cursor:pointer;margin-top:8px}
button:hover{background:#105143}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #6ba8d8;outline-offset:3px}
.secondary button{color:var(--accent);background:#edf2ef;border:1px solid var(--line)}.danger button{color:#8b3e2d;background:white;border:1px solid #dab3a9;padding:7px 14px;font-size:14px}
.review-form{border-top:1px solid var(--line);padding-top:12px}.review-form .evidence{border-top:0}.review-form button{min-width:140px}
@media(max-width:600px){main{padding:20px 16px 40px}section{padding:18px 16px}.card-heading{flex-wrap:wrap}h1{font-size:25px}.flow{font-size:13px}}
'''


def details(title, value):
    return '<details><summary>'+esc(title)+'</summary><pre>'+esc(json.dumps(value, ensure_ascii=False, indent=2))+'</pre></details>'


def obligation_label(key, task=None):
    if task is not None:
        return obligation_copy(task, key)['title']
    return {'reader-question': '这篇文章要回答什么问题？', 'scope': '这篇文章的介绍范围是什么？',
            'limitations': '哪些内容不能当作已验证的事实？'}.get(key, '需要核对的事实 '+key.removeprefix('fact-'))


def obligation_copy(task, key):
    copy = OBLIGATION_COPY.get(key)
    if copy and task.obligations[key] == copy[0]:
        return dict(title=copy[1], description=copy[2], tip=copy[3])
    return dict(title=obligation_label(key),
                description='请核对这项要求是否得到引用资料的支持。',
                tip='本项尚无匹配的中文说明。请展开原始要求，逐句核对证据、适用范围与限制后再选择结论。')


def _page_url(value):
    """Only render an external link for an explicit, usable HTTP(S) URL."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except (TypeError, ValueError):
        pass
    return ''


def source_display(state, source):
    """Describe provenance from saved content; labels alone are not evidence."""
    url = _page_url(source.get('locator', ''))
    if source.get('source_type') == 'WEBSITE_SAMPLE':
        if url and urlsplit(url).path in {'', '/'}:
            label = '网站首页介绍'
        elif (url and urlsplit(url).path.rstrip('/') == '/products/cnc-milling-machine'
              and 'cnc milling machines' in source.get('label', '').lower()):
            label = 'CNC 铣床产品页原文'
        else:
            label = '网站页面原文'
        return dict(label=label, url=url, note='本次保存的网页样本。网页中的描述仍需逐项核对。')

    analysis = state.get('analysis', {})
    content = source.get('content', '')
    # A local document can be a saved excerpt from the same crawl, but its
    # provider-entered label and URL cannot establish that relationship.
    if (url and content and analysis.get('data_kind') == 'REAL'
            and source.get('data_kind') == 'REAL'
            and source.get('label', '').startswith('REAL crawl snapshot transcript:')
            and source.get('content_sha256') == sha(content)):
        for page in analysis.get('content', {}).get('pages', []):
            if page.get('final_url') != url:
                continue
            retained_page = any(candidate.get('source_type') == 'WEBSITE_SAMPLE'
                                and candidate.get('locator') == url
                                and candidate.get('page_digest') == digest(page)
                                for candidate in state.get('sources', []))
            if not retained_page:
                continue
            for block in page.get('structured_content', []):
                if block.get('text') == content:
                    label = ('产品页规格说明摘录（来自本次网页抓取）'
                             if block.get('heading') == 'Sample Technical Specifications'
                             else '网页文本摘录（来自本次网页抓取）')
                    return dict(label=label, url=url,
                                note='这是从同一次网页抓取中保存的本地文本摘录，与对应网页属于同一来源；不是独立上传文件、第三方证明或独立证据。')
    return dict(label='本地补充资料', url=url,
                note='本地保存的补充资料，尚未确认与本次网页抓取的关系。来源地址由资料提供者填写，不表示已经获得独立证明。')


def overview(state, task, gaps, saved, attempt):
    reviews = {r['obligation_id']: r for r in state['reviews']}
    done = sum(key in reviews for key in task.obligations)
    total = len(task.obligations)
    host = urlsplit(task.website).hostname or task.website
    stage = '英文草稿复核' if attempt else '资料与事实核对'
    content = '<div class="overview"><p class="muted">网站：'+esc(host)+'</p><h2>'+esc(task.title)+'</h2>'
    content += '<p>目标文章语言：英文 · 当前阶段：'+stage+'</p></div>'
    if saved:
        content += '<div class="notice" role="status">已保存本项核对。'+esc(obligation_label(saved, task))+'</div>'
    content += '<h2>已核对 '+str(done)+'/'+str(total)+' 项</h2>'
    content += '<progress aria-label="已保存核对进度" value="'+str(done)+'" max="'+str(total)+'"></progress>'
    content += '<p>你正在检查文章使用的资料。请逐项核对原文，确认引用是否支持对应的说法。全部核对后，还需要单独确认是否进行预览生成。</p>'
    if attempt:
        content += '<p><strong>下一步：</strong>阅读下方英文草稿并核对内容。预览生成已执行，不代表已经获得生产发布授权。</p>'
    elif gaps:
        content += '<p><strong>下一步：</strong>阅读引用、判断支持关系并保存本项核对。'+('已保存的核对中仍有冲突或待判断内容，请继续处理。' if done == total else '')+'</p>'
    else:
        content += '<p><strong>下一步：</strong>各项核对已保存，可在下方单独确认是否进行预览生成。</p>'
    content += '<p class="muted">“证据支持这项写法”仅表示当前引用支持当前限定表述，不代表企业真实性、技术能力、认证或生产资质已经获得独立验证。每次保存只更新当前这一项。</p>'
    content += '<nav class="progress-links" aria-label="核对项目">'
    for key in sorted(task.obligations, key=lambda key: key in reviews):
        status = reviews.get(key, {}).get('verdict', 'UNREVIEWED')
        content += '<a href="#review-'+esc(key)+'">'+esc(obligation_label(key, task))+' · '+STATUSES[status]+'</a>'
    content += '</nav>'
    content += details('技术详情', dict(run_id=state['run_id'], task_id=task.task_id, version=task.version,
        revision=state['revision'], state_digest=digest(state), evidence_digest=evidence_digest(state),
        readiness=gaps, production_authorized=state['production_authorized']))
    return content


def review_cards(request, state, task, saved, form, hidden):
    content = ''
    reviews = {review['obligation_id']: review for review in state['reviews']}
    ordered = sorted(task.obligations.items(), key=lambda item: item[0] in reviews)
    for index, (key, obligation) in enumerate(ordered, 1):
        selected = [s for s in state['spans'] if s['obligation_id']==key]
        review = reviews.get(key)
        status = review['verdict'] if review else 'UNREVIEWED'
        checked = set(review['span_ids']) if review else set()
        copy = obligation_copy(task, key)
        content += '<section id="review-'+esc(key)+'" class="review-card'+(' just-saved' if key==saved else '')+'">'
        content += '<div class="card-heading"><h3>'+str(index)+'. '+esc(copy['title'])+'</h3><span class="badge '+status+'">'+STATUSES[status]+'</span></div>'
        content += '<p class="fact">'+esc(copy['description'])+'</p><p class="review-tip">'+esc(copy['tip'])+'</p>'
        content += '<details><summary>查看原始英文要求</summary><blockquote>'+esc(obligation)+'</blockquote></details>'
        if key == saved:
            content += '<p class="notice" role="status">已保存本项核对。可继续核对其他项目。</p>'
        elif review:
            content += '<p class="muted">本项结论、意见和来源选择已保存，可以重新核对并更新。</p>'
        fields = hidden('obligation_id', key)+'<h4>请阅读引用 <small>共 '+str(len(selected))+' 条证据</small></h4>'
        for number, span in enumerate(selected, 1):
            source = next(s for s in state['sources'] if s['source_id']==span['source_id'])
            display = source_display(state, source)
            fields += '<div class="evidence"><strong>证据 '+str(number)+' · '+esc(display['label'])+'</strong>'
            if display['url']:
                fields += '<p class="source-page">来源页面：<a href="'+esc(display['url'])+'" target="_blank" rel="noopener noreferrer">'+esc(display['url'])+'</a></p>'
            else:
                fields += '<p class="source-page">来源：本地保存的资料；原始位置可在技术详情中查看。</p>'
            fields += '<p class="source-note">'+esc(display['note'])+'</p>'
            fields += '<p class="excerpt">'+esc(span['quote'][:180])+('…' if len(span['quote'])>180 else '')+'</p>'
            fields += '<details><summary>查看完整原文</summary><h4>本项引用的完整片段</h4><blockquote>'+esc(span['quote'])+'</blockquote>'
            fields += '<details><summary>查看本次保存的来源原文</summary><blockquote class="source-text">'+esc(source['content'])+'</blockquote></details>'
            fields += details('技术详情', dict(source=source, span=span))+'</details>'
            fields += '<label><input required type="checkbox" name="span_id" value="'+esc(span['span_id'])+'"'+(' checked' if span['span_id'] in checked else '')+'>我已阅读证据 '+str(number)+' 的完整片段，并核对适用范围与限制</label></div>'
        if selected:
            fields += '<label>选择本项核对结论<select required name="verdict" aria-describedby="verdict-help-'+esc(key)+'">'
            if not review:
                fields += '<option value="" selected disabled>请选择核对结论</option>'
            for value, label in [('SUPPORTED','证据支持这项写法'), ('CONFLICT','发现证据冲突'), ('UNRESOLVED','暂时无法判断')]:
                fields += '<option value="'+value+'"'+(' selected' if status==value else '')+'>'+label+'</option>'
            fields += '</select></label><ul class="verdict-help" id="verdict-help-'+esc(key)+'"><li>证据支持这项写法：引用内容足以支持当前限定范围内的表述。</li><li>发现证据冲突：不同来源相互矛盾，或者来源与拟写内容冲突。</li><li>暂时无法判断：证据不足、含义不清或仍需要补充材料。</li></ul>'
            fields += '<label>核对意见（必填，最多 1000 字符）<textarea required name="note" maxlength="1000">'+esc(review['note'] if review else '')+'</textarea></label>'
            fields += '<label><input required type="checkbox" name="review_ack" value="LOCAL_PREVIEW_REVIEW">我已主动核对本项全部证据、范围与限制，并确认本次判断。上传资料不等于核对通过。</label>'
            content += '<div class="review-form">'+form(request, '/runs/'+state['run_id']+'/review', fields, '更新本项核对' if review else '保存本项核对', state)+'</div>'
        else:
            content += '<p>尚无引用资料。请先在下方“补充资料”中添加本项资料，再进行核对。</p>'
        content += details('技术详情', dict(obligation_id=key, review=review, system_status=status))
        content += '</section>'
    return content
