# 客户证据与原生 SEO Planning 集成（2026-10-09）

本轮实现可运行的安全子链路：已有原生 EXPLAIN Plan → 具体事实义务/缺口 → 客户补充 → 原生 Change Planning 消费独立客户上下文 → 新快照绑定 → 逐 claim 人工语义审核材料。没有第二套 Planning、语义充分性算法、生产签核或客户证据 Draft 授权。测试使用独立虚构出口阀门企业 LumenSeal/V7；没有复用 NovaCNC 的历史审批。

## A. 实际端到端数据流与阻塞

阅读了 AGENTS.md、上一轮 Intake 实施报告，以及 crawl/packet/audit、opportunity、change plan、Intake、Sufficiency、普通/P-only Draft、持久化和对应测试。开始工作时记录 394 个已有路径的内容 hash；保留全部既有 dirty/untracked 改动和已删除文件。

| 环节 | 实际实现、artifact 和本轮连接方式 |
| --- | --- |
| Site Crawl | `SiteCrawlWorkflow` 的有界同源抓取与提取形成 `SiteCrawlReport`；`SiteContentPacketBuilder` 生成原生 `SITE_CONTENT`。现有 EndToEnd 保留 Crawl 在结果中，未单独追加 Crawl artifact。 |
| SEO Audit | `CrawlSeoAuditor.audit_crawl` 消费已抓取内容；`SITE_AUDIT` 保存确定性审计。适用 Audit 材料进入 Opportunity 的 `audit_evidence`/A 上下文。 |
| Industry Research | 原生 `IndustryResearchWorkflow` 生成 `INDUSTRY_RESEARCH`；来源被标注为未验证研究上下文。不是客户产品事实。 |
| Content Opportunity | 原生 `ContentOpportunityWorkflow` 生成 `CONTENT_OPPORTUNITY`，包含 P 页面展示、S 来源/精确保留材料和 A 审计上下文。 |
| Change Planning | 原生 `ChangePlanWorkflow` 生成 `CHANGE_PLAN`。原 `ContentDraftInput` 只有 site、Opportunity、Plan、语言四字段，没有客户任务身份或修订登记。合法 EXPLAIN Plan 不证明解释所需事实充分。 |
| Evidence Gap → Customer Intake | 复用已有 `EvidenceTask`、逐点 `EvidenceRequirement`、`CustomerEvidenceRequest`、`CustomerSubmission` 和 V1 journal。事实义务需要分析人员明确编制，每个 EXPLAIN 内容点均必须覆盖。 |
| Evidence Rebinding → Replanning | 新 `replan` 冻结当前 digest，把全部客户材料映射成原生 `ChangePlanInput.customer_context`，调用同一个 `ChangePlanWorkflow`，再用原生验证和任务保留检查绑定新 Plan。 |
| Human Review Candidate | `PlanningReviewCandidate` 给出当前原生 Plan、完整证据快照、逐义务原文材料及显式人工 verdict。材料待审与客户仍需补充可区分；无 Draft 权限。 |
| Draft 实际入口 | 普通 `ContentDraftWorkflow.run` 可装配 `ContentDraftAdmission`；runtime 暴露该注入入口。`EvidenceIntakeDraftAdmission` 查询当前任务快照、digest、Plan binding 和输入一致性，最终仍拒绝客户证据 Draft。配置 Intake 的实例也拒绝从 P-only 入口绕过。 |

本轮前的断点是：Intake 材料仅存 journal；`rebind_plan` 由调用方另传 DraftInput，未交给原生 Planner；普通 Draft 不读取 Intake。已有通用重新规划引擎并不存在，但已有原生 Change Planning 可复用，故只新增其可选上下文和 Intake 的调用方法。

本轮不重新生成 Opportunity：客户资料没有被转换为 P/S，原页面/研究/审计未改变，原 Opportunity 的同一主题及动作重新通过原生上游校验。它被完整冻结到新快照，Plan 在该上下文上重新生成。原网站或研究更新、多任务/多操作重规划、尚未形成合法 Plan 的早期缺口仍不在此有界入口内。

生产阻塞仍包括客户登录/提交身份接入、可靠的当前人工语义审核适配器、正式客户证据 Draft purpose，以及生产路由对任务边界的强制装配。既有 EndToEnd 默认仍走其历史 Planning→Draft 路径；没有自动识别所有客户任务或全局改写旧行为。

## B. 客户补充证据到原生 Planning 的映射契约

