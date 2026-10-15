# 自主解释候选：离线实施与验收

本轮已经实现“新解释可以提出和保留，交付资格必须另行审核”的原生路径。离线契约链 READY；完整采购指南的下一次真实 Flash 质量实验仍为 **BLOCKED_OUTPUT_BUDGET_PREFLIGHT**。未调用真实 DeepSeek、余额接口或 WordPress；未部署、commit、push、merge，未改生产 Gate、P1、PostgreSQL，也未删除历史冻结材料。

最终冻结目录：`docs/seo-autonomous-interpretation-2026-10-11/final-v2/`。所有文章和审核演练均为 SYNTHETIC / Mock；没有真实模型质量结论，也没有可信真人签核。

## 1. Phase 0 审核与最小方案

原自主解释阻断有三层，定位如下（行号以本轮代码为准）：

- `core/draft_customer_evidence.py:170`，`DraftCustomerEvidence.claim_error`：解释 text、全部 fact_refs 必须匹配已有 `DraftInterpretation`。本轮增加 proposal 的精确匹配，没有取消这一正式准入规则。
- `workflows/evidence_intake.py:19`，`reviewed_draft_input`：此前要求每章已有预审解释选项，并用选项 premise 估算输出可行性；现在只有显式候选模式可以不提供预写解释，事实充分性、范围审核和原生 Plan 绑定继续必需。
- `core/content_draft.py` 的 `ContentDraftPrompt.material_json` 与 `adapters/deepseek_content_draft.py` 的 `build_system_prompt`：此前要求复制解释选项；新增候选模式要求提出新分析，并禁止模型输出批准字段。

旧 Parser 能读取任意解释字符串，但没有独立候选状态：新解释被 Validator/Finalizer 拒绝。`adapters/retained_deepseek.receive_candidate` 已保留安全原始响应、model-output 和 rejected-candidate；旧 Web Article Review 只展示已成功准入的 Draft，因此被拒解释不能逐条审核。

复用方案：同一 `ContentDraftInput` / `DraftClaimSpecification` → 原生 Parser → 非准入候选检查视图 → 既有 `SQLiteLocalDraftReviewStore` 追加版本与决定 → 明确 TEST-only 复验 → 原生 Finalizer → 既有 HistoryStore / Review。没有第二套文章、Evidence 或 Planning 数据库。

## 2. 新契约与来源绑定

`core/draft_customer_evidence.InterpretationProposal` 保存模型的采购问题、推理说明、未确认假设、限制和采购动作。实际解释正文在原生 `DraftClaimSpecification.text`，一个或多个 premise 在 `customer_refs`，claim type 仍为 `EVIDENCE_BASED_INTERPRETATION`。限制和动作必须出现在实际正文中。

Python 从已审阅 `DraftCustomerFact` / `DraftCustomerSource` 绑定精确原文、偏移、来源标签、locator、文档内容 SHA256、证据版本和完整来源文档。原始条件和适用范围保持原文字节，不让模型另写一份条件摘要充当权威。完整来源也在候选 Markdown/Web 中显示，包括文档头的修订及有效期说明。

`ContentDraftInput.propose_interpretations=True` 是写作模式，不是执行权限。该模式投影的解释 allowlist 为空。`DraftClaim`、`DraftInterpretation`、`ReviewedInterpretation` 可以携带同一 proposal，正式复验要求正文、premise、proposal 元数据完全一致。所有现有 E Draft 仍受 TEST-only profile 限制。

## 3. 确定性与语义审核的边界

| 类别 | 程序处理 | 仍需语义判断 |
|---|---|---|
| A 直接事实 | 单引用、精确原文；来源哈希/偏移/版本及 native scope 核验 | 来源可信度、事实适用性 |
| B 新解释 | 新正文可进入候选；检查有效 refs、元数据、数值、预算、范围覆盖及明确禁止的声明 | 推理是否成立、premise 是否完整、采购价值、假设是否充分 |
| C 错误事实/数字/承诺 | 明确数值、错误引用、错误单位、已知宣传规则等拒绝；其他语义错误没有自动准入资格 | 无数字的能力夸大、条件遗漏、提案变承诺、隐晦主体混用必须拒绝或要求修改 |
| D 衔接/CTA | 无事实引用；衔接语采用保守的非事实句式；数字、已知能力/宣传声明拒绝 | CTA 是否暗含额外产品事实，全文仍需检查 |

新解释的数量性句子采取保守规则：除既有数字/单位核验外，含数量的整句必须来自所引原文，防止从汇总事实目录取一个正确数字却换了型号、主体、动态/静态条件或限定。数量性事实可独立精确引用，采购分析另写。无数量的推理依然不能由该规则证明。

proposal 推理和假设也接受数字及宣传规则检查。非规范空白的解释正文明确拒绝，避免审核后在 Finalizer 中悄悄归一化；原始输出仍保存。不执行自动语义打分或模型自我签核。

## 4. 审核状态、版本和原生复验

