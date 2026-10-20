# 普通 SEO Draft 离线验收与受控 DeepSeek 准备

日期：2026-10-08。依据本轮实际源码、只读历史检查和新执行结果；前轮报告的测试数字未作为本轮通过依据。真实 DeepSeek 调用、客户站点访问、真实 WordPress 写入均为零；没有 commit / push / merge。

## A. Git 工作区与变更边界

开始及报告编写前的工作区共有 79 个 modified、1 个 deleted、37 个 untracked；原有删除的 `tests/test_history_migration_v1_to_v2.py` 未恢复。报告新增后 untracked 增加一个。工作区远大于上一轮的比较准入改动，不能把当前整份 `git diff` 归为本轮修改。

读取了 AGENTS.md、两份 comparison 报告及当前 core、workflows、adapters、runtime、CLI、codec、SQLite、组合测试和验证脚本。相对本轮开始的 248 个现存 tracked/untracked 文件 SHA-256 快照，只有下列两个现存文件变化；其他既有文件字节不变：

1. `src/foreign_trade_geo_agent/adapters/deepseek_change_plan.py`：保留直接 adapter 的特定比较拒绝码。
2. `tests/test_comparison_admission.py`：新增一项 HTTP 前拒绝及类别回归。

新增可纳入版本管理的文件仅本报告。`.data/seo-draft-acceptance-20261008/` 内的本地验收脚本、SQLite、请求材料、结果和日志均被现有 `.gitignore` 忽略；它们是本地可复现验收设施，不接入产品执行路径。`accept_offline.py` 复用已有组合 fixture，`accept_deepseek.py` 复用它和现有生产 provider、workflow、codec、store、环境加载器，没有另建生产架构。

没有修改数字 grammar、Prompt、core、Draft workflow、Runtime、CLI、codec、SQLite schema、审核/交付逻辑或 GEO 分支；已有无关 dirty 改动保留。没有 reset / clean / stash。

## B. 安全准入独立复核结果

| 性质 | 结果 | 源码和执行证据 |
|---|---|---|
| 普通 Planning 不依赖比较 | PASS | `_derive_allowed_operation_types` 跳过比较 action，其他 action 独立推导；真实 CLI/Runtime 的新无比较 Plan 成功。 |
| 普通合法 Plan 可进入 Draft | PASS | 新 `EXPAND_SECTION`、`ADD_SECTION` 经生产 Planning adapter、workflow/finalizer 后进入 Draft；旧无表 V1 正向路径也在现有测试中覆盖。 |
| 直接/嵌套比较被拒绝 | PASS | `comparison_operation_error` 同时检查 operation type、source action、顶层 schema、resource purpose 和 nested brief；Planning common 校验后进入该拒绝，Draft 在 provider 前检查整份 Plan。 |
| 比较拒绝码 | PASS（修复后） | 工作流、Draft adapter 和直接 Planning adapter 为 `COMPARISON_UNAVAILABLE`。无效公共字段仍遵循原先首错顺序。Run diagnostic 仍映射到既有 `OPERATION_NOT_ALLOWED`，不改变 SQLite CHECK。 |
| 跨层无比较执行旁路 | PASS | 源码检索确认 Runtime/CLI、web composition 共用 `ContentDraftWorkflow`；公开 builder、prompt constructor、直接 finalizer 和 Draft adapter 都检查比较资格。Planning adapter 复核确定性材料；其 raw generation 不是可执行 Change，仍需 Planning finalizer。 |
| 历史 C2 不能因兼容读取重获执行资格 | PASS | 真实旧库只读 decode 后，整份输入和 C1/C2 prompt builder 均拒绝；Draft writer calls=0。缺少旧兼容字段的合成 V1 测试同样拒绝。 |
| 既有 Change 未静默删除/改写 | PASS | 真实旧 Plan 保留 C1/C2/C3；数据库字节摘要前后相同。新材料仅报告不可用 R，不改原 opportunity artifact；整份已有含比较 Plan 不进行部分 Draft。 |
| V1 codec / SQLite 兼容 | PASS | 真实库 user_version=4，五个 payload_version=1 artifact decode/encode/decode 等值；无 schema/codec 修改。当前回归含历史 migration、serialization、SQLite 测试。 |
| 普通 Draft 能力未被关闭 | PASS（离线范围） | 正常两个 section draft 持久化、重新读取、CLI review 成功；既有其他普通操作单元测试保留。 |