| 原始材料 | 新原生输入位置 | 允许含义 |
| --- | --- | --- |
| 原网站证据 | 原 `site_content.pages`/P catalog | 抓取到的网站内容，不因客户补充而替换或提高验证等级。 |
| 原研究及 Audit | 原 Opportunity 的 S/A catalog | 保留原分类、原文、截断状态及审计 provenance。 |
| 客户陈述 | `customer_evidence_intake.records[].supplement.method=CUSTOMER_FACT` | 有归属的未验证陈述，仅供规划与人工核验。 |
| 客户文本文件 | 同一独立 context 中的 `TEXT_DOCUMENT` | 严格 UTF-8 原文、原 bytes SHA256、声明的来源/locator，仅供规划与人工核验。 |
| 任务内容义务 | context 的 goal、required_point_subjects、EXPLAIN intent、requirements | 当前全部事实需求及用途，不允许 Planner 静默删点或改为 DESCRIBE/P-only。 |

`CustomerPlanningContext` 是原 `IntakeSnapshot` 的确定性投影。输出 project/customer/task、task/Plan/evidence/revision、输入 snapshot digest；全部记录保留 evidence ID、requirement IDs、完整原文、来源名称、声明 locator/归属、file hash、supersedes、submission ID、提交者、时间和材料版本，并标记 active。历史/矛盾/被替代材料不会被悄悄丢掉。独立引用展示为 `customer:<evidence_id>`，不能成为原生 page_refs/source_refs/subject_ref 的合法 grounding origin。

**没有生成网站 URL、P 页面、S 外部来源或 PDF 页码。** locator 是提交者声明的具体位置，真实性仍要人审；本轮只支持已有 UTF-8 文本适配器，不实现 PDF/DOCX/OCR。无法提供可靠 locator 的材料不能被映射成可验证 P/S 引用。原文、归属声明、关键词或文件数量均不能证明内容是真实、适用或语义充分。

输入必须匹配原 SiteContentPacket、完整 Opportunity report 和 task_id，不与 FirstPartyPlanningScope 混用。全量 context 计入原生已有字符、bytes 和请求 envelope 上限；超限在 writer 前拒绝，没有截断客户义务或扩大预算。DeepSeek adapter 的新边界提示明确客户资料为不可信数据；本轮仅通过 MockTransport 验证 HTTP 请求内容，没有调用付费模型。

## C. 具体修改及兼容性

| 修改文件 | 行为 |
| --- | --- |
| `core/evidence_intake.py` | 增加客户规划投影、原生重规划 port、任务保留校验、逐 claim 审核条目和审核候选。复用既有模型、原生 stable validation/finalizer；新增对象不授权执行。 |
| `core/change_plan.py` | `ChangePlanInput` 增加默认 None 的独立 customer_context；原生 material 和输入校验显式消费它。未配置时原 JSON 不新增字段。 |
| `workflows/change_plan.py` | 原 `run` 可选接收 context；生成结果再次检查完整保留 EXPLAIN 内容点、目标和 P/S/A 绑定。即使直接调用原生 Planner，也拒绝未经同意的缩水/目标迁移。 |
| `workflows/evidence_intake.py` | 新 `replan` 和 `review_candidate`；旧 `rebind_plan` 保留签名并收紧新重绑定的任务/原生证据保留检查。增加查询当前快照的 Draft admission。 |
| `storage/evidence_intake.py` | 新 append 的 Plan 重绑定必须保留原生证据与目标；读取旧 V1 历史仍使用原版本规则，不改写旧行。 |
| `reporting/evidence_intake.py` | 增加完整本地人审 JSON：原生 P/S/A、材料历史、逐义务原文及 verdict、待办与明确无 Draft 权限。 |
| `adapters/deepseek_change_plan.py` | 在原预算内增加客户上下文不可信/EXPLAIN 范围保护提示。 |
| `core/ports.py`、`core/content_draft.py` | 新执行准入 port 和有界 `INTAKE_EXECUTION_BLOCKED` 类别。 |
| `workflows/content_draft.py` | 装配准入时先查询当前边界，writer 前拒绝旧/无绑定输入；异常统一拒绝，原始异常及任意 adapter reason 不持久化。配置 Intake 时 P-only 不能绕过。 |
| `runtime.py` | 原 composition root 暴露可选 `intake_admission`，交给同一个 DraftWorkflow。 |
| `tests/test_intake_native_planning.py` | 独立 LumenSeal synthetic 场景、真实原生 workflow/验证器和局部外部边界 fixtures。 |

没有新源码模块、依赖、DB schema/migration、History artifact 根类型或第二套 Planning。IntakeSnapshot 和 ContentDraftInput 字段未改变，因此既有序列化与 digest 未改变。保留普通 P/S、P-only receipt purpose、comparison 准入、WordPress create-only/draft-only；默认未装配 Intake 的调用方行为不变。