确定性失败为 `DETERMINISTICALLY_REJECTED`；结构通过为 `PENDING_SEMANTIC_REVIEW`。两者都不是 admitted DraftItem。Web 可读取拒绝候选及失败原因。

候选原始 JSON 作为现有 `LocalDraftRevision.body_text` 的不可变首版本保存；后续 `CandidateDecision` 只有 `APPROVE / REJECT / REQUEST_CHANGES`、理由及完整绑定。绑定包含任务/Plan 图、全部来源及版本、证据快照、writing brief 和确切原始 JSON。正文、premise、推理、假设、条件、范围或证据变化会使旧决定失效；修订始终追加，原始模型输出不覆盖。

Web 本地操作员没有认证，APPROVE 仅表示本地语义意见。模型无法输出决定字段；浏览器不能提交 signature、reviewer_id、production_authorized 或切换执行模式。

`workflows/content_draft_review.test_only_revalidate_candidate` 是明确调用的模拟复验：当前事实审核有效、全部候选有当前版本的明确批准后，才构造 TEST-only reviewed projection 并调用原生 Finalizer。它不会在生成时自动升级候选，也不发放生产权限。可信真人审核仍应经已有 `EvidenceSemanticReviewer` 边界提交确切解释和 premise；本轮没有建设认证或多人审批平台。

审核后保存的 `DraftItem` 保留 proposal，SQLite 独立重读继续检查文本与 premise 绑定；原生修订复验保留 proposal，避免丢失审核元数据。

## 5. 独立多事实正反例

输入事实审核有 **零条预写解释**。MockTransport 输出六条此前未在输入 allowlist 中出现的解释：

- 型号表面尺寸、夹具及合并静载 → 大夹具场景排除 NCX7，NCX10 仍只是条件候选，保留 clearance / dynamic load 未验证，要求提交工装布局。
- 空载评级和试验条件 → 解释其没有测量刀具与工件相互作用，要求 loaded trial / torque records。
- 材料、工具、冷却、路径 → 解释匹配试验只可作为相同 setup 的起点，要求提供真实应用与完整周期。
- 外宽测量、样本、假定不确定度和拟议验收条款（E3/E4/E6 共 17 个 premise）→ 拟议公差内的结果不自动等于已约定的验收结论，decision rule 仍需约定。
- 拟议 FAT / RFQ / disposition / re-test → 要求双方明确责任，不能变成既成合同承诺。
- dispatch、远程培训及 initial response → 区分到货和恢复义务，要求书面确认商业条款。

负例包括未知 fact_ref、变造直接事实、错误数字/单位、给 NCX7 复用 NCX10 数值、删除限制/premise、改推理/假设、伪造批准字段、editorial/CTA 产品事实、旧任务/Plan/来源版本复用。无数量的硬化合金能力、空载转速推扭矩、提案变合同等作为语义负例：即使确定性检查未能判错，仍没有准入资格，明确 REJECT 后不能完成 TEST replay。

## 6. 实际输入输出预算

| 项目 | 最终实测 / 上限 |
|---|---|
| 文档 / 独立事实 | 7 / 43；全部进入输入及来源映射 |
| 原生章节 | 6，问题地图仍显式提供 |
| user material | 22,162 chars / 26,000 chars；bytes 上限 56 KiB |
| 实际请求 | 31,139 bytes；原生 envelope 上限 36,000 chars / 76 KiB |
| Mock 响应 JSON | 8,031 chars / bytes；上限 16,000 chars / 32 KiB |
| claims / blocks | 13 / 6；上限 16 / 8 |
| provider max_tokens | 3,000，包含 JSON/引用/元数据；实际 token 数未知 |
| 资料内文总量 / refs | 原上限 16,000 chars、64 facts、每 claim 最多 20 refs |

Mock 正文实际为 368 个空格分词、2,520 chars；六条解释分别引用 14/5/8/17/6/9 个 premise。这是手写 Mock 响应，不能证明真实模型写作质量。

去掉了候选输出中重复抄写整套 premise quotes 的设计；模型只输出 refs，程序绑定原文。原输入事实目录仍有首条 quote 与 facts 的小量重复，没有为节省输入删减事实或问题。

预算测试明确构造更深的六章表达：每章一事实加两分析及 CTA 为 19 claims；两段/章加独立 CTA 为 13 blocks，超过当前上限。这个反例证明当前预算会阻止更充分表达；不证明每篇指南必须采用该布局。为了本轮最小契约变更，没有提升生产共享上限，也没有静默裁剪章节。**正式完整指南质量实验暂按预算未通过阻断**，需下一步确定受限文章预算并通过实际 structured-output 可行性预检。

## 7. 低资料与丰富资料验收

A：E1-only 要完整采购指南仍 BLOCKED，列出 F1–F8 缺口，writer 调用 0。

B：7 份资料、43 事实 → 原生 Parser → 六条新候选 → 未审核正式 Finalizer 拒绝 → Web/Markdown 显示来源与状态 → SQLite 追加 REJECT、REQUEST_CHANGES、明确模拟 APPROVE → 当前版本原生复验 success → HistoryStore 保存与独立重读 → 原生 Review Markdown。

