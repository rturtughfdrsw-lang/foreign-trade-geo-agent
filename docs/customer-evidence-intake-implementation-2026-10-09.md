# 客户补充资料最小闭环（2026-10-09）

本轮建立可运行的本地 Evidence Intake：具体事实缺口 → 客户请求 → 受控补充/明确范围调整 → 版本记录 → 原生 Planning 重验 → 当前证据人工语义判断 → 后续审核候选。没有 Draft 执行能力。全部验证使用独立虚构包装出口客户，未操作真实客户、真实签核、LLM、网站、WordPress 或 Windows 安全配置。

## A. 现有 Evidence Intake 能力与真实缺口

阅读了 AGENTS.md、P-only Draft 实施报告，以及 `core/evidence_sufficiency.py`、`core/first_party_planning.py`、`core/change_plan.py`、`core/content_draft.py`、对应 workflows、历史 codec/SQLite、receipt store 和相关测试。开始工作前检查 Git 并记录 379 个已有文件的 SHA256。

| 能力 | 审计结论 |
| --- | --- |
| 通用客户 Evidence Intake | 本轮之前没有任务事实义务、客户提交、缺口请求和补充版本重验的可运行模块。现有 first-party scope 是受限原文展示规划上下文，不是 Intake。 |
| 现有 Evidence Sufficiency Gate | `EvidenceSufficiencyPreflight` / persisted preflight 是 P-only profile；它们拒绝 EXPLAIN，并要求当前可信审核与精确冻结绑定。不能扩大解释为通用工程语义充分性 Gate。 |
| 普通 Planning / Draft | 有 P/S/A 来源、主题、引用、操作、数字、类型及结构检查。普通 Draft 的 stable validation 不查询通用客户语义审核；主题 grounding 不证明因果解释、参数适用性或证书真实有效。 |
| 客户补充资料请求 | 之前没有通用请求对象；本轮从人工明确列出的缺失事实义务及其 Plan 内容点生成，不自动猜测工程事实。 |
| 版本与旧审批 | 现有 excerpt receipt/registration 有特定 task/Plan/evidence 版本绑定；HistoryStore 的 append-only artifact 不是通用客户任务修订流或审核身份源。 |
| 最小剩余真实业务组件 | 客户身份/提交接入、可靠的当前人工语义审核适配器、客户资料到既有 P/S 消费输入的显式受审映射、独立 Draft 授权。不能以新 journal 或 candidate flag 替代它们。 |

没有重建 Planning、Draft 或签核系统；新增层复用既有原生验证函数，收集独立的客户资料并停止在审核候选。

## B. 客户补充资料的业务契约

V1 输入限制为 **一个既有、结构合法的 `EXPAND_SECTION` Plan，全部内容点为 EXPLAIN**。最大五个内容点、32 项事实义务、100 条累计证据、20 条单次补充、100 次客户提交、1000 个修订、单条文本 16000 字符、整个快照 1500000 UTF-8 bytes。超限拒绝，错误不携带原始异常。这是新登记 Intake 任务的独立版本线，初始 task/Plan/evidence 均为 1；没有导入旧 registration 的版本历史。更早阶段尚无合法 Plan 的任务，以及其他 operation 类型，本轮不支持。

