"""Offline replay only: no provider, permit, review approval or historical writes."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from foreign_trade_geo_agent.core import content_draft as cd
from foreign_trade_geo_agent.storage.serialization import _decode, _encode
from foreign_trade_geo_agent.workflows.content_draft import _parse_specification, inspect_candidate_output

OUT = Path(__file__).resolve().parent
HISTORY = ROOT / 'docs/seo-flash-contract-quality-live-2026-10-12'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def load_case():
    raw = (HISTORY / 'model-output.txt').read_bytes()
    response = (HISTORY / 'response-body.bin').read_bytes()
    assert sha(raw) == '04c311ca5fc7a85833f3662dd11d21a97aae00cc95a40afe2604dd5e4ba202e0'
    assert sha(response) == '9f69992de2e7a9d0c16a66893a07b72dd39cbb8fe5e538f47ed10378383398db'
    assert json.loads(response)['choices'][0]['message']['content'] == raw.decode('utf-8')
    value = _decode(json.loads((HISTORY / 'native-input.json').read_bytes()), cd.ContentDraftInput)
    assert cd.stable_content_draft_input_error(value) is None
    return value, raw.decode('utf-8')


def replay():
    value, raw = load_case()
    operation = value.change_plan_report.operations[0]
    spec = _parse_specification(raw, expected_change_ref=operation.change_id, operation=operation)
    check = inspect_candidate_output(value, raw, current_snapshot_sha256=value.customer_evidence.snapshot_sha256)
    facts = {f.fact_ref: dict(_encode(f), evidence_id=s.evidence_id,
                evidence_version=s.evidence_version, source_label=s.source_label,
                source_locator=s.source_locator, content_sha256=s.content_sha256)
             for s in value.customer_evidence.sources for f in s.facts}
    sections, claims, offset = [], [], 0
    for index, (section, brief) in enumerate(zip(spec.sections, operation.new_resource_spec.section_briefs), 1):
        group = [c for b in section.blocks for c in (b.claims if hasattr(b, 'claims') else b.items)]
        ids = [f'CL{i}' for i in range(offset + 1, offset + len(group) + 1)]
        refs = {r for c in group for r in c.customer_refs}
        sections.append(dict(section=index, brief=_encode(brief), claim_ids=ids,
            actual_sources=sorted({r.split('.')[0] for r in refs}),
            actual_requirements=sorted({rid for r in refs for rid in facts[r]['requirement_ids']}),
            outside_facts={cid: [r for r in c.customer_refs
                if not set(facts[r]['requirement_ids']) & set(brief.requirement_ids)]
                for cid, c in zip(ids, group)
                if any(not set(facts[r]['requirement_ids']) & set(brief.requirement_ids) for r in c.customer_refs)}))
        for cid, c in zip(ids, group):
            native = check.claims[int(cid[2:]) - 1]
            evidence = '\n'.join(cd._normalized_text(facts[r]['quote']) for r in c.customer_refs)
            claims.append(dict(_encode(native), section=index, heading=section.outline_heading,
                facts=[facts[r] for r in c.customer_refs],
                numeric_expressions=[dict(expression=e, present=cd._numeric_expression_is_present(e, evidence))
                    for e in cd.extract_numeric_expressions(c.text)]))
        offset += len(group)
    used = {r for c in claims for r in c['refs']}
    return dict(parser='PASS', input_validation='PASS (original input, no refreshed timestamp)',
        raw_sha256=sha(raw.encode()), response_sha256=sha((HISTORY / 'response-body.bin').read_bytes()),
        native_check=_encode(check), sections=sections, claims=claims,
        missing_facts=[facts[r] for r in sorted(set(facts) - used)])


def diagnose(result):
    """Full original text/evidence for each actual rejection, not only first error."""
    claims = {c['claim_id']: c for c in result['claims']}
    rows = []
    def add(ids, section, rule, reason, category, extra=()):
        group = [claims[cid] for cid in ids]
        facts = {f['fact_ref']: f for c in group for f in c['facts']}
        facts.update({f['fact_ref']: f for f in extra})
        rows.append([' / '.join(ids) or '—（文档级）', section,
            '<br>'.join(c['text'] for c in group) or '正文未引用以下事实',
            ', '.join(sorted({r for c in group for r in c['refs']})) or '—', rule, reason,
            '<br>'.join(f"{r} · v{f['evidence_version']} · {f['source_locator']} · [{f['start']}:{f['end']}] · {f['quote']}"
                         for r, f in sorted(facts.items())), category])
    add(['CL7'], '1', 'NUMERIC_CONTEXT_NOT_PRESERVED',
        '520 kg / 180 kg 均存在于引用；含数值的新解释句并非任何引用中的完整原句。',
        '模型契约违规；未证实数值或型号错误；契约保守性待业务确认')
    add(['CL19'], '3', 'NUMERIC_NOT_GROUNDED',
        '6061-T6 被拆成 6061-t 与 t6，整词查找均失败；正文逐字等于 E4.F01。', '程序误判（已修复）')
    add([], '全文（主要关联1/3/4章）', 'CUSTOMER_EVIDENCE_COVERAGE',
        '40/43；当前代码要求使用全部 quote_map refs，而非仅覆盖必需采购问题。',
        '模型遗漏 + 全量引用契约设计问题（本轮不放松）', result['missing_facts'])
    for rule, reason in (
            ('SECTION_EVIDENCE_OUTSIDE_QUESTION', 'E5 源 requirement F5/F8 与本章 F2 无交集。'),
            ('SECTION_FACT_OUTSIDE_QUESTION', 'E5.F03 属 F5，不在本章 F2 允许事实中。'),
            ('SECTION_QUESTION_EVIDENCE_INCOMPLETE', '实际 E1/E3/E5 ≠ brief E1/E3；此处是多出 E5，并非缺少 E1/E3。')):
        add(['CL17', 'CL18'], '2', rule, reason,
            '模型违反显式映射；主轴/型号比较语义重叠；契约设计疑点')
    add(['CL25'], '4', 'SECTION_FACT_OUTSIDE_QUESTION',
        'E3 是本章合法源，但 E3.F04 仅映射 F2，本章要求 F4/F6。',
        '模型违反事实级映射；测量环境与 F4 明显相关，映射设计疑点')
    # E2.F09 is already quoted in CL12, but not in section 6.
    e2 = next(f for f in claims['CL12']['facts'] if f['fact_ref'] == 'E2.F09')
    add([f'CL{i}' for i in range(38, 48)], '6', 'SECTION_QUESTION_EVIDENCE_INCOMPLETE',
        '实际 E5/E7 缺少 brief 的 E2；E2.F09 已放第1章 CL12，F7/F8 仍均有覆盖。',
        '模型未遵守显式来源集合；章节间配置/选配重叠；无 Parser 路由 Bug', [e2])
    def cell(text):
        return str(text).replace('|', '\\|').replace('\n', '<br>')
    lines = ['# 原始响应全部拒绝诊断', '',
        '只读证据；正文与引用未修改。source SHA256、proposal、全部47条 claim 结果见 before.json / after.json。', '',
        '| Claim ID | 章 | 原始内容 | 使用 fact_refs | rule_id | 实际原因 | 原始客户证据 | 初步分类 |',
        '|---|---|---|---|---|---|---|---|']
    lines += ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows]
    target = OUT / 'diagnostics.md'
    assert not target.exists()
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    stage = sys.argv[1]
    if stage == 'diagnose':
        diagnose(json.loads((OUT / 'before.json').read_bytes()))
        sys.exit(0)
    assert stage in {'before', 'after'}
    result = replay()
    target = OUT / f'{stage}.json'
    assert not target.exists(), 'Never overwrite an earlier replay result'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if stage == 'before':
        assert result['native_check'] == json.loads((HISTORY / 'candidate-validation.json').read_bytes())
        historical = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in (ROOT / 'docs').rglob('*')
            if p.is_file() and OUT not in p.parents and '__pycache__' not in p.parts}
        (OUT / 'historical-sha256.json').write_text(json.dumps(historical, indent=2), encoding='utf-8')
    else:
        before = json.loads((OUT / 'before.json').read_bytes())
        old, new = before['native_check'], result['native_check']
        diff = dict(before=old['state'], after=new['state'],
            removed_errors=[e for e in old['errors'] if e not in new['errors']],
            added_errors=[e for e in new['errors'] if e not in old['errors']],
            retained_errors=[e for e in new['errors'] if e in old['errors']],
            claim_results=[dict(claim_id=a['claim_id'], before=a['deterministic_error'], after=b['deterministic_error'])
                for a, b in zip(old['claims'], new['claims'])],
            unchanged_binding=old['binding_sha256'] == new['binding_sha256'],
            historical_files_unchanged=all((ROOT / n).is_file() and sha((ROOT / n).read_bytes()) == h
                for n, h in json.loads((OUT / 'historical-sha256.json').read_bytes()).items()))
        assert diff['historical_files_unchanged'] and diff['unchanged_binding']
        (OUT / 'diff.json').write_text(json.dumps(diff, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(parser=result['parser'], state=result['native_check']['state'],
                         errors=result['native_check']['errors']), indent=2))
