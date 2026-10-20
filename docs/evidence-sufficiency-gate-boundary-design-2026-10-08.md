# Evidence Sufficiency Gate：契约核对、RED 重建与停止实施设计

日期：2026-10-08（Asia/Shanghai）。本轮结论：**停止生产实现；Gate 未实现，真实 Draft 验收 NO-GO。** 按用户要求第 5 条，现有契约不能支持可信的任务级充分性判定时，先给出最小附加契约，不用语义启发式凑出实现。

已阅读[根因审计](seo-draft-quality-root-cause-audit-2026-10-08.md)及真实/离线验收报告，核对当前工作区 Planning、Draft、validator、固定 workflow、codec 和测试。本轮不调用真实 LLM、crawler 或 WordPress，不执行原 live harness，不 commit/push。保留既有未提交修改。

## A. 根因与契约边界

### 真实失败重建

证据目录为 `.data/seo-draft-acceptance-20261008/live-/d3793d59826448c9834cfcbe87bb2188/`。数据库用 SQLite `mode=ro` 读取；不实例化会迁移数据库的 store。

- run：`58681c3b-2611-490a-93f1-0ec5f2e89f4e`。
- 原任务：`How should buyers evaluate chemical compatibility?`，见 `accept_offline.py` 的 CLI 输入。
- SITE_CONTENT：`3624a6df-aca9-4906-bbf2-c07e8da63baf`；CONTENT_OPPORTUNITY：`fec4f838-04ad-4085-af2b-a033ebcc7c90`；CHANGE_PLAN：`04c82de7-c294-4b56-96c0-2cd8e85446d5`。
- 真实已验证 Draft：`0c58bab3-6807-4d18-add8-6b0fb534dcfc`。同库 `d66717b0-3038-4cc0-9354-5aecfebe8c8d` 是准备 mock，不用它替代真实失败。

| 环节 | 本轮独立核对结果 | 能支持的结论 |
|---|---|---|
| 用户任务 | 解释买家如何评估兼容性；R1 topic 为 `Chemical compatibility selection guide` | 任务具有评估/选材指南语境，不是把主题重新列一遍 |
| P1 | Industrial Pump Materials / Chemical Compatibility；正文列举主题，并说买家在选腐蚀工况泵前比较接液材料与工况；structured sections 重复相同材料 | 支持主题观察和这一具体先后关系；没有给出如何评价兼容性的判断依据、条件或方法 |
| S1 | 标题含 selection guide；完整正文只有 `Chemical compatibility and material selection help buyers evaluate industrial pump applications.` | 支持这一外部概括；标题不是指南正文，不能支持接液材料/工况/腐蚀过程/先后关系的具体命题 |
| 提取状态 | P1 extraction success；page、structured、packet 均未截断；crawl budget 未耗尽；fixture HTML 有相同两句 | 材料薄已证实；不能归因于丢失抓取内容 |
| Planning | fixture/Mock 选择 C1 EXPAND_SECTION、EXPLAIN Chemical Compatibility、P1/S1、PAGE_LEVEL | 生产准入接受坏 brief；不能证明真实 Planning LLM 自行作出该决策 |
| Draft | 9 条：6 条主题观察、CL3 复制 P1、CL4 复制 S1、CL9 泛化 CTA | 合法引用与结构存在；没有完成“如何评估”的解释任务 |

本轮用 LocalPlanWriter 重建相同 C1，生产 ChangePlanWorkflow 返回 success，operations 与历史相等。用 LocalDraftWriter 重放保存 specification，生产 ContentDraftWorkflow report 与真实 artifact 完全相等。当前生产 request builder 与保存 request.json 相等。全部为本地调用，不是原始 provider envelope 字节重放，不是新的模型样本。

### 必须分开的四层

