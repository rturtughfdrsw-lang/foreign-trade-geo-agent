# SEO Agent 实际执行入口收口（2026-10-09）

本轮把默认 CLI/Live runtime 的 Draft 执行边界收为 fail-closed，并阻断直接真实 Draft adapter 的网络调用。没有可靠的客户身份、当前可信语义审核及客户证据 Draft purpose，故没有增加任何生产放行分支。原生 Planning、Gate、Draft 和 journal 继续复用。TEST GO 限定于本地验证；真实客户流程、商业 Draft 仍 NO-GO。

## A. 实际运行入口与调用图

```text
console script / python -m foreign_trade_geo_agent
  -> cli.main(plan) -> build_planning_workflow

python -m foreign_trade_geo_agent.web / scripts/start_demo.py
  -> create_app -> POST /live/analyses -> LiveApplicationService
  -> LiveComposition.planning_workflow -> build_planning_workflow

build_planning_workflow
  -> shared _compose_planning_workflow
  -> EndToEndWorkflow.run
  -> Crawl -> Packet -> CrawlSeoAuditor -> Research -> Opportunity -> ChangePlan
  -> ContentDraftWorkflow.run -> mandatory admission -> REFUSE, writer=0

explicit isolated TEST root (all external ports supplied)
  -> SAME _compose_planning_workflow / SAME native workflows and validators
  -> fixture writer only, no production route selects this root

Demo POST /analyses -> DemoComposition -> SAME EndToEnd / DraftWorkflow
  -> DemoContentDraftWriter (local fixture, no provider)

direct historical ContentDraftWorkflow.run -> _run -> _generate
  -> DeepSeekContentDraftWriter.write_content_draft
  -> REFUSE unless exact local httpx.MockTransport, no real HTTP client

production_p_only_draft -> SAME ContentDraftWorkflow(None)
  -> run_p_only -> missing consumer/generator -> REFUSE
isolated_test_p_only_draft -> TEST anchors / existing frozen consumer
  -> SAME run_p_only -> revalidate -> deterministic copy generator
  -> original finalizer -> current authority/digest revalidation -> TEST result

Intake register -> request -> submit(CAS) -> native replan(CAS)
  -> current review_candidate / human wait -> no execution permission

CLI review / Live draft GET -> persisted artifact inspection only
CLI deliver -> ApprovedWordPressDraftDeliveryWorkflow -> create-only draft publisher
CLI verify -> read-only remote GET; Demo delivery uses MockTransport
```

可达性依据：`pyproject.toml` 的唯一 console script 指向 CLI；包 `__main__.py` 直接调用 CLI；Web `__main__.py` 指向 `web.app:create_app`；`web.routes` 的两个 start POST 分别选择 Live 与 Demo。Live composition 只调用公开生产 `build_planning_workflow`，不接收 Intake task/receipt/approval 的表单字段。CLI 的 factory injection 是可信 Python 测试/嵌入接口，CLI 参数没有选择 TEST root 或解除授权的开关。