真实历史证据：`.data/task17-final-acceptance/fresh-cli-3c5d419bdf5d4c07bf68d5fa20dcb96d.sqlite3`，run `86d25a34-31de-4808-91c3-b0ed89461960`。使用 `sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)`，没有实例化会迁移该历史库的写入 store。五个 artifact 分别为 site_content、site_audit、industry_research、content_opportunity、change_plan；该 run 没有历史 Content Draft，不能声称通过了真实旧 Draft 成品读取。合成旧 table Draft 读取由现有 serialization 测试验证。

## C. 普通 SEO Draft 离线端到端验收

最终成功输出：`.data/seo-draft-acceptance-20261008/offline-27174d3c58b84f83bc96751ca07b41fb/`。

- 成功 run：`2410caf4-762b-49c1-8902-5056007c602a`。
- Content Draft artifact：`c75c07e1-d3ae-4dbd-ac2e-7714bf30148b`。
- 新 C1=`EXPAND_SECTION`，新 C2=`ADD_SECTION / TECHNICAL_DOCUMENTATION`；这里的 C2 是新普通操作，和历史比较 C2 没有身份关系。
- `summary.json`、`success-cli.json`、`review-D1.json`、`review-D2.json`、`draft-requests.json`、`history.sqlite3` 可直接复查。

执行路径是现有 `cli.main(plan, planning_factory=...)` → `build_planning_workflow` → `EndToEndWorkflow`，使用生产 extractor、`CrawlSeoAuditor`、Planning workflow/finalizer、`DeepSeekChangePlanWriter`、`ContentDraftWorkflow`、`DeepSeekContentDraftWriter`、SQLite/codec、真实 `cli.main(review)`。Crawler 和 research/search/opportunity provider 使用已有 fixture；两个 DeepSeek adapter 的 HTTP 边界为明确的 `MockTransport`，没有 DNS/真实网络请求。离线期间拦截 DNS、同步外部连接和 delivery workflow 构造。

| 环节 / 要求 | 状态 | 实际证据 |
|---|---|---|
| 持久化证据 → Planning | PASS | Planning HTTP mock handler 先从新 SQLite 读取 SITE_CONTENT 和 CONTENT_OPPORTUNITY，确认它们已持久化。P1 来自真实 extractor 对本地 HTML fixture 的提取；S1 来自固定 mock search 材料。 |
| Planning → Change Plan 校验 | PASS | provider 响应选择实际 CP/LOC/PH catalog 引用，经过生产 parser/finalizer；Plan 有两项合法普通操作，无任何比较 schema/brief。ADD_SECTION 选择合法 PH_02，避免 PH_01 原有的重复 Guide 候选，无产品规则改动。 |
| Draft 输入构造 | PASS | EndToEndWorkflow 构造完整输入；Draft HTTP 前从持久化 artifact 重建输入，`stable_content_draft_input_error` 为 None。 |
| Draft adapter | PASS | 两次生产 Draft adapter 请求，由 HTTP mock 返回固定 JSON；模型、字段、英文 system/user 材料沿现有路径构造。 |
| Draft 结果校验 / 与 Plan 对应 | PASS | D1/D2 对应 C1/C2、R1/R2、P1、原 locator 和批准的 proposed heading；均为 SECTION_DRAFT。主体文本围绕两项 Plan 的 Chemical Compatibility content point。 |
| A：证据引用有效 | PASS（fixture） | observed claim 绑定真实持久化 P1；外部 context claim 绑定 S1，并与 review 中 S1 excerpt 完全相同。P999 反例得到 UNKNOWN_PAGE_REFERENCE。S 为未验证外部材料，不升级为第一方承诺。 |
| B：不接受错 Change | PASS | C999 反例最终 UNKNOWN_CHANGE_REFERENCE；已有一次受限修复 retry，合计 3 次 mock Draft HTTP（C1 一次、C2 两次），没有成功 artifact。 |
| C：计划外结构化比较表格 | PASS | 普通输出仅 PARAGRAPH/BULLET_LIST；注入 COMPARISON_TABLE block 得到 FIELD_CONTRACT，没有 Draft artifact。比较 Plan 的准入拒绝另由 B 节证明。 |
| D：JSON / 字段契约 | PASS | 正向报告成功并经 V1 codec 读取；错误 JSON 得到 JSON_FORMAT，结构错误被拒绝。 |
| E：失败可诊断 | PASS | CLI 输出 stopped_stage=content_draft、failure_kind=content_draft.invalid_output、validation_diagnostic.category；每个失败 CLI JSON 单独保存。 |
| F：单条 Draft 失败的数据保全 | PASS | C1 成功而 C2 失败时整份 Draft all-or-nothing，不持久化部分 Draft；该失败 run 的五个上游 artifact 保留。四个失败 run 使用同一库，原成功 run 的全部 artifact ID/payload 前后相同。 |
| 持久化 / 重新读取 | PASS | 成功六个 artifact 均 V1；重新构造 SQLiteHistoryStore 和 CLI review 读取 D1/D2，schema v4。 |
| G：人工审核边界 | PASS | run/report/draft 要求审核；review 明确 NOT RECORDED、READ ONLY。读取不产生批准状态。 |
| H：WordPress 写入 / 发布 | PASS（零副作用） | 每个 run 的 WordPress attempts 为空；未构造 delivery workflow，未调用 deliver。 |
| CREATE_NEW_RESOURCE、链接、重排的本轮 E2E | NOT TESTED | 本轮两个操作足以覆盖普通 Draft adapter 与结构契约；其他普通类型只引用实际执行的现有回归，不伪造本次 E2E 覆盖。 |
| 真实 LLM 内容质量 | NOT TESTED | 两条 fixture 正文只证明链路与校验，不是商业成稿或真实 LLM 质量验收。 |