`rebind_plan` 的新写入不再允许替换 site、Opportunity、语言、操作类型、source action、P/S/A refs 或 locator；合法显式整点范围同意仍可重新绑定，旧记录可读。它仍是兼容的手工结构重绑定接口，不能证明调用方曾执行客户 context 的重规划；本轮可验证的自动集成路径是 `replan(..., planner=ChangePlanWorkflow(...))`。

## D. 端到端正负例结果

新测试使用本地 fake fetcher/extractor/search/provider 和明确脚本化的 synthetic HUMAN verdict；Crawl、Packet、Audit、Research、Opportunity、Change Planning、Intake、SQLite、真实 Draft 入口均使用现有实现。没有替换原生 Planning 验证路径。另有标准 runtime 的全链路测试，原生 artifacts 进入 HistoryStore，最后停止在 Draft guard，writer=0。

| 场景 | 实际结果 |
| --- | --- |
| 原始 EXPLAIN 三项事实需求 | 流量的型号/单位/工况/方法、密封材料的介质/温度/限制、证书的机构/标准/型号范围/有效期。初始三项缺口，Draft 拒绝。 |
| 第一次只补流量资料 | 原生 Planner 接收 E1 的归属/原文；新绑定后明确 synthetic 人工支持 F1，F2/F3 继续请求客户补充。 |
| 第二次补密封陈述及证书文本 | 新 evidence=3、Plan=3、revision=5；保留三点 EXPLAIN 和原 P/S/A。三项均 UNREVIEWED，staff_action 为 HUMAN_SEMANTIC_REVIEW_REQUIRED，Draft writer=0。 |
| 当前 synthetic 人工明确逐义务支持 | 可得到原 Intake 的 CANDIDATE_FOR_REVIEW；仍没有客户证据 Draft permission。 |
| 无关文件含全部主题词 | 人工明确 IRRELEVANT 后保留该缺口；不靠关键词或数量通过。 |
| 矛盾事实 | 两条材料均保留，明确 CONFLICT 阻塞，不能最后写入自动覆盖。 |
| 不确定/缺失 | 有材料但 UNREVIEWED 等待人审；无材料为 MISSING。审核包逐项显示状态和原文。 |
| 伪造引用/quote/locator | 客户 E 不能成为原生 P/S subject_ref；改写已冻结 provider material 的 locator 被拒绝；伪造人审 span/quote 不被采纳。 |
| 重放/并发 | 旧 digest 在 Planner 前拒绝；旧 check/assessment 不能跟随新版本。Planner 期间并发提交使 CAS 失败，拒绝旧输出。 |
| 未同意缩水/改深度/迁移目标 | 删点、EXPLAIN→DESCRIBE、换 locator、P/S/A/语言替换均拒绝，直接 storage append 也无法替换原生绑定。明确整点同意仍可用。 |
| 旧 DraftInput 绕过 Intake | 已装配入口查询当前 digest；旧绑定 STALE、无绑定拒绝。拿新 digest 包装旧等值输入也仍不获 Draft permission。配置 Intake 的 P-only 入口拒绝旧 purpose。 |
| 状态不可用/超限/未知 context | fail-closed，writer=0；不导出原始异常、静默截断或绕过校验。 |
| 历史兼容 | 原生 SITE_CONTENT、SITE_AUDIT、Opportunity、Plan codec roundtrip；Intake 旧快照可重读，普通/P-only/comparison 既有测试保留。 |

可复核样例见 [synthetic 目录](intake-native-planning-synthetic-2026-10-09/README.md)：初始请求、剩余两项请求、精确原生 Planner material、待审候选及五次状态 digest。样例生成使用与新测试相同的真实工作流，不代表生产身份或语义签核。

## E. 版本失效、来源追溯和人工语义审核边界

```text
revision=1：task=1 / Plan=1 / evidence=1，初始绑定，三项事实缺口
revision=2：task=1 / Plan=1 / evidence=2，第一次客户提交，Plan unbound
revision=3：task=1 / Plan=2 / evidence=2，原生重规划、全范围重验、绑定
revision=4：task=1 / Plan=2 / evidence=3，第二次客户提交，Plan unbound
revision=5：task=1 / Plan=3 / evidence=3，原生重规划、绑定，全部材料等待人审
```

Plan 文案可能不变，但每次重绑定仍增 Plan version、追加快照并改变 digest。任务目标/义务/主体、全部原生输入、客户原文及元数据都参与 snapshot SHA256。Planning context 绑定其输入（revision 2/4）digest；review candidate/check 则绑定生成后的 revision 3/5 digest。旧充分性记录不会继承，新 check 重新调用可信 reviewer，并验证当前 digest、全部义务及精确 spans；未装配 reviewer 默认 BLOCKED。