| 入口 | 生产可达性及版本/授权追踪 | 本轮后行为 |
| --- | --- | --- |
| CLI `plan` / Live POST | 真实入口。保存 run_id、SEO goal、artifact ID；这些不是 Intake task_id、task/evidence/Plan version 或授权。DraftInput 原四字段没有 epoch，无法从相同文案反推任务。 | 必须有 admission；没有可信绑定/执行 purpose 时 writer 前拒绝。前五阶段 artifacts 保留，run FAILED，CLI exit 1。 |
| 直接 `build_planning_workflow(...).run`，包括注入外部 ports/旧 admission | 公开 Python runtime。同一生产边界，不把传入对象的允许决定视为执行授权。 | 注入返回 None 的 admission 也拒绝；当前 Intake 可提供明确 stale/task/input 诊断，但不能放行。 |
| 原 `ContentDraftWorkflow.run` / `EndToEndWorkflow` 手工构造 | 内部 workflow/历史兼容 API。源码中除 runtime 和 Demo 外没有另一个用户生产装配点；测试直接构造很多 fixtures。 | 配置 admission 时一律拒绝执行；无 admission 的普通 P/S 验证保留。若手工接真实 DeepSeek writer，adapter 再拒绝真实 transport。 |
| 直接 `DeepSeekContentDraftWriter.write_content_draft` | 可导入的外部 adapter；历史代码可直接调用，因此单封 runtime 不够。 | 默认 transport、真实 transport及未知 transport 都在 HTTP client 构造前拒绝；只保留精确 MockTransport 的本地协议验证。密钥存在也不能解锁。 |
| Demo start | UI 可达，但固定 Demo ports、站点及 SQLite profile；不是客户生产 writer。 | 原 fixture 成功流程保留，普通 P/S/comparison 原 validator 不变。 |
| P-only | 没有 CLI/Web 接到此执行方法的 route；生产 composition 无 trusted root/consumer，TEST composition 明确 TEST anchors。 | 生产拒绝；Intake/runtime 不能借旧 P-only receipt 转义。TEST 仍冻结 task/Plan/evidence/input、独立 Draft purpose、当前 registration/key/grant/revocation 与前后二次验证。 |
| `rebind_plan` / `replan` / reviewer / preflight | Intake 库接口，当前 CLI/Web 没有登录、提交、审批或 Draft endpoint；native replan 调原 ChangePlanWorkflow。 | CAS 和完整 task/evidence/native context 绑定保留。候选或 HUMAN verdict 不是执行 token；没有客户证据 Draft purpose。 |
| `review`、GET results/changes/draft、`deliver`、`verify` | inspection/delivery 只读取已保存 D#，不调用内容 writer。WordPress create-only/draft-only 明确批准边界独立。 | 不扩展、不执行 live delivery、不让新拒绝 run 获得 D#。旧 artifacts 不迁移或删除。 |

全库 `rg` 验证：生产源码中内容 writer 的调用点只有 `workflows/content_draft.py::_generate`，实现只有 DeepSeek adapter 和 Demo writer；所有 workflow 构造点只有 runtime、Demo composition 和 review composition。`scripts/verify_*` 没有 Draft writer 调用；它们各自止于 research/opportunity/change plan/独立 GEO，不运行本轮。新 TEST root 在生产源码中只有定义，没有 CLI/Web/scripts 调用点。这是可达性审计，不声称抵御能任意执行/修改 Python 代码的攻击者；注入任意自定义外部 ports 或 MockTransport handler 属于可信开发代码边界。

## B. 已发现的绕过风险

1. 默认 runtime 的 admission 为 None，CLI/Live 自动 Planning→Draft；Intake 版本更新不影响该路径。已改为强制装配。
2. 旧 admission 的返回 None 能被理解为批准，但 port 不提供可信身份、Draft purpose、输入冻结或跨 writer await 的原子性。已明确拒绝该允许值。
3. 原 DraftInput 不带任务/证据 epoch，旧 Plan 文案可能与新 Plan 完全相同；给旧输入包装新 digest 不可能证明原请求的新资格。保留明确拒绝，不通过内容 hash 推断授权。
4. 直接真实 adapter 调用能绕过 workflow。已拒绝全部非 MockTransport transport；只检查 workflow 不足以覆盖这条旧 Python 调用路径。
5. 原 Live 只读页面只允许 SUCCEEDED run；生产 Draft 拒绝后用户看不到原生 Plan。现允许在固定 `content_draft.invalid_input` 终止下只读原生规划，仍拒绝读取 Draft、成功状态或任何交付授权。Live 错误页也修复为使用 Live 导航。

仍未完成的生产能力是可信身份/审核/执行授权，而不是某个允许开关。测试 port、JSON 来源声明、材料数量、人工候选、缓存 GREEN 或旧授权均不能代替它们。

## C. 实际修改和兼容性

| 文件 | 本轮变化 |
| --- | --- |
| `runtime.py` | 原公开生产签名保留，默认强制 admission；一个私有共享对象图，显式 isolated TEST helper 要求全部外部 ports，没有第二套规划。 |
| `evidence_review_composition.py` | 增加无放行分支的 ProductionDraftAdmission，复用已有生产 review composition 的拒绝策略。 |
| `workflows/content_draft.py`、`core/ports.py` | 明确 admission 仅提供绑定诊断；None 不是执行授权。异常和任意 reason 均固定脱敏，无 writer/重试/await 允许窗口。 |
| `workflows/evidence_intake.py` | 现有 guard 检查 store 返回的精确 snapshot 类型及 project/task_id；错误任务拒绝。 |
| `adapters/deepseek_content_draft.py` | 直接调用时拒绝真实网络 transport；本地 MockTransport 协议预算/验证仍照旧。 |
| `web/live_application.py`、`web/app.py` | 拒绝 Draft 后原生 Plan/Results 仍可审阅；新 Draft 不可取得；Live 错误使用 Live 导航。 |
| README、architecture | 更新当前生产行为及历史成功示例适用范围。 |
| 新 `tests/test_draft_execution_boundary.py` | 14 个独立 synthetic/生产入口/竞态/伪造/旧路径测试。 |
| 8 个既有测试文件 | 3 个成功 Draft/诊断测试改用显式 isolated TEST root，复用原 validators；Live/文档测试改验新拒绝行为。没有删除测试或减弱 Gate。 |