| 层 | 当前保证/反例 | 与下一层的关系 |
|---|---|---|
| 结构合规 | exact keys、enum、非空 blocks、预算、locator 等 | 合规正文仍可能只有 CTA |
| 引用存在 | P/S ID 已知、在 Change scope 中、第一方必须有 P | 引用存在不能证明引用支持命题 |
| 引用支持具体论断 | CL3 完整受 P1 支持，附加 S1 不支持；S1 相关主题不能证明该具体关系 | 单句有支持仍不能证明整个指南任务完成 |
| 任务完成度 | 是否回答认可的买家问题、覆盖必答范围并提供有依据的解释/判断 | 当前契约未定义答案范围，不能确定性验证 |

引用语义支持还不同于来源真实性：S1 是未验证搜索 context，即使逐字复制也不能自动成为权威技术事实或第一方产品承诺。

### 当前实现核对

| 代码 | 已有可验证信息 | 缺失信息/检查边界 |
|---|---|---|
| `core/site_content.py::SiteContentEvidence` | P ID、完整 bounded 文本、structured blocks、提取/截断标记 | 没有命题支持/充分性人工判断；OBSERVED_PRESENT_ONLY 不表示不存在其他内容 |
| `core/content_opportunity.py::ContentOpportunitySourceMaterial` | S ID、title/content/truncation | 没有问题→答案支持关系；外部 context 的真实性没有升级 |
| `core/change_plan.py::ContentPoint` | 仅 `intent`、`subject` | 没有买家问题、必答义务、支持的答案、span 或人工判断 |
| `core/change_plan.py::_validate_content_points` | intent 合法、subject phrase 在材料中 grounding | 主题出现不是能解释；availability 也只是候选/预算合法性 |
| `core/content_draft.py::ContentDraftInput` | site/opportunity/plan/language | 不携带原 research question 或任务答案范围 |
| `core/content_draft.py::_content_point_payload` | subject 出现位置投影为 observed/required refs | 不能当作 claim support；不能把 required refs 数量当充分性 |
| `core/content_draft.py::_validate_claim_evidence` | ID/scope/type、第一方 P、数字、禁用表达等 | 普通 S 句义校验不接收 source content；非数字关系反转可通过 |
| `core/content_draft.py::finalize_draft_item` | 合法 blocks 和 operation 形状；ADD_SECTION 派生 heading | 不核对 EXPLAIN 完成；EXPAND heading=null 合法 |
| `workflows/content_draft.py::_run` | stable input 校验后逐 C 调 writer；失败 all-or-nothing | 没有任务级 preflight；若第二个 Change 不足，不能等第一个生成后才检查 |
| `core/content_draft.py::ContentDraftReport` | success/validation/provider failure 等状态；error 必须为 allowlisted category | 没有 insufficient/review-required 分类；失败不可携带任意 payload |
| `workflows/end_to_end.py` | Draft 非 success 时保留上游、不追加 Draft、run failed | 通用错误不可定位问题；现有 RunDiagnosticContext/CLI validation_diagnostic 可供最小扩展复用 |
| `storage/serialization.py` | V1 显式字段 codec；历史语义不因读取升级 | 给旧 ContentPoint 强塞新必需字段会破坏历史读取，不应这样做 |

现有 workflow/core tests 中薄材料作为正例验证的是机器契约。正常任务的机器回归有价值，但不是“充分解释材料”的质量金标准。没有最低 9 条 claim，也不以 heading=null、页数、字数或引文数解释本次问题。

### 停止实施的关键缺口

1. Draft 层失去原任务；`EXPLAIN Chemical Compatibility` 没有规定回答深度。术语介绍与评估指南都可带此标签，不能给它预设一套全局必答技术项。
2. 没有可信的任务义务→答案命题→原文 span→人工支持判断契约。扫描词或句长、数句子、拒绝 observed-topic 模板、要求某类技术词，都不能补上它。
3. 当前材料没有一份经认可、获使用授权的充分解释正例及匹配任务范围。用本地 writer 返回好文案，或者捏造 `sufficient=true`，都不是可靠放行依据。
4. 当前没有独立于 P/S/provider 内容的人工 assessment 输入路径。文本里声明 human-reviewed 或提供 reviewer_id 不能自行取得可信身份。

