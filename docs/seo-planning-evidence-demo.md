# SEO Planning → Evidence Intake 本地演示

日期：2026-10-10，Asia/Shanghai。**交付范围：原任务导入、补证、原生 Plan 重新核对、待审包；生产 NO-GO、PostgreSQL BLOCKED 保持。** 全部示例是明确标注的 **SYNTHETIC NovaCNC / VMC-DEMO**，不代表真实客户、认证、工程性能或人工批准。

## 已检查的实际链路与本轮补齐

主 `cli.py plan` 和 `web/composition.py` 的 Live 共用 `runtime.build_planning_workflow`。原链按 Crawl → Packet → Audit → Research → Opportunity → Change Plan → Draft 保存 artifacts。生产 Draft admission 仍拒绝，前面五类 artifacts 可保留；Live 也允许读取这一失败 run 的 Plan。

现有 `EvidenceIntakeWorkflow` 已提供 register、submit、replan、review_candidate、check；SQLite journal 已有追加式快照、CAS digest、来源/原文/hash/版本和审核记录。原 `ChangePlanWorkflow` 已接受 CustomerPlanningContext，并核对完整原生输入、P/S/A、目标和 EXPLAIN 范围。原 `review` CLI 检查的是已经生成的 Draft，不能代替客户证据审核；`EvidenceSemanticReviewer` 尚无生产实现。

本轮新增主 CLI 的 `evidence open/show/submit/recheck/review` 和 `plan` 的可选 handoff，复用上述机制。没有扩展独立 Crawl → Packet → Audit 入口，也没有新建第二套资料存储或 Planning。

原 run ID 作为 Intake project ID，原 Change Plan artifact ID 作为 Intake task ID。登记时导入原 AnalysisRunInput 的 SEO goal、target language 和完整 Packet/Opportunity/Plan。每次操作重新验证源 History、唯一 artifact 和初始快照；`origin_artifacts` 显示原 Packet/Audit/Opportunity/Plan 的 artifact ID。后续 Plan 版本留在既有 Intake 版本链，原 History artifacts 和原 run 的 FAILED/SUCCEEDED 不被改写。

## 直接运行一次合成演示

在仓库根目录 PowerShell 中运行，无需 API key 或 WordPress。脚本使用本地固定外部 ports，但运行真实 Crawl、提取、Audit、Research/Opportunity/Plan workflow、SQLite 与**生产 Draft 拒绝**，不装配 TEST 批准。

```powershell
$py = '.\.venv\Scripts\python.exe'
$demoRoot = '.data/novacnc-intake-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& $py scripts/demo_seo_evidence.py --output-dir $demoRoot
$meta = Get-Content -Raw -LiteralPath "$demoRoot/demo.json" | ConvertFrom-Json
$common = @('--run-id', $meta.run_id, '--plan-id', $meta.plan_id,
            '--db', "$demoRoot/history.sqlite3", '--intake-db', "$demoRoot/intake.sqlite3")

# 1. 查看缺口。初始 WAITING_FOR_EVIDENCE，具体 F1/F2/F3。
& $py -m foreign_trade_geo_agent evidence show @common --format text

# 2. 查看并提交脚本生成的合成客户文本资料。
Get-Content -LiteralPath "$demoRoot/submission.json"
& $py -m foreign_trade_geo_agent evidence submit @common `
    --customer-id SYNTHETIC-NOVACNC --file "$demoRoot/submission.json"

# 3. 提交持久化后是 RECHECK_REQUIRED，旧 Plan 绑定失效。
$current = (& $py -m foreign_trade_geo_agent evidence show @common) | ConvertFrom-Json
& $py -m foreign_trade_geo_agent evidence recheck @common `
    --expected-sha256 $current.request.snapshot_sha256

# 4. 新 Plan 绑定后查看审核状态与逐义务原文包。
& $py -m foreign_trade_geo_agent evidence show @common
& $py -m foreign_trade_geo_agent evidence review @common
```

最后应得到 `WAITING_FOR_HUMAN_REVIEW`，`submission_status=SUBMITTED`，`evidence_candidate_status=AVAILABLE_FOR_HUMAN_REVIEW`，三个 claim 都为 `UNREVIEWED`，`draft_authorized=false`，`execution_status=AUTHORIZATION_REQUIRED`。这是可供人工查看的证据候选，**不是语义审核通过或正式执行授权**。无需为“等待审核”重复上传。