引用存在、类型/scope/数字规则正确，不能自动证明任意生成句子的完整语义蕴含或商业可用性。真实请求之后仍须逐句对照材料并人工评估相关性、充分性、语言质量及是否出现未经支持的对比/承诺。

## D. 发现的问题及最小修复

发现且修复一个 adapter 诊断缺口。复现：向 `DeepSeekChangePlanWriter.write_change_plan` 直接传入只有 ADD_COMPARISON_TABLE action 的合法 prompt；HTTP calls=0，但 error 为 `Change plan provider material is inconsistent (FIELD_CONTRACT).`，丢失核心返回的 COMPARISON_UNAVAILABLE。

根因：adapter 原来将 `validate_provider_generation_material` 的所有非 None 错误映射成同一通用消息。修复仅捕获其中 `ChangePlanValidationCategory.COMPARISON_UNAVAILABLE` 并返回原码；其余拒绝、调用位置及 FIELD_CONTRACT 消息保持原样。没有放宽准入，也不增加 retry。

新增 `test_direct_planning_adapter_preserves_comparison_refusal_before_http`：先 RED（1 failure，精确错误码不匹配），再 GREEN；同时验证 FAILED、具体码和 requests=[]。除此无需生产修复。

本地探针早期三次失败均是验收脚本自身：拦截 socket.connect 破坏 Windows asyncio 内部 self-pipe；误读 CLI 不存在的 terminal_report 字段；对 UNKNOWN_CHANGE_REFERENCE 的现有一次 retry 少计一请求。分别以既有网络阻断方式、真实 validation_diagnostic 字段、3 次 mock 请求预期纠正，没有修改生产实现或降低断言。

## E. 测试命令和实际结果

1. 当前上下文恢复后的相关回归：**391 tests / 38.211s / OK / exit=0**。

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_comparison_admission tests.test_change_plan_core tests.test_change_plan_material_availability tests.test_change_plan_workflow tests.test_content_draft_core tests.test_content_draft_workflow tests.test_deepseek_change_plan_adapter tests.test_deepseek_content_draft_adapter tests.test_history_serialization tests.test_history_migration_to_v3 tests.test_sqlite_history_store tests.test_runtime tests.test_cli tests.test_end_to_end_workflow tests.test_mvp_composed_flow -q
```

2. 新回归 RED：**1 test / 1 expected failure / exit=1**；修复后相关模块 **166 tests / 14.536s / OK / exit=0**。

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_comparison_admission.ComparisonAdmissionTests.test_direct_planning_adapter_preserves_comparison_refusal_before_http -v
.\.venv\Scripts\python.exe -m unittest tests.test_comparison_admission tests.test_deepseek_change_plan_adapter tests.test_change_plan_workflow tests.test_deepseek_content_draft_adapter -q
```