普通 P/S、P-only、EXPLAIN、comparison 的原有合同和验证器没有改变。生产真实 Draft 的行为有意收紧，不能宣称其旧调用仍能执行；旧成功 artifacts/序列化/digest/DB schema 与 create-only/draft-only delivery 保持兼容。没有 artifact 破坏性迁移、第二套 Planning/Gate/Draft、新 provider 或 Windows 配置变更。

## D. 端到端 synthetic 正负例

[BellHarbor/F9 样例](draft-execution-synthetic-2026-10-09/README.md) 使用独立虚构出口过滤器企业，不复用上一轮 LumenSeal 或 NovaCNC 的事实/审批。原生五阶段从 Crawl 到合法 EXPLAIN Plan 实际运行并存储。

| 步骤/攻击 | 观察结果 |
| --- | --- |
| 原 SEO 任务，P/S 仅有主题 | 具体请求精度单位/型号/介质/温度/测试方法，以及壳体材料/工况/排除条件。 |
| 第一次只补精度资料 | 同一 task goal、requirements、task_version 保留；新 evidence=2；原 Plan unbound；原生 replan 后 F1 等人审，F2 仍缺资料。 |
| 第二次补壳体资料 | evidence=3、Plan=3、revision=5，五个不同 snapshot digest；原 P/S/A 不变，客户声明作为独立不可信 context 给同一个 Planner。 |
| 资料结构完整 | F1/F2 仍 UNREVIEWED，`HUMAN_SEMANTIC_REVIEW_REQUIRED`，不证明 EXPLAIN 事实/适用性/因果深度。 |
| 十个旧/当前 Input×digest 组合 | 全部拒绝，writer=0。新 digest 包装旧等值文案也只有无执行权的当前候选。 |
| 默认 CLI，无替换 planning factory | 正常原生 artifacts=5，exit 1，writer=0。只替换外部 ports 为本地 fixtures。 |
| 实际 Live POST，伪造 approved/task/reviewer/Draft 字段 | form 不能装配权威；同一 runtime 拒绝，artifacts=5，Plan GET=200，Draft GET=503，writer=0。 |
| 旧公开 runtime/admission、直接旧 workflow、真实 adapter | permissive admission 不放行；默认/非 MockTransport adapter 在 HTTP 前拒绝；旧 P-only receipt 不能切换 task profile。 |
| 错误任务、未知状态、伪造来源/允许字符串 | 固定 task/state/blocked 原因，异常 canary 不出现在 report；writer=0。 |
| admission 内输入替换 | 测试实际修改输入语言后返回 None；仍拒绝，不执行已替换输入。 |
| 另一线程在 binding read 后提交 | SQLite 新 evidence/未绑定 Plan 已落地，旧快照即使先读成功也无执行分支；下一次读明确 STALE，writer=0。 |
| 重新规划/人审期间并发版本更新 | 既有 native Intake 测试实际 CAS 拒绝旧输出/旧 assessment。 |
| 过期、撤销、伪造来源/签名、registration/key/grant 改变 | 既有 P-only TEST 负例验证前检查与后生成二次验证；无客户证据正式授权分支可借用。 |

第一部分补资料不是自动支持 F1：本独立样例明确保留待人审；已有上一轮 TEST 显式 HUMAN fixture 的支持/冲突/无关负例也保留。新测试不调用真实客户、不提交正式签核、不产生商业文案。

## E. 当前绑定和 Draft 授权边界

Intake 请求冻结的是明确 project/customer/task、task_version、Plan version、evidence version、revision、完整 native site/Opportunity/Plan/Input、义务与客户资料的 snapshot digest。每次补充使旧 Plan unbound，新重绑定增 Plan version，append CAS 拒绝并发旧 digest。Opportunity 没有另造 revision 字段，完整原报告包含在 snapshot 中；更新网站/研究/Opportunity 仍要新任务导入，不在现有补资料 profile 内。