脚本拒绝覆盖已有 output 目录；重新演示使用新目录。`demo.json` 保留 run/Plan ID；关闭终端后可用它恢复。上面的 `$common` 可重新构造，无需重新跑 Crawl 或重复提交。

部分补充可在第一次提交前只保留 `submission.json` 的第一个 supplement。提交并 recheck 后 F1 为待审核，F2/F3 继续缺失，任务仍 `WAITING_FOR_EVIDENCE`。第二次提交需新的 submission ID、未使用的 evidence ID，以及最新 `request.snapshot_sha256`。更正资料使用 `supersedes`；旧原文不会删除，冲突材料不能靠最后写入自动变成事实。

## 已有 CLI / Live run 导入

已有 run 必须保留完整原生输入、成功的单操作 EXPLAIN Plan；生产 Draft 拒绝的 run 也可以导入。`--plan-id` 是原 change_plan 的 artifact ID，不是 C1。可从主 CLI 的 `artifacts` 获取，或通过现有 `SQLiteHistoryReader.list_artifacts(run_id)` 只读取得 Live run 的 Plan ID。Live 页面本轮没有新增按钮。

```powershell
& $py -m foreign_trade_geo_agent evidence open `
    --run-id '<原 run UUID>' --plan-id '<原 change_plan artifact UUID>' `
    --db .data/history.sqlite3 --intake-db .data/evidence-intake.sqlite3 `
    --customer-id '<本地客户标识>' --requirements '<分析人员编制的 requirements.json>'
