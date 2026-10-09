# 受控真实 DeepSeek SEO Draft 验收

日期：2026-10-08（Asia/Shanghai）。本轮明确授权最多一次真实 Draft HTTP；实际一次。最终结论：机器契约 GO，内容质量 NO-GO，商业成稿准入 NO-GO。

## A 准入检查

已完整阅读 `docs/seo-draft-offline-acceptance-2026-10-08.md` 和 `.data/seo-draft-acceptance-20261008/accept_deepseek.py`，并沿 `accept_offline.py`、生产 Draft adapter/workflow、环境加载器及 codec 核对执行路径。脚本与报告所述单请求 Draft-only 方案一致。

- 使用现有环境加载器仅检查 DEEPSEEK_API_KEY 非空；存在。未输出、记录或回显键值，未调用凭据/余额查询 API。
- 实际 endpoint 仅为 `POST https://api.deepseek.com/chat/completions`；transport 第二次调用在委托底层前拒绝。底层 `AsyncHTTPTransport(retries=0)`，AsyncClient 默认不跟随 redirect；observer 在 repair prompt 到达真实 writer 前阻断。
- 固定 `deepseek-flash`、thinking disabled、temperature=0、max_tokens=3000。两条 message 共 8,497 UTF-8 bytes，低于 16,000-byte transport 护栏；生产材料、envelope、输出预算及稳定输入校验仍有效。bytes 不是 tokens。
- 准备阶段全部 crawler/search/research/opportunity 为 fixture，Planning/Draft HTTP 为 MockTransport；新 Plan 只有 C1 EXPAND_SECTION，不构造 delivery workflow。不存在比较表格执行路径。
- 本轮新跑 51 项相关单元测试：1.753s，OK，exit=0。命令为 `.\.venv\Scripts\python.exe -m unittest tests.test_deepseek_content_draft_adapter tests.test_content_draft_workflow tests.test_comparison_admission tests.test_deepseek_draft_numeric_prompt -q`。未重跑完整 suite，不沿用旧报告的测试数字作本轮通过依据。
- 本轮 PREPARE 和 success/bad_json/wrong_change/secret/http_401 共 6 个离线场景，退出码分别 0/0/1/1/1/1，符合预期；wrong_change 保留 UNKNOWN_CHANGE_REFERENCE 并阻断 repair HTTP。DNS、同步联网入口、真实 HTTP transport 与 delivery 构造在这些检查期间均被拦截。
- 7 个 transport 护栏探针通过：错误 method、endpoint、model、3001 tokens、thinking enabled、16001-byte input 均在委托前拒绝；第二次请求被拒绝。全部 fake/mock，不占真实请求额度。

准入证据：`.data/seo-draft-acceptance-20261008/current-live-audit/preflight.json`；初始工作区摘要和状态保存于同目录。没有修改验收脚本或生产配置。

## B 实际请求

执行且仅执行一次：

```powershell
.\.venv\Scripts\python.exe .data/seo-draft-acceptance-20261008/accept_deepseek.py --execute-live
```

进程 exit=0；实际请求数 1；HTTP 200；响应 envelope JSON 合法；requested/response model 均为 deepseek-flash；finish_reason=stop，未截断；文本 1,718 chars / 1,718 UTF-8 bytes。没有第二次真实请求，没有联网 repair/retry。

| usage | 实际值 |
|---|---:|
| prompt_tokens | 1899 |
| completion_tokens | 464 |
| total_tokens | 2363 |
| prompt_cache_hit_tokens | 1152 |
| prompt_cache_miss_tokens | 747 |

`cost_estimate_ceiling_usd=0.01` 是既有脚本的估算 metadata，不是本轮实付金额或账户侧硬预算。本轮不额外访问价格页或结算 API。

真实结果目录：`.data/seo-draft-acceptance-20261008/live-/d3793d59826448c9834cfcbe87bb2188/`。run=`58681c3b-2611-490a-93f1-0ec5f2e89f4e`；真实 result artifact=`0c58bab3-6807-4d18-add8-6b0fb534dcfc`。判定依据是此新 artifact，不是同 run 的准备 mock Draft。