3. 首次完整回归在最小修复前启动，**1371 tests / 306.440s / OK / exit=0**。它不是最终修改状态的通过依据。

4. 最小修复后的最终完整回归：**1372 tests / 299.563s / OK / exit=0**。日志 `.data/seo-draft-acceptance-20261008/full-regression-final.log`。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
```

5. 修复后离线 CLI E2E：**5/5 cases / exit=0**；成功 case exit=0，四个预期失败 case 的 CLI exit=1。可复现命令：

```powershell
.\.venv\Scripts\python.exe .data/seo-draft-acceptance-20261008/accept_offline.py
```

6. 受控 harness 默认 PREPARE：**exit=0，真实请求=0**。`--mock-case success/bad_json/wrong_change/secret/http_401` 五项全部符合预期退出码（0/1/1/1/1），每项最多一次 mock HTTP，JSON 和 SQLite 均未保存 mock secret。结果保存于 `.data/seo-draft-acceptance-20261008/controlled-mock-matrix.json`。历史只读 probe exit=0；`git diff --check` exit=0。新报告另以 `git diff --no-index --check -- NUL docs/seo-draft-offline-acceptance-2026-10-08.md` 检查，无 whitespace 输出，exit=1 表示文件与 NUL 不同。最终检查不使用前轮测试数字。

7. 真实模块 CLI 只读入口另执行成功（exit=0），输出 `.data/seo-draft-acceptance-20261008/module-cli-review-D2.json`，确认 D2、NOT RECORDED、READ ONLY；没有联网或 delivery：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent review --db .data/seo-draft-acceptance-20261008/offline-27174d3c58b84f83bc96751ca07b41fb/history.sqlite3 --run-id 2410caf4-762b-49c1-8902-5056007c602a --artifact-id c75c07e1-d3ae-4dbd-ac2e-7714bf30148b --draft-id D2 --format json
```

完整回归输出存在既有 StarletteDeprecationWarning、asyncio 慢任务提示、CLI 负向参数测试的 usage/error 和 mock demo 启动/端口提示；这些不等于测试 failure，也不应隐瞒。

## F. 下一轮真实 DeepSeek API 验收方案

**本轮未执行；以下 live 命令必须先获得用户对这一次付费请求的明确授权。**

已有 provider 支持 injected transport、固定 deepseek-flash、thinking disabled、temperature=0、max_tokens=3000，HTTP 本身不重试；ContentDraftWorkflow 对部分校验错误可能进行一次 repair。仓库没有独立 verify_content_draft 脚本，verify_change_plan 只验证 Planning；直接运行真实 `plan` 会额外 crawl/Tavily/多个 LLM stage，超出最小 Draft-only 范围。

因此本地 controlled harness 复用生产 DraftWorkflow + adapter，并在 transport 层限制一次请求、35 秒 generation / 45 秒 workflow 超时；repair prompt 被 observer 阻断，保留首个 validation category，不进行第二次真实 HTTP。只有精确 `POST https://api.deepseek.com/chat/completions`、指定 model/thinking/token 设置、两条 message 总 UTF-8 字节 ≤16,000 的请求能放行，底层 transport retries=0。无 WordPress publisher。

默认准备命令（已运行）：

```powershell
.\.venv\Scripts\python.exe .data/seo-draft-acceptance-20261008/accept_deepseek.py
```

已准备可审查样本：`.data/seo-draft-acceptance-20261008/prepare-/6df5e84a89264e0cb44fa277974041e0/`，`prepared-request.json` 含确切 system/user 材料，`review-D1.json` 含新无比较 C1 和 P1/S1；当前两条 message 总计 **8,497 UTF-8 字节**。样本来自本地合成 HTML / research fixture；它可以验收真实 LLM 的普通 Draft 输出，不代表真实客户材料的商业效果。

授权后的可执行命令（本轮没有运行）：

```powershell
.\.venv\Scripts\python.exe .data/seo-draft-acceptance-20261008/accept_deepseek.py --execute-live
```

该命令先用 mock 上游及 mock Draft 构建全新单项 EXPAND_SECTION Plan，验证并持久化；随后只针对该新 Plan 调用一次真实 Draft provider，不读取或修改历史 C2。DEEPSEEK_API_KEY 只由既有 `scripts.local_env.load_api_keys` 在 live 分支加载，不输出键值；API Key 配置存在仅说明本地有非空值，本轮未验证凭据有效性或账户余额。