- `EvidenceTask` / `EvidenceRequirement`：project/customer/task、任务版本和目标；每项所需事实、用途、现有材料不足原因、Plan point_index 和允许补充方式。每个 EXPLAIN 内容点都必须有事实义务。义务需要分析人员明确编制；这项结构覆盖检查不能证明人工列出的义务已穷尽整个工程问题。
- `CustomerEvidenceRequest` / `EvidenceGap`：绑定当前 task/Plan/evidence/revision/digest，包含 C1、内容点、事实义务、剩余缺口和审核说明；可输出 JSON 或直接交给客户阅读的文本；已提交但待人工判断时明确提示无需重复提交。缺口为空时不请求额外客户资料，工作人员仍可能需要重新绑定 Plan。
- `CustomerSubmission` / `Supplement`：submission ID、当前 expected digest、明确的 requirement IDs、事实文本或文本材料、来源名称、具体 locator、声明归属；可显式 supersede 某个已有材料，保留原记录。未知义务、跨客户、重复 ID、旧 digest、禁止的补充方式均拒绝。
- `text_document(...)`：接受有界、严格 UTF-8 bytes，保存原文和原 bytes SHA256，不读取客户路径、不抓取 URL、不解析二进制。PDF、DOCX、图片/OCR 接入不在 V1 中；本轮没有声称已有这些解析能力。
- `CustomerContext`：customer/actor/time 来自集成应用的已认证边界，不能从客户提交 JSON 取得。**本轮没有实现客户登录或验证此上下文所声明身份的生产服务。** 来源归属是客户声明，真实权威性仍要审核。
- `ScopeAdjustment` / `ScopeConsent`：明确的新目标、保留义务、原因、同意值、提交者/时间及原快照 digest。没有明确同意就拒绝；只能删除整组内容点，不能保留同一 EXPLAIN 承诺却静默删减其中某个事实义务，也不能改成 DESCRIBE/P-only。可以明确保留后面的内容点，索引会重新绑定。
- `EvidenceSemanticReviewer`：由可信装配注入、每次取得当前人工语义决策的 port。审核职责包含证据权威性、产品/工况适用性、解释深度、限制和全部活动材料/P/S 上下文中的矛盾。协议要求适配器验证当前 reviewer 身份/权限/撤销；**本轮没有生产适配器，也不把客户 JSON 或 LLM 的 supported flag 当作它。**

不存在自动编造认证、参数或能力的路径。材料中的主题词、材料数量、引用数量、客户自称“全部充分”，均不能使状态变为候选。

## C. 实际代码修改与兼容性

只新增以下五个模块和一个测试文件；已有文件内容均保留。

| 新文件 | 行为 |
| --- | --- |
| `core/evidence_intake.py` | 有界任务、事实义务、客户提交/同意、证据记录、快照、请求、人工语义决策与 ports；调用已有 stable validation 和 Planning finalizer，验证当前 digest、全义务覆盖、精确 spans。 |
| `workflows/evidence_intake.py` | `register`、`customer_request`、`submit`、`rebind_plan`、`check`；默认拒绝，没有 writer/fetcher/CMS；并发修改时不交付旧候选。 |
| `adapters/customer_evidence.py` | 保留字节的有界 UTF-8 文档输入。 |
| `storage/evidence_intake.py` | 独立 V1 SQLite Intake journal；复用 storage 内部严格 dataclass codec；快照/检查记录 append-only、compare-and-append、精确 schema 检查、事务、超时/VM/长度限制、版本关系校验。 |
| `reporting/evidence_intake.py` | 客户请求 JSON/中文说明文本；不发送消息。 |
| `tests/test_evidence_intake.py` | 独立虚构包装客户的业务和边界验收。 |

没有新增依赖，也没有修改原 HistoryStore schema/migrations、artifact codec 根列表、Plan/Draft 公共调用签名、runtime/CLI/Web、P-only profile、签核 receipts/host、真实审核包或 WordPress 行为。Journal 是专用收集记录，不能当作证据授权服务或第二套 Planning。

调用者在本地 composition 边界装配 `SQLiteEvidenceIntakeStore` 和 `EvidenceIntakeWorkflow`；本轮没有新增 Web/CLI 路由。最小使用顺序是：

```python
store = SQLiteEvidenceIntakeStore.create(local_new_database_path)
flow = EvidenceIntakeWorkflow(store)  # 默认没有语义审核来源
snapshot = flow.register(analyst_authored_task, existing_content_draft_input)
request = flow.customer_request(project_id, task_id, now=aware_now)
# 将请求交给客户；此代码不会自动发送。
snapshot = flow.submit(project_id, task_id, submission,
                       customer=application_authenticated_customer_context)
snapshot = flow.rebind_plan(project_id, task_id,
                           expected_sha256=snapshot_digest(snapshot),
                           planning_input=structurally_revalidated_input)
result = flow.check(project_id, task_id, now=aware_now)
```