当前版本、语义充分性、执行授权是三个独立条件。digest/材料/spans 是追溯材料，不能证明客户或 reviewer 身份。真实运行缺少这些可信生产边界，因此统一拒绝；不会在检查之后 await writer，不存在允许分支的输入替换、版本或撤销窗口。这里没有声称实现生产原子执行 lease：不能保证原子性时按本轮要求明确拒绝。P-only TEST 保留既有私有解码冻结图和生成前后权威/版本重验，仍无生产许可。

CLI/Live 的新 run_id 不是原客户 task_id。原任务注册/客户登录/提交、可信人审源、正式客户证据执行 purpose 尚未接入生产 route，本轮没有伪装自动完成这些能力。生产 Planning 本身仍可能调用真实 crawl/search/LLM，需具体 live 授权；本轮运行均为 injected local fixtures。

## F. 回归测试及 Git 安全检查点

最终验证结果、命令、迭代失败、完整文件分类与本轮 hash 保存在 [verification JSON](draft-execution-verification-2026-10-09.json)。原始日志和完整 turn 前文件副本在 ignored `.data/draft-entry-20261009/`。

最终针对性组合 **326 tests / 54.162s / OK / exit 0**；完整回归 **1560 tests / 248.061s / OK / exit 0**，相较上一轮 1546 新增 14 项。源码和测试在最终针对性/完整回归期间冻结，最终逐文件 hash 相同。`git diff --check` exit 0，新文件另做 whitespace 检查。完整回归尾部 Demo/8000 端口提示来自既有 mock tests，不是实际启动服务或失败。

迭代失败如实记录：初始 6 项均失败，先定位 synthetic HTML 缺 description 使原生 shape validation 拒绝，补全 fixture 后 6 项复现缺失入口保护；完成保护后 5 项通过，1 项因新测试误写 `EvidenceGap.code` 报错，修为真实 `reason_code`。165 项组合首次 8 failures/9 errors 来自旧生产 Draft 成功预期及 Live 结果读取，改为明确 TEST root 和生产拒绝/只读配套；第二次 1 failure/1 error，分别为 Live 错误页用了 Demo 导航、测试误读 view 的 Plan 字段，修正实际导航和读取原生 persisted Plan；随后 24 项边界组合通过。样例生成首次因独立脚本 import path 未包含 repo 根而失败，补上本地路径后成功。没有提高预算、弱化 Gate 或移除有效断言。

Git 起始：分支 `feat/live-site-analysis`，HEAD `fedcb3b7a8ffb3e3480c9807d5831ddd89dfc148`；逐文件分类 **79 modified、193 untracked、1 deleted、0 staged**。既有删除是 `tests/test_history_migration_v1_to_v2.py`，保留；不要只因删除存在而恢复它，先与新增 `test_history_migration_to_v3.py` 一起审阅。405 个起始路径均记录 hash，未被本轮指定修改的路径逐字节核对。没有执行 stage/commit/push/reset/clean/rebase/merge 或删除分支。

最终分类 **79 modified、205 untracked、1 deleted、0 staged**。本轮仅变更 **18 个已有文件**（8 source、8 tests、README/architecture），其余 **387 个起始路径**含原删除状态不变；新增 1 个测试文件、入口报告/验证摘要、9 个 synthetic 示例文件。完整逐文件分类见 verification JSON，避免把当前整份 dirty diff 归为本轮工作。

| 累积功能阶段 | 主要代码/测试范围及提交依赖 |
| --- | --- |
| 通用 SEO/Crawl/Web Live | `_page_worker`、CrawlSeoAuditor、research_query/live_analysis、research/opportunity/site packet/end_to_end、runtime/CLI、web composition/service/routes/templates/static、对应 Live/no-network/security/fixtures 测试与 verify scripts。 |
| Draft 合同/数值/claim/comparison | core change_plan/content_draft/content_opportunity、原 workflow/finalizer、DeepSeek 提示、comparison schema/admission、numeric/claim/block/table/competitor 测试与报告。多个文件与前后阶段有共享 hunks。 |
| History 与迁移 | core/history、storage serialization/sqlite、schema/migration-to-v3 测试及既有 v1-to-v2 测试删除；需与契约同时验证，不能单独提交删除。 |
| First-party / Sufficiency / Review authority | core first_party_planning/evidence_sufficiency/review_authority/registry，adapters review/registered/client/host/signing/CNG/protocol，storage receipts、persisted/preflight workflows、composition、Windows inventory script、review packages 和相关测试。生产安装仍拒绝。 |
| P-only TEST 消费 | core/adapters p_only_draft、既有 ContentDraftWorkflow 的显式方法、composition、消费/缺口/撤销/过期测试；依赖前一阶段 authority，不等于普通 Draft 授权。 |
| Customer Intake → native replanning | core/storage/reporting/workflows evidence_intake、customer_evidence adapter、change_plan customer_context、native integration tests/样例；依赖原契约/Planning。 |
| 本轮生产执行收口 | runtime、review composition、Draft admission/adapter、Live 只读错误处理、14 项新测试及显式 TEST 回归调整；依赖前述模块。 |