因此不实现全局 EXPLAIN 拒绝、不做原样本字符串黑名单、不把模型自评作为证明，也不静默改成 DESCRIBE/营销正文。这个停止来自用户第 5 条，而不是额外审批流程。

## B. 最小附加证据契约与落地方案（设计，未实现）

### 附加一个独立人工审核 brief，复用现有 P/S 与 C

无需先改持久化 Evidence、ContentPoint、DraftClaim、SQLite schema 或 artifact codec。最小增加一个 provider-independent、只用于本次生成准入的 `ReviewedTaskEvidenceBrief`，由操作者明确选定的本地审核记录加载。记录来自可信应用边界，不能来自 crawler 文本或 LLM 响应；审核身份的来源必须在接入时确认。下面字段名是设计，不是已存在的公开接口。

| 信息 | 最小字段/语义 | 软件能验证什么 |
|---|---|---|
| 绑定 | brief ID/version；原 task 文本/摘要；Plan 和 bounded evidence 的 canonical digest；如有历史则加 artifact ID | 确认评的是这项任务、这份 Plan 与这版材料；不能跨 run 只靠 P1/S1 复用结论 |
| 任务 | `change_ref`、`content_point_path`、原 intent/subject；人工认可的买家问题和必答义务 ID/文本 | 位置确实属于当前 Plan，所有 EXPLAIN point 均覆盖；不能由 writer 减少义务 |
| 支持 | 每项义务的可支持答案命题，原 P/S ref、字段路径、字符区间 `[start,end)`、原文 digest、归因角色 | ref/scope/字段/span 精确一致；不从词重合推断命题支持 |
| 审核 | 每义务 `SUPPORTED / PARTIAL / TOPIC_ONLY / UNSUPPORTED / NOT_REVIEWED`；人工理由、审核者/时间/记录版本 | 只能验证记录完整和身份来源；状态语义由人工对照全文判定，软件不冒充 entailment engine |
| 准入 | 人工 `sufficient / insufficient / not_reviewed`；正文的允许答案范围；不支持/待补证义务 ID | 一致性及 fail-closed 覆盖；未审与已证实不足必须区分 |

边界：span 精确存在只证明位置；SUPPORTED 是可信人工结论，不能仅有 span 就自动派生。`answer` 不是新证据：人也不能往 brief 中填来源没有的事实。S 的允许角色仍是未验证一般 context；第一方/数字限制照旧。必要内容若在截断区外，结果应是待补证/未评，不得推断真实网站缺失。短、具体且覆盖认可任务的证据可以通过；没有最低词数或引文数。

digest 必须来自 core 的确定性字段投影（task、完整所选 operation、bounded P/S 原文及截断状态、语言），不能在 core 导入 storage codec 或读取数据库。span 使用未规范化原字段的 Unicode 字符下标，`0 <= start < end <= len(field)`；禁止以先清理空白后的命中位置替代原文定位。brief 解析须拒绝未知键、重复 ID、越界索引、不一致的 verdict 和所有没有可信审核来源的记录。point 数量沿用现有最多 8 operations × 每 operation 5 points；任务义务/支持 span 的新增资源预算在正例与任务粒度确定后选定，仅作为资源上限，不能作为充分性阈值。

第一切片只检查 Planning 明确声明的 EXPLAIN，包括 ADD/EXPAND content_points 和 new_resource_spec.content_points；保留非解释型 intent 和 structure-only 的现有合法路径。这不是自然语言任务分类器。任务与 intent 的错标、遗漏和静默降级需任务 brief 的独立人工范围审核；不能声称所有隐含解释任务都已覆盖。brief 缺失时给 `EVIDENCE_ASSESSMENT_REQUIRED`，不是冒充已经知道证据不足。

### 准入顺序与失败结果