没有 reviewer 时最后仍 BLOCKED。只有可信人工审核 port 对当前完整对象作出有效的全义务支持判断，才可能得到 `CANDIDATE_FOR_REVIEW`；该对象不是 `ContentDraftInput`，也不是 Draft 授权凭据。

## D. 完整正负例测试

虚构客户要求解释包装载荷、密封材料适用性和认证范围。初始 P1/S1 只列主题，故结构上可规划但缺少客户产品事实。这刻意检验“合法 Plan 不等于足够工程证据”。所有例子与真实 O1–O6 无关。

| 场景 | 实际行为 |
| --- | --- |
| 初始不足 | BLOCKED；精确请求载荷单位/型号/工况/测试限制、密封材料/流体/温度/测试方式、证号/机构/标准/型号范围/有效期。 |
| 只补 F1 | 旧 Plan binding 失效；重新绑定且 synthetic 人工确认 F1 后，请求只剩 F2/F3。 |
| 三项完整补充 | 没重绑时 `PLAN_REBIND_REQUIRED`；已重绑但没有人工判断时仍 BLOCKED；当前完整 synthetic 人工判断后才候选。 |
| 无关材料 | 即使包含所有主题词，明确人工 IRRELEVANT 后仍阻塞并保留具体原因。 |
| 矛盾材料 | 12 kg / 30 kg 两版全部保留；CONFLICT 阻塞；明确 correction + 新绑定 + 人工重新确认后才能候选。不能采用最后一条材料自动赢过原材料。 |
| 范围同意 | 未同意拒绝；明确同意删除整组后 task version 增加、同意链保留、新 Plan 必须恰好保留授权内容点，后面的点可重新编号。 |
| 静默缩水/P-only | 直接重绑一个删点 Plan，或把 EXPLAIN 改成 DESCRIBE 均拒绝；同一内容点内偷偷删掉事实义务也拒绝。 |
| 旧版本复用 | 旧 submission、旧 Plan expected digest、旧 candidate/assessment、旧 check 追加全部失败。每次 check 都重新调用 reviewer，不读旧绿色记录。 |
| 并发变化 | 人工判断期间收到新材料，最终 compare-and-append 失败，不返回/保存候选结果。 |
| 错绑定/伪造输入 | 跨客户、未知事实、重复证据/提交、未知 JSON 字段、duplicate keys、approved 参数、错误类型/超限/上传 digest/禁止方式、缺义务、错 span/quote/来源/时间/摘要均拒绝。 |
| 存储与保留 | 旧快照、来源、归属声明、actor/time、提交/证据版本可重读；UPDATE/DELETE、直接历史改写、schema 变更、覆盖已有 DB 均拒绝。 |
| 候选但无 Draft 授权 | `draft_authorized` 始终 False；把 IntakeCheck 交给原 ContentDraftWorkflow 得 INVALID_INPUT、writer=0。 |

这是收集、绑定和受信人工决定的验收；不是一个可靠自动工程判定器的验收。Synthetic reviewer 明确脚本化人工 fixture 决策，没有关键词评分或真实签核。

客户能看到的可复核样例在 [synthetic 请求目录](customer-evidence-intake-synthetic-2026-10-09/README.md)：初始三项请求 → 一项客户提交 → 剩余两项请求，提供 JSON 与可读文本。

## E. 新旧证据、Plan 和授权版本一致性

```text
初始：task=1, Plan=1, evidence=1, revision=1, bound
补充：task=1, Plan=1, evidence=2, revision=2, unbound
重验：task=1, Plan=2, evidence=2, revision=3, bound
检查：仅当前完整人工判断可得审核候选；无 Draft 权限
```

scope 调整另增 task version；只有材料补充才增加 evidence version；每次重新绑定增加 Plan version；每次状态追加增加 revision。即使 Plan 的操作文字无需改变，也必须重新通过既有原生校验并获得新的当前绑定，不能继承旧充分性。

快照 SHA256 覆盖完整 task/目标/义务、三版本、全部原生 P/S/Plan/语言、证据原文及来源元数据、submission IDs 和同意链。人工判断绑定这个 digest，逐义务、逐原文 span 验证；时间必须为当前时刻前五分钟内。身份/授权实时有效性由可信 reviewer port 负责；数据库、digest、客户声明及 reviewer ID 字符串本身均不证明身份或语义。