请求/响应诊断：保存不含 headers/cookies 的确切 synthetic request JSON；只记录 HTTP status、受限 model 字符串、finish reason、响应长度、数值 usage、generation/final validator category 及 repair 是否被拦截。原始 provider 错误体不落盘、不打印。输出含当前密钥、Bearer/API key/password/authorization 标记时直接拒绝并仅记录安全原因。成功的 validated Draft 作为**新 artifact**追加到该新 mock 准备 run，旧 mock Draft 不覆盖；`diagnostics.json.result_artifact_id` 才是实际这次响应的 artifact 身份，不能以准备 run 的 SUCCEEDED 或旧 mock Draft 宣称 live 通过。

预计付费请求 **1 次**；crawler/Tavily/research/planning provider 的真实请求 **0 次**；WordPress **0 次**。输出 hard cap **3,000 token**。输入 exact token 数在响应 usage 前未知，不把 chars/bytes 冒充 token；message 上限 16,000 bytes，加 1,024 framing token 余量作保守成本估算。

2026-10-08 查阅 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)：deepseek-flash，峰时 cache-miss input $0.30 / 1M tokens，output $1.20 / 1M tokens；按峰时和全 cache miss 估算，当前样本上限约 **$0.00646**，本地输入 byte 护栏极限约 **$0.00871**。下一轮拟授权费用预算 **US$0.01**。这是当前价格及保守分词假设下的估算，非提供商账户侧硬美元限额；以真实 usage 结算，授权前若价格/模型变更需重新核算。无需余额查询 API，不增加调用。

验收标准分开记录：

1. HTTP 成功、正常 stop、未截断、JSON 和 exact field contract 合格；真实请求≤1，usage/模型诊断完整。
2. 新 C1 的 Draft 类型/引用/locator/内容主题与 Plan 一致；P/S 有效、scope 正确、第一方和外部 context 分离、数字规则未放宽；没有新增表格或未经计划授权的比较。
3. 成功 artifact V1 往返读取，人工逐条审查真实正文和 P/S：来源支持、没有新参数/承诺/竞争者事实、主题覆盖充分、英文可用；JSON/校验成功不代替这一步。
4. requires_human_review 保持 true，WordPress attempt=0。以新真实 result artifact 审查，不审查准备阶段的 mock artifact。

授权后用 diagnostics 中的身份读取实际响应：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent review --db '<live目录>/history.sqlite3' --run-id '<diagnostics.plan_run_id>' --artifact-id '<diagnostics.result_artifact_id>' --draft-id D1 --format json
```

停止条件：缺密钥或 preflight/材料/预算失败时零真实请求停止；HTTP 401/403/429/5xx、网络异常/超时、非 JSON、缺文本、非 stop/截断、contract/grounding/引用失败、敏感输出立即停止，不重发；repair 类错误只记录原类别并阻断 repair HTTP。真实内容质量不合格同样停止，另开最小诊断，不扩大 Prompt、grammar 或比較能力。结果即使 schema SUCCESS，内容质量仍须人工明确判定，不能自动升级为生产准入。

## G. GO / CONDITIONAL GO / NO-GO

| 对象 | 判断 | 边界 / 下一步最小动作 |
|---|---|---|
| 普通 SEO Draft 离线能力 | GO | 两种普通操作在实际 CLI/Runtime/adapter mock HTTP 链路通过，失败保全和审核边界通过；最终 1372 项回归通过，不声称真实 LLM 质量。 |
| 真实 API 验收准入 | CONDITIONAL GO | 已具备可执行单请求、低成本、诊断脱敏方案；下一步仅需用户明确授权本方案的这一次 DeepSeek Draft 请求。凭据有效性/余额及真实响应/质量 NOT TESTED。 |
| 旧比较操作 / 比较 V2 | NO-GO | 继续 COMPARISON_UNAVAILABLE；保留历史数据，不裁剪旧 Plan 来执行，不恢复表格。 |
| WordPress 交付 | NO-GO（本轮及下一次 Draft smoke） | 当前没有真实内容质量结论，也没有特定交付授权；计划/读取成功不能授权写入或发布。原 create-only/draft-only 能力及其 mocked tests 不代表本轮真实交付验收。 |

这三项证据必须保持分离：**单元/回归通过；离线组合链路通过；真实 LLM 内容质量尚未验收。**