1. 保留现有 stable input/safety/availability validation。全量收集本次已声明 EXPLAIN 的 point，不等逐 Change 生成时才评估。
2. 由 runtime 边界取得可信、当前版本、绑定正确的 brief。core 检查位置、scope、span、digest、预算、审核来源与覆盖；workflow 不进行 I/O 或在线评审。
3. 对已人工判定不足或有未支持必答义务的任务，整个 Draft stage 拒绝；`writer calls=0`，无 repair、无部分 Draft artifact。保持当前 all-or-nothing，不减少任务义务。
4. 对未评/身份不可信/绑定过期的任务，拒绝进入正常链路并要求证据审核，分类不同于 confirmed insufficient。非解释型正常任务不因缺 brief 被全局拒绝。
5. 仅人工确认可支持的任务进入现有 writer/parser/finalizer。准入不保证模型输出受支持或完成任务；生成后的逐论断支持和完成度仍需独立审核。

最小结果映射建议复用 `ContentDraftStatus.INVALID_INPUT`，新增 allowlisted `EVIDENCE_INSUFFICIENT`、`EVIDENCE_ASSESSMENT_REQUIRED` 分类，不新增 SUCCESS 空正文或把不足伪装成 GENERATION_FAILED。它表达生成前的资格不满足，不表示 JSON 结构损坏。失败仍 `drafts=()`、`limitations=()`、`requires_human_review=true`；保留现有非 success → run FAILED 机制与上游 artifacts。

结构化定位复用现有 process-local diagnostic 模式，增加 `EvidenceSufficiencyViolation` 和 RunDiagnosticContext 字段，并在已有 CLI `validation_diagnostic` 返回有界固定字段。原文和人工理由留在绑定的审核 brief；diagnostic 只放合法 ID、路径、状态和 reason code。下面是本样本应有的诊断设计，**不是当前程序已返回的结果**：

```json
{
  "category": "EVIDENCE_INSUFFICIENT",
  "change_ref": "C1",
  "operation_type": "EXPAND_SECTION",
  "field_path": "change_plan_report.operations[0].content_points[0]",
  "intent": "EXPLAIN",
  "reason_code": "REQUIRED_ANSWER_UNSUPPORTED",
  "assessment_origin": "TRUSTED_HUMAN_REVIEW",
  "page_refs": ["P1"],
  "source_refs": ["S1"],
  "writer_attempt_count": 0,
  "draft_generated": false
}
```

实际诊断还应有绑定的 brief ID/digest、任务义务 ID；目前没有这份正式 brief，不能伪造它们。运行时失去 process-local diagnostic 后，审核者需能通过 run 保存的定位信息与 brief 身份重新找到原记录。现有 run 的 `sanitized_error` 可存不超过 512 chars 的固定分类/首个 Change/point/brief ID/digest 摘要，不存源文或任意 provider 文本；完整多项记录保留在有界审核 brief。若实际接入不能保障 brief 可追溯保全，则仍停止，不能仅用瞬态属性宣称满足可审查要求。CLI 的新增诊断字段属于必要的失败可审查扩展；不扩展 UI。

### 预计最小落点与兼容策略

- 新 core 模型/纯检查函数；可增加 `ContentDraftInput` 末尾默认 None 的非持久化 brief 字段，维持原四个位置参数；这是必要的附加契约，不是改旧 ContentPoint 含义。
- ContentDraftWorkflow 在第一条 provider 请求前全量检查；每次 run 清空旧诊断。runtime 通过明确操作者输入加载/注入 brief；绝不自动从证据正文取“批准”。没有可信输入路径前不接假审批默认值。
- EndToEndWorkflow 复用失败路径、追加顺序及 run failed。RunDiagnosticContext/CLI 只增加这一准入诊断分支；保留公开结果形状。生成失败不追加 CONTENT_DRAFT。
- 不改变 V1 artifact 字段；不对历史 decode/review 运行新 Gate，不篡改旧 success。旧 success 仅代表原机器契约结果。再次尝试生成是新运行，必须接受当前准入。
- 若上述瞬态契约与 run 摘要能保障审查，不需要 SQLite/codec 改动；只有实际消费链证明不够时才重新评估存储契约。本轮没有修改这些模块。

## C. 本轮修改文件