## C 契约结果

机器契约 PASS：generation_status/draft_status 均 success，final_category=null。生产 parser 已验证唯一顶层 draft、操作专属 exact fields、英文、预算、引用 ID/scope、第一方引用、数字/宣传/竞争者限制和重复契约。

- D1 → C1 → R1，SECTION_DRAFT / EXPAND_SECTION，target P1；Draft locator 与 Change 相等，均 PAGE_LEVEL，locator_heading=null；Draft heading 与 proposed_heading 均 null。此操作没有批准新增标题，review 标记 requires_title_override=true，不能把无标题视为可直接插入 CMS 的完成结构。
- 3 blocks：PARAGRAPH / BULLET_LIST / PARAGRAPH，9 claims；没有比较表、HTML、CMS 字段或新增引用。CL1–CL8 均 P1/S1，CL9 CALL_TO_ACTION 引用为空；规范化全文没有完全相同的重复句。
- P1/S1 均存在且在 C1 scope 内。引用 ID 合法和 MIXED_CONTEXT 标签不能证明每个引用逐句支持文案；该问题在 D 中独立判定。
- 新 live Draft 追加为 V1 artifact，SQLite user_version=4。库中共 7 artifacts，其中 2 个 CONTENT_DRAFT：原准备 mock artifact 保留，新 live artifact 单独追加。
- 使用只读 SQLite decode，并对真实 artifact 做 encode/decode 等值检查；由已验证 artifact 重建 provider specification，使用纯本地 ReplayWriter 再跑生产 DraftWorkflow，结果与真实 artifact 相等。此 replay 不是第二次 API 请求，也不是原始 provider 文本字节重放。
- 新跑真实模块 CLI review，exit=0；approval_record=NOT RECORDED，review_action=READ ONLY，requires_human_review=true。全库 WordPress attempts=0；离线验证前后数据库 SHA-256 不变。

持久化证据：`diagnostics.json`、`request.json`、`prepared-request.json`、`history.sqlite3`、`live-review-D1.json`、`verification.json`、`reconstructed-validated-specification.json`。请求 JSON 不含认证 headers/cookies；未保存原始 provider envelope/错误体。脚本 diagnostics 的 quality 仍为 HUMAN REVIEW REQUIRED，独立质量结论记录于 verification 和本报告，没有改写机器执行记录。

## D 内容质量

内容质量 NO-GO。逐句对照实际请求中的完整 P1/S1，检查的是新 live artifact 的正文，不是 fixture Draft。

| claim | 内容核对 |
|---|---|
| CL1 | “Chemical compatibility is an observed topic for industrial pump materials.” P1/S1 包含主题，但这是材料观察描述，未解释兼容性。 |
| CL2 | “Material selection is an observed topic alongside chemical compatibility.” 同样仅复述主题，与 CL1 信息价值重叠。 |
| CL3 | 关于 wetted materials、operating conditions、corrosive process 的句子直接复制 P1；P1 支持，但 S1 没有这些具体信息，多余 S1 不能逐句证明该句。 |
| CL4 | 完整复制 S1 的短句；没有长篇复制问题，但几乎没有新增解释。 |
| CL5–CL8 | 分别说 port size、application、maintenance、pump performance 是 observed topic。P1 的主题列表支持其出现；S1 不包含 port size、maintenance、performance，application 也不支持“该页面出现主题”的观察结论。四句附加 S1 属于不支持该句的引用。它们还偏离 C1 唯一 EXPLAIN Chemical Compatibility content point。 |
| CL9 | 泛化 CTA，引用为空符合契约；没有提供具体可执行的选材/兼容性判断步骤。 |

未发现编造产品参数、数字、认证、性能优势、竞争者品牌、不存在的 P/S ID 或事实夸大；不应因此声称引用质量合格。发现了引用归因不充分、主题漂移、重复句式及空泛 SEO 文案。6/9 claims 使用 observed topic 句式，与 system prompt 的 “Do not write ... meta-analysis statements” 不一致。