人审包的 claim 是分析人员明确编制的事实义务，不是已生成商业文案的每句话。人工须检查原文、权威性、产品/工况适用性、因果解释深度、范围和跨全部材料的矛盾。材料存在只能触发待审路由；JSON 合法、主题 grounding、引用数量和结构覆盖都不证明 EXPLAIN 语义充分。义务是否穷尽原工程问题也仍需要分析人员/人工确认。

追溯精度是 Intake 的当前版本链、完整原生输入副本、来源声明/locator、提交者/时间、文档 hash、人工 spans 及快照 digest。此 V1 journal **不新增原 History run/artifact ID 外键，也不能由 DraftInput 反推原 run 的 SEO goal**；集成应用须在登记时明确导入正确的任务目标和义务。来源身份、locator 真实性及材料权威性不由 hash、actor 字符串或客户声明证明。

失效覆盖新 Intake 版本链、原生重规划候选，以及显式装配的 Draft 实例。它不是全局撤销：没有任务 ID 的历史 DraftInput、未配置 guard 的旧 runtime/CLI/Web 调用方仍按旧契约执行。由于旧 Input 可与新 Plan 内容完全相同，单靠对象内容不能恢复证据 epoch；本轮入口必须依赖应用绑定的 task/digest，且始终拒绝客户证据 Draft。没有新生产 route、授权 purpose 或允许执行分支；不能据此宣称真实客户全流程可上线。

## F. 本轮测试与完整回归

上一轮 **1528 tests OK** 仅作为已有记录。本轮最终冻结源码的针对性组合：**502 tests / 23.075s / OK / exit 0**。

本轮完整回归：**1546 tests / 235.922s / OK / exit 0**，shell wall 236.999s。新增 18 项业务/边界测试全部通过；源码在最终针对性测试、完整回归和样例生成期间冻结，完整回归后 hash 一致。原始日志位于 ignored `.data/intake-planning-20261009/`；[验证摘要](intake-native-planning-verification-2026-10-09.json) 记录命令、成绩、迭代失败和源码 hash。

实际针对性命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_intake_native_planning tests.test_evidence_intake tests.test_evidence_sufficiency_preflight tests.test_first_party_planning tests.test_change_plan_material_availability tests.test_change_plan_core tests.test_change_plan_workflow tests.test_content_opportunity_workflow tests.test_content_draft_core tests.test_content_draft_workflow tests.test_p_only_draft_consumption tests.test_comparison_admission tests.test_deepseek_change_plan_adapter tests.test_history_serialization tests.test_sqlite_history_store tests.test_end_to_end_workflow tests.test_runtime tests.test_crawl_seo_audit -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

迭代失败如实记录：新 12 项测试首次 1 ERROR，fixture 将已有 `text_document(payload=...)` 错写成 content，修正后 12 项通过；60 项组合首次 1 failure，新增 system 提示使既有 7892 字符基础提示超出 8000 上限，Mock 请求未发出。缩短新提示至原预算内，并为 mock 响应补上现有协议要求的 finish_reason=stop 后，60 项组合通过。未扩大上限、弱化安全断言或运行 live/integration verification。

`git diff --check` exit 0；新测试/文档另用 no-index whitespace 检查，没有 whitespace diagnostics（相对 NUL 的内容差异退出码 1）。394 个起始路径中只有本轮列出的 11 个源码文件内容变化，其余 383 个路径保留原样；已有删除也保留。新增一个测试文件、报告/验证摘要及 synthetic 示例。完整回归尾部的 Demo/port 提示来自既有测试的 mock 输出，测试 runner 总结为 OK。

## G. 独立 GO / NO-GO

| 范围 | 结论 |
| --- | --- |
| TEST：本地原生 Planning→Intake→新绑定→逐 claim 人审候选 | **GO（有界集成子链路）**。EXPLAIN 单操作 profile；真实工作流与验证器运行；候选无 Draft 权限。 |
| 真实客户完整流程 | **NO-GO**。生产身份、可靠当前人审源、原任务导入/生产路由强制绑定尚未接入；PDF/DOCX/OCR、多任务及早期缺口不在 V1。 |
| 商业/正式 Draft | **NO-GO**。没有客户证据授权 purpose，也未把补充事实映射成已验证网站事实；新入口全部拒绝 Draft。 |
| WordPress / 发布 | **NO-GO（本轮未授权/未执行）**。保留 create-only/draft-only 的原约束。 |

本轮没有付费 LLM、真实站点、WordPress、生产签核、正式商业 Draft、Windows 安全配置变更或 commit/push/reset/clean。