唯一新增非 ignored 文件是本报告。生产代码、公开接口、正式 tests、codec、SQLite schema、Prompt 均未修改。

ignored `.data/evidence-sufficiency-20261008/red_replay.py` 是可重跑的本地 RED/边界探针，依赖现有 ignored 历史证据包，不加入测试 discovery。它故意保持 RED，不能当成可合并的已完成回归测试或 Gate 实现。其余该目录文件是基线 hash、测试日志和保全结果。

## D. 拒绝与放行行为

| 场景 | 本轮实际行为 | 拟定 Gate 行为 |
|---|---|---|
| 已审计的薄 P1/S1 + C1 | success，LocalWriter 调用 1 次；正文等于真实 artifact | 有可信不足记录则明确拒绝、0 writer calls、保留上游 |
| 同材料，仅生成真正由 P1 支持的 CL3 | success，1 次；支持一个关系不等于完成指南 | 仍拒绝；不能通过短写/删引用降低原任务 |
| 同材料，CL3 只挂存在但不支持的 S1 | success，1 次 | 同一薄输入应生成前拒绝；这不能证明充分输入的坏 claim 会被 preflight 捕获 |
| 充分材料 + 经认可的任务/审核 brief | 当前缺少可信正例；未伪造材料验证准入 | 原检查不放宽，匹配/完整审核则进入正常成稿链路 |
| P 仅主题、S 提供充分一般解释 | 未提供经认可正例 | 可作为一般外部 context；不能升级为第一方承诺 |
| 正常非解释型/structure-only | 沿用既有实现和回归 | 不因缺 brief 全局拒绝 |
| 历史 V1 decode/review | 真实 7 artifacts 等值往返 | 继续只读兼容；不把历史 success 重新认证为商业合格 |

**本轮没有生产拒绝行为改变。已确定不足的任务仍会被现有程序错误放行，不能在运行层假称已阻断。** 本报告作出真实 Draft NO-GO；可执行准入要等附加契约与可信输入闭环补齐。

## E. RED/GREEN、相关测试与完整回归

### 已执行 RED 与真实重建

```powershell
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-20261008/red_replay.py
```

8 项：5 通过、3 预期 RED failures，0 errors，exit=1，0.287s。三个 RED 名称为：

- `test_RED_audited_insufficient_explanation_must_not_generate`
- `test_RED_partial_answer_does_not_complete_selection_guidance`
- `test_RED_existing_related_source_does_not_supply_explanation`

三者均失败于 `writer.calls: 1 != 0; status=success`，不是 import/fixture/拼写错误。五个通过探针核对 Planning 选择、request 等值、真实 report 等值、V1 roundtrip 和普通关系反转仍被接受的边界。最后一项通过只是证实 validator 缺口。

三个 RED 使用同一不足输入、不同本地候选正文，不能冒充三个独立证据包，也不是对所有语义支持情况的覆盖。缺少可信充分正例，因此**未完成用户要求的完整六类准入测试，未进入 GREEN 实现阶段**。非解释型与历史测试在已有 suite 中执行，不能当作新 Gate 的正例。

附加契约补齐后的必要 RED 矩阵：

| 类别 | 需要的独立预期与断言 |
|---|---|
| 不足拒绝 | 原失败包 + 绑定的人工不足记录；结构化位置/义务理由；0 writer calls；无 Draft；上游保全 |
| 充分放行 | 获授权且经认可的短解释包 + 明确问题/义务 + 人工支持记录；正常 writer/finalizer 可用；不设数量下限 |
| 部分支持 | 同一任务多个必答义务只有部分被支持；whole-stage 0 calls；不得删义务或改 task |
| 引用存在不支持 | span 合法但人工标注 TOPIC_ONLY/UNSUPPORTED；不能自动转 SUPPORTED；P/S 贡献分别审查 |
| 正常回归 | 非 EXPLAIN、structure-only、零操作、充分 EXPLAIN；复用原预算/数字/第一方/scope 安全测试 |
| 历史兼容 | 旧 V1 无 brief 的 decode/review 仍成功；历史失败、codec 等值；新生成无 brief 不能冒用旧 success |