结构形式可读且预算合理，但单个列表混排泛化 context 与多个主题观察，没有形成 Chemical Compatibility selection guide 的实质解释。PAGE_LEVEL 且 heading=null 与 Plan 一致，不能确定现有 Chemical Compatibility H2 下的插入位置；需人工确定标题/位置。英文语法可理解，商业信息增量不足。

材料本身为合成 fixture：P1 是主题枚举加一个选材句，S1 只有一个概括句。它们没有具体材料兼容性、工况条件或决策证据。本次不代表真实客户 SEO 效果或生产材料覆盖。

## E 失败诊断

没有 HTTP、JSON、机器契约失败或脱敏网络错误；失败发生在内容质量审核层。未发送第二次真实请求，未放宽校验，未修改模型、Prompt、grammar、codec 或 schema。

离线根因证据：

1. 输入 P1 含 “are observed topics”，模型在 6 条 claim 中延续该表达；S1 的信息也极少。稀薄且偏观察式的材料与输出模式一致。一次样本不足以证明 deepseek-flash 的普遍能力，不能把材料诱导认定为唯一模型成因。
2. `core/content_draft.py::_validate_claim_evidence`（约 1373 行）检查引用存在与 scope、claim type、第一方 P、numeric grounding 和禁止表达等，没有逐句非数字语义蕴含校验，也没有 observed-topic 元分析拒绝规则。故 S1 的附加归因和这些空泛句可通过。
3. `_factual_identity` / `_finalize_claim`（约 1525/1533 行）按规范化文本及 refs 判断重复；文本不同的主题枚举不会触发 DUPLICATE_CLAIM。EXPLAIN 主题的充分性、商业信息增量和列表语义结构不是当前机器契约所保证的性质。
4. 由真实已验证 artifact 重建 specification 的离线重放仍 success，复现了“机器通过、内容不合格”的边界；codec 与持久化没有导致内容变形。heading/location 直接来自现有 Plan/finalizer，并非模型虚构标题。

本轮只记录问题和根因，不实施修复。要重新验收，需要另行明确授权真实请求；本轮没有扩大授权。

## F 文件变更

唯一新增的可纳入版本管理文件为本报告。其余新增内容均位于既有 ignored `.data/seo-draft-acceptance-20261008/`：新 PREPARE/mock 目录、live 目录、current-live-audit 的准入/快照记录及离线复核文件。

对开始快照包含的 252 个现存/已删除文件（含两份 ignored 验收脚本）逐一复查 SHA-256/存在状态：原有文件变化为零；已有 dirty 和删除状态保留。没有修改任何生产源码、测试、既有报告、验收脚本或旧数据库。没有 Git commit/push/merge、WordPress 请求/写入、客户站点访问或比较表格功能恢复。

本轮验证：51 项单元测试、6 个离线场景、7 项护栏探针、一次真实请求、artifact/codec/只读 review/离线 replay。没有测试失败；内容质量审核失败。未执行完整回归。

最终保全检查通过，新增非 ignored 文件只有本报告；对本轮 56 个输出文件执行当前 API key 精确字节检查，仅记录 PASS，未输出匹配内容。新报告无尾随空白；`git diff --check` exit=0，输出既有 LF→CRLF 提示，没有 whitespace error。保全摘要保存于 `current-live-audit/final-preservation-check.json`。

## G 最终 GO/NO-GO

| 验收对象 | 结论 |
|---|---|
| 单次真实 HTTP 与机器 Draft 契约 | GO（仅此合成样本） |
| 人工内容质量 / 商业成稿准入 | NO-GO |
| 本次 Draft 整体验收 | NO-GO：空泛元分析、无支撑附加引用、EXPLAIN 不充分 |
| WordPress 交付 / 比较表格恢复 | NO-GO；本轮均无授权且零执行 |

成功 artifact 可追溯且仍需人工审核；不得将 schema success 或准备 run 的 SUCCEEDED 当作可交付批准。