Receipt / AuthenticatedReview / P-only GREEN 均不是新 API 的 SemanticAssessment。没有消费旧审批的接口，也没有把新候选转成旧 Draft receipt 的接口。`checks()` 是历史检查记录，不能当作当前执行权限；当前状态只能经 workflow 重查。

这项失效规则覆盖**新 Intake 链路**。本轮没有为所有旧 `ContentDraftInput` 增加全局修订登记或改变普通 Draft 的历史调用行为；直接绕开 Intake 调用旧 Draft 不属于新闭环认可的客户工作流。生产整合必须保留明确的人审和正式执行准入，不能宣称本轮已经全局撤销一切旧输入。

## F. 针对性测试与完整回归

新增模块最终单独运行：**22 tests / 2.999s / OK / exit 0**。

针对性组合：**324 tests / 13.790s / OK / exit 0**。覆盖 Intake、原充分性 preflight、first-party Planning、material availability、Planning core/workflow、普通 Draft core/workflow、P-only consumption、历史 serializer/SQLite。完整回归：**1528 tests / 231.925s / OK / exit 0**，helper wall 232.979s；最终六个源码/测试文件的 SHA256 在各轮验证前后均相同。命令和日志摘要见同名 verification JSON。

实际命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_evidence_intake -v
.\.venv\Scripts\python.exe -m unittest tests.test_evidence_intake tests.test_evidence_sufficiency_preflight tests.test_first_party_planning tests.test_change_plan_material_availability tests.test_change_plan_core tests.test_change_plan_workflow tests.test_content_draft_core tests.test_content_draft_workflow tests.test_p_only_draft_consumption tests.test_history_serialization tests.test_sqlite_history_store -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

迭代中失败如实保留：首次 18 项均因新 fixture 漏传 SiteContentEvidence 参数而 ERROR；修复 fixture 后，18 项运行出现 1 failure / 4 errors，分别发现越界 span 切片问题和测试 SQLite 连接未关闭/失败事务仍持锁的 Windows 清理问题。新增显式 end 长度检查，测试改用 closing 并回滚失败事务；未放松断言或安全规则。随后 18 项通过，再补请求输出、版本 digest、受控输入及范围索引验收，最终 22 项通过。最终复核还补全了虚构证书标准与密封测试方法/温度范围，并将“已提交、待人工审核”提示明确为无需重复提交；对冻结后的最终源码重新运行了单模块、324 项组合和完整回归。

`git diff --check` exit 0；Git 仅提示既有 LF/CRLF。新增文件另以 `git diff --no-index --check -- NUL <file>` 单独检查；首次发现两个新文件的 EOF 多余空行，修正后全部通过。起始 379 个已有文件的内容没有变化；起始已删除的 migration 测试和所有既有 dirty/untracked 文件状态保留。原始测试日志和 baseline 在 ignored `.data/customer-evidence-intake-20261009/`。没有运行 live/integration verification。

## G. TEST、真实客户工作流与商业 Draft

| 范围 | 结论 |
| --- | --- |
| 独立 synthetic、本地资料闭环 | **GO**：可执行、可持久化、输出客户请求；材料齐全 + 当前明确的 synthetic 人工判断后可进入审核候选。 |
| 本地人工协作收集资料 | **GO（有界收集能力）**：分析人员编制事实义务，客户提交资料或明确调整范围；没有生产审核适配器时保持 BLOCKED。 |
| 真实客户完整端到端工作流 | **NO-GO**：尚未装配已认证客户接入、当前真实人工语义决定源、资料进入原消费输入的受审映射及正式 Draft 执行准入。Web UI 本身不是本轮必需项。 |
| 商业/正式 Draft、真实 O1–O6、WordPress | **NO-GO**：本轮没有授予任何权限；真实既有审核包未改，仍未审核。 |

安全检查点建议：本轮新增源码/测试、样例和验证文档可以作为独立审查检查点，与既有历史修改分开核对。本轮未 commit、push、merge、reset、clean 或修改 Git 历史。