冻结实验执行器也通过单独的 MOCK-only permit 演练，能接收超过旧 16KB 默认的丰富输入并保留待审候选。OneShotTransport 仍精确匹配请求、绑定截止时间、限制一次请求，不重试。没有 LIVE permit 或真实网络请求。

## 8. 真实 Flash 实验冻结及阻断

冻结文件包含原生任务/Plan/证据快照、事实审核、Prompt/request、代码/模板哈希和原始输出留存方案。模型 `deepseek-flash`、temperature 0、thinking disabled、一次请求、60s、不重试。确切 bundle/request 哈希见 `final-v2/readiness.json` 和 `final-v2/B-rich-evidence/web-experiment/bundle.json`。

暂按归档价格和 32,768 input tokens / 3,000 output tokens 假设得到 ¥0.089536 的保守估算，**不是当前报价、实际 token 测量、账单或账户硬限额**。没有余额调用或费用授权；实际授权金额为 0。

精确剩余阻断：

1. 完整六章指南的 claim/block/output-token 可行性尚未通过；当前 Mock 只是短契约样本。
2. DeepSeek tokenizer/实际 token 数与当前费用口径尚未核实，不能把字节数或归档价当成服务端硬预算。
3. 下一次执行必须重新核对事实/范围的当前审阅、冻结哈希，并另获明确真实请求授权；本轮没有该授权。
4. 所有真实模型解释、premise 完整性、商业推理和 CTA 必须由真人语义审核；TEST-only 批准不能替代。

对照保留此前 170 词低资料文章，新条件为 7 份资料/43 事实及开放候选解释；评价维度统一为准确性、解释深度、采购价值、重复、结构和 CTA。资料、Prompt 和解释机制同时变化，不宣称单变量实验。宽泛任务自主产生完整采购问题地图仍未完成。

## 9. 修改文件与实际验证

本轮涉及 `core/{content_draft,draft_customer_evidence,draft_candidate_review,content_draft_review,draft_revalidation,evidence_intake}.py`；`workflows/{content_draft,content_draft_review,evidence_intake}.py`；`adapters/deepseek_content_draft.py`；`storage/{serialization,content_draft_review}.py`；`reporting/content_draft_review.py`；`web/{generation,experiment,candidate_review,mvp_routes}.py`；`web/templates/{mvp_generation,mvp_candidate}.html`；`scripts/accept_autonomous_interpretation.py`；`tests/{test_autonomous_interpretation,test_seo_e_only,test_intake_native_planning}.py`。保留进入本轮前所有其他未提交改动。

实际定向验证：最终分组 **92 tests，110.700s，OK**，日志 `verification/11-targeted-final.log`；其后新增的原始空白/超限不截断测试纳入完整回归。CRLF 与 Web 修订定向 39 项通过；两个完整回归失败的独立复核 2 项通过；最终候选专项 18 项通过。最终冻结脚本成功，退出码 0，日志 `verification/18-final-freeze.log`。**最终完整回归：1,857 tests，527.117s，OK，退出码 0**；命令 `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q`，日志 `verification/19-full-final-fixture.log`。此前串行共享代码完整回归亦为 1,857 tests / 429.899s / OK。机器摘要见 `verification/verification-summary.json`。最终 67 个冻结文件和源码哈希均独立复核一致。

中途失败全部保留：

- `01-shared-contract.log`：67 tests，1 failure；editorial 放开导致明显产品事实通过，已修正。
- `02-offline-probe.log`：脚本直接执行无法导入 scripts，改用 `python -m scripts.accept_autonomous_interpretation`。
- `03-offline-probe.log`：候选检查没有沿用 E 来源实体上下文，误报 competitor；已与原生上下文对齐。
- `04/05-offline-probe.log`：测试 HistoryStore 的 site_key 不是带有效端口的 canonical origin，已修正。
- `07-targeted.log`：77 tests，1 failure；版本失效测试使用了原本相同的 v2，改为真正不同的版本。
- `09-targeted.log`：58 tests，1 failure；旧 digest 测试独立重建未去掉新增默认 False。保留原哈希断言，补充旧 shape 重建及“默认字段不得编码”的断言；真实历史冻结哈希回归亦通过。

- `12-full-regression.log`：首轮完整回归 1,856 tests / 518.491s，2 failures。原生 Intake 历史字段清单补上新增模式，并保留旧 payload 的完全相等断言；既有 10ms/50ms 超时测试在并行验证负载下返回外层超时，未改其断言或实现，独立复核通过，后续串行全套复验。
- 主动发现合法 CRLF JSON 无法进入旧本地 Review 文本校验，已允许原始 CRLF 并验证 SQLite 字节级原样重读；未归一化或覆盖模型输出。

没有将失败计入通过，也没有清理这些中间材料。已有 Starlette/httpx 弃用提示与 asyncio 慢任务诊断不属于测试失败。