另需 stale digest、伪造审核来源、span 越界、第二个 Change 不足时第一个也不调用、new_resource EXPLAIN、清空诊断的少量边界测试。充分材料上的关系反转/装饰引用仍属于生成后质量审核，preflight 不接收未来输出，不能给其测试标成 Gate 能拒绝。

### 现有回归命令与本轮结果

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_change_plan_core tests.test_change_plan_workflow tests.test_change_plan_material_availability tests.test_content_draft_core tests.test_content_draft_workflow tests.test_deepseek_content_draft_adapter tests.test_end_to_end_workflow tests.test_history_serialization tests.test_mvp_composed_flow -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
```

| 执行 | 实际结果 |
|---|---|
| 相关 9 模块首次运行（与完整 suite 并行） | 263 项，27.556s，exit=1；1 failure：`tests.test_change_plan_workflow.ChangePlanWorkflowTests.test_provider_failure_exception_timeout_and_no_retry` |
| 该失败测试单独复跑 | 1 项，0.084s，OK，exit=0 |
| 相同相关 9 模块串行复跑 | 263 项，20.266s，OK，exit=0 |
| 完整 discovery | 1372 项，286.079s，OK，exit=0；无 failure/error/skip |

首次 failure 的断言是 generation_deadline 预期 GENERATION_FAILED、实际 WORKFLOW_TIMEOUT；该子场景设置 generation_timeout=0.01 / total_timeout=0.05。并发运行时可能存在调度竞争，串行复跑通过不独立证明因果；没有修改生产代码、时间阈值或测试断言来消除失败。首次失败记录完整保留，不把它改报为全部一次通过。

日志为 `.data/evidence-sufficiency-20261008/focused-regression.log`、`focused-regression-serial.log`、`full-regression.log`。既有 suite 通过也不能填补充分性语义契约或商业质量金标准。

保全检查：本轮 baseline 记录的 252 个既有 tracked/untracked 路径内容/缺失状态全部不变，唯一新非 ignored 文件为本报告。历史 request.json、history.sqlite3、reconstructed-validated-specification.json 的 SHA-256 与根因审计 G1 三个值完全一致。只读查库 WordPress attempts=0；没有运行 live harness。文档 diff whitespace 检查无错误（与 NUL 有内容差异的 exit=1 是正常结果）。

## F. 未解决风险及继续实施所需材料

- 提供一份获使用授权、人工认可充分的解释材料包及原问题/必答答案范围；允许使用短证据，不要求更多页面、数字或更长输出。
- 确认人工 brief 从可信操作者输入、绑定当前任务/Plan/evidence，并可在进程结束后审查；不能只加一个可由 provider 填写的布尔字段。
- 明确审核粒度及来源使用限制，尤其外部未验证 context 与第一方技术承诺的区别。不能把来源可信性与句义支持合并。
- 若用审核 brief 实施，Gate 验证的是可信人工准入的完整性和绑定，不是自动理解任意原文。原数据无法证明不足时分类为待评，不谎称已证实不足。
- 即使可信准入通过，模型仍可能逆转关系、重复、越题或挂装饰引用；Draft 后的语义支持与任务完成度需独立人工审核。不能靠通过现有 suite 宣称已经解决。

不为了达成实现而新增不能证明的技术词/claim 数/heading/来源数规则。未改变 GEO、UI 或 WordPress 安全边界。

## G. 是否允许进入真实 Draft 验收

**NO-GO。** 当前目标仅完成根因与契约核对、最小落地设计和离线失败重建；可执行 Evidence Sufficiency Gate 没有完成。现有链路仍存在已知误放行，不能据此做真实 Draft 质量验收。

后续先补齐 F 中的最小材料和可信审核输入，完成六类 RED→GREEN 与回归、验证失败的可审查保全，再单独决定真实 Draft 验收。新一次真实 LLM 调用和任何 WordPress 写入仍需各自明确授权。