建议人工按依赖分批提交：①通用 SEO/Live；②原生 Draft 合同及配套 History 迁移；③First-party/Sufficiency；④Review authority/receipts（Windows 部署文档单独核验）；⑤P-only TEST；⑥Intake/native replanning；⑦本轮入口收口。拆分时对共享文件逐 hunk 检查，在单独 review checkout 中验证每批完整状态；若无法形成可独立通过测试的批次，应合并相邻依赖批，不能按文件扩展名机械拆分。最终 docs verification/样例跟对应阶段一起审阅。这只是方案，没有自行 stage/commit。

敏感/生成文件审计：

- Git 只跟踪 `.env.example`；`.env`、`.env.*`、`.data/`、`.venv/` 被忽略。测试日志、SQLite、before patch、完整本地备份均放 `.data/`，没有加入 Git。
- 全部非忽略路径做不输出匹配值的 secret-name/token/private-key 启发式扫描；发现 literal assignments 均是既有 TEST/Demo placeholder。不能据此声称穷尽式秘密检测。
- `tests/fixtures/safe_http/safe-test-key.pem` 是**既有 tracked 私钥 fixture**，对应 CN=`safe.test` 的本地 TLS 测试，不是新添加的部署密钥；其使用仅限本地 TLS fixture，提交前仍应核对其来源，禁止复用于生产。未输出私钥内容。
- 根目录任意 `.log`/`.sqlite3` **不会被现有忽略规则覆盖**；以后运行产物应留在 `.data/`，每批提交显式审查路径，避免 `git add .` 带入。未自改忽略规则。
- docs 已有 70 个 JSON（本轮样例生成前），包含冻结 TEST inputs、review packages、验证摘要；属于可审阅 generated fixtures，需核对 synthetic 标签、没有真实客户材料或 raw responses，再决定入库。Windows runbook 含 SID 格式/身份示例，属于身份/环境元数据，发布前人工检查；不输出具体 SID。

恢复方案：先保留 `.data/draft-entry-20261009/baseline-files/`（包括起始 untracked 内容）、`baseline.json`、`tracked-before.patch`、`git-status-before.txt` 和最终 turn diff。Git diff 无法备份 untracked，因此不能只依赖 patch。需要回退本轮时，在无后续编辑的前提下逐文件对比 before/final hash，只恢复本轮指定修改；新文件另存、由人工决定移出，保留原删除状态。若存在后续编辑，必须三方合并 before/current/turn-final，不能整体覆盖工作树。提交后的修正采用经授权的新提交/revert；本轮不执行任何恢复或 history 操作。本地 `.data` 不是异地备份，正式分批前可由操作者另做受保护的副本。

## G. 独立 GO / NO-GO

| 范围 | 结论 |
| --- | --- |
| TEST：本地统一入口、native Intake/replanning、人审等待、负例拒绝 | **GO（有界 TEST 验收）**。不代表生产身份或授权已实现。 |
| 真实客户完整业务流程 | **NO-GO**。登录/提交、原任务可信导入、当前可靠语义 reviewer、生产 route 和正式授权仍缺；保留拒绝。 |
| 商业/正式 Draft | **NO-GO**。没有 production execution purpose 或可靠原子/二次授权执行方案；真实 writer transport 拒绝。 |
| WordPress、发布、生产签核 | **NO-GO（本轮未授权/未执行）**。既有 create-only/draft-only 独立批准边界保持。 |

本轮无付费 LLM、真实外部网站、WordPress、正式 Draft、生产签核、Windows 安全配置变更或 Git 写入历史动作。