```

requirements 文件是 `EvidenceRequirement` 的 JSON 数组，示例见脚本生成的 `requirements.json`。每项必须提供 requirement_id、point_index、required_fact、intended_use、existing_material_insufficiency、allowed_methods；须覆盖所有内容点。当前没有自动语义充分性判断，不能从关键词、引用数或模型输出推断必须补哪些事实。

主 `plan` 支持 `--evidence-requirements <file> --customer-id <id> --intake-db <path>`，在现有 run 完成并保存 Plan 后登记上述任务，输出 `evidence_intake`。这是原有模型流程的配置说明；**本轮没有运行真实模型**。原 Draft 拒绝仍输出 `status=failed`、`INTAKE_EXECUTION_BLOCKED`、退出码 1，同时可有 `evidence_intake.state=WAITING_FOR_EVIDENCE`，不能把 handoff 当作 Draft 成功。hand-off 失败退出 2，源 artifacts 保留，可修正义务后 `evidence open` 恢复。

没有传补证义务时，原流程不强制登记 Intake，也不要求上传。既有充分证据的任务不会因为新增 CLI 被强制重复上传；证据充分仍不能获得生产 Draft 权限。

## 三种状态与恢复

| 业务事实 | 实际字段/行为 | 不代表什么 |
| --- | --- | --- |
| 缺客户资料 | WAITING_FOR_EVIDENCE；具体逐义务 gaps | 不能进入 Draft |
| 客户资料已提交 | SUBMITTED；Plan unbound；RECHECK_REQUIRED | 尚未核对新 Plan、更未证明事实 |
| 证据候选可供人审 | 原生重新核对后 AVAILABLE_FOR_HUMAN_REVIEW；claim=UNREVIEWED | 不代表 Intake 的语义 SUPPORTED/CANDIDATE_FOR_REVIEW |
| 正式授权执行 | 本入口始终 draft_authorized=false / AUTHORIZATION_REQUIRED | 本轮没有任何批准或执行命令 |

等待状态由已持久化的 task/Plan/evidence/revision/check 重建，是可恢复业务状态；没有增加或伪改原 History RunStatus。两个本地 DB 和原 run 必须一并保留。

`submit` 和 `recheck` 是两个明确步骤。提交先持久化并使旧绑定失效；如果终端中断或原生核对失败，`show` 可发现 `RECHECK_REQUIRED`。用当前 digest 重试 `recheck`；重复核对已绑定快照不会增加版本。陈旧 digest、重复 submission ID、非法 JSON、伪造 actor/time/review 字段均拒绝。

`recheck` 使用 `RetainedIntakePlanWriter` 为原生候选选择器保留原任务，通过**同一个 ChangePlanWorkflow + CustomerPlanningContext + EvidenceIntakeWorkflow.replan** 校验和重绑定。它不调用模型，不改变策略，不自动把客户事实写进 P/S，也不判断证据含义。若原生候选或预算不满足要求，会拒绝，保留可恢复的未绑定状态。每次新资料得到新的证据版本、Plan 版本和 snapshot SHA256；旧审核只留在历史，不能自动跟随。

`show`/`review` 复用 Intake check，向 append-only journal 追加当前检查记录；不会写回原 Plan/History，也不是审核批准接口。本地 actor 固定为 LOCAL-OPERATOR，customer ID 是操作者声明，**不是客户登录认证**。没有从客户 JSON 信任 reviewer，也没有生产语义签核适配器。原文来源 locator 和归属仍是声明，hash 只证明文本一致性。

## 实际验收与剩余 MVP 阻断

实际合成运行产物见 [验收目录](seo-planning-evidence-acceptance-2026-10-10/01-waiting.json)：初始缺口、提交后状态、重新核对后状态、逐项审核包。演示记录版本为 revision 1 → 2 → 3，Plan 1 → 2，evidence 1 → 2；Draft writer=0。原主 run 保持真实的 Draft 拒绝结果。

自动测试覆盖完整/部分补证、精确来源和版本、恢复、重放/陈旧 digest、客户伪造权限、原 run/Plan 错绑、义务缺失、旧审核保留但不沿用，以及不充分/冲突/无关/过期/未经审核资料均在实际 Draft writer 前拒绝。显式合成人工 SUPPORTED 也只产生候选，无执行权限。

本轮实际执行结果：

| 验证 | 结果 |
| --- | --- |
| 新 `tests.test_planning_evidence_cli -v` | 11 tests / 4.474s / OK |
| 最终 `tests.test_planning_evidence_cli tests.test_runtime tests.test_cli -q` | 53 tests / 10.159s / OK |
| 完整 `unittest discover -s tests -p "test_*.py" -v` | **1599 tests / 268.183s / OK / exit 0** |
| 实际 CLI submit → show → recheck → review | 全部 exit 0；三阶段状态与审核包已导出 |
| 实际 CLI 重放旧 submission | exit 2，正确拒绝 |
| `git diff --check`；本轮新增文件尾空白检查 | exit 0；无尾空白 |

完整命令（仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_planning_evidence_cli -v
.\.venv\Scripts\python.exe -m unittest tests.test_planning_evidence_cli tests.test_runtime tests.test_cli -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

迭代测试另运行了 `tests.test_cli tests.test_evidence_intake tests.test_intake_native_planning -q`，73 tests / 11.767s / OK；不与最终组合重复累计。上述测试没有失败。完整日志留在本地 ignored `.data/seo-evidence-demo-20261010/full-suite.log`；机读摘要见 [demo-verification.json](seo-planning-evidence-acceptance-2026-10-10/demo-verification.json)。日志末尾 Demo/port 文字来自既有模拟测试，runner 结论为 OK；没有启动真实服务或进行部署。

本轮修改：`cli.py`、`runtime.py`、`storage/evidence_intake.py`；新增 `evidence_cli.py`、`workflows/planning_evidence.py`、`adapters/retained_intake_plan.py`、演示脚本和聚焦测试。没有改 core schema、HistoryStore schema、独立 Audit、Draft gate、P1 或 WordPress。

仍需后续单独解决：

1. 当前 Intake 仅支持**单个 EXPAND_SECTION、全部 EXPLAIN**；多任务、多操作、CREATE_NEW_RESOURCE 整篇文章、早于成功 Plan 的缺证导入暂不支持，安全拒绝。
2. 分析人员仍需明确编制事实义务及材料不足原因；不提供自动工程充分性判断。只支持现有 UTF-8 文本/事实声明，不支持 PDF/DOCX/OCR。
3. 生产客户身份、来源权威性与真实性、可信当前人工语义签核尚未接通；本地 CLI 只能提交和查看待审包。
4. 真实模型根据资料重新制定策略、完整商业文章的内容质量验收和正式 Draft 授权尚未成立。本地保留 Plan 核对不能替代这些验收，也不授予旧历史 Draft 新的执行权。
5. **P1 全局一次性消费历史失败仍未解决；PostgreSQL BLOCKED 保持。** 本轮不修改、不以 SQLite 或 TEST 批准替代其生产验收。生产、WordPress、部署继续 NO-GO。

没有真实模型、真实网站抓取、WordPress 写入、部署、提交、推送或合并。
