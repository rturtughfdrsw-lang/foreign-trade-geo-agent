# 单篇英文 SEO 文章：离线生成与本地审核验收

日期：2026-10-10。范围仅为 NovaCNC **合成资料**、单任务、单个 `CREATE_NEW_RESOURCE`。这是结构完整的短文章候选和工程路径演示，**不是 DeepSeek 成稿，不是商业写作质量验收，也不是生产 Draft 授权**。

## 实际结果与可复用能力

已生成 `NovaCNC machining center buyer guide`，正文 **293 个英文空白分词**、一个 `D1 / NEW_RESOURCE_DRAFT`、两个原生正文节、五个 paragraph blocks、14 条 claim。包含开篇、主轴说明、公差说明、证书适用范围、采购核对建议与结尾 CTA。标题、两节及整篇正文一同持久化，重开 SQLite 后由既有 `ContentDraftReviewWorkflow` 选择并审核整篇 D1。预览保留正文逐项 CL/P/S 引用和每条 `UNREVIEWED` 状态。

- 文章预览：`docs/seo-article-acceptance-2026-10-10/article-preview.md`。
- 原生 Draft：`03-content-draft.json`；整篇只读审核：`04-article-review.json`。
- 三组完整客户文档与 CL/F/E 对应关系：`submission.json`、`05-evidence-binding.json`。
- 补证前缺口与自然待审状态：`01-missing-evidence.json`、`02-intake-human-review.json`。
- 实际运行结果：同目录 `verification.json`；测试汇总另见 `test-verification.json`。

核查结论：

| 原能力 | 本轮处理 |
| --- | --- |
| `CREATE_NEW_RESOURCE` / `NewResourceSpec` | 直接复用新资源标题、确定性两节 outline、P/S 来源绑定、EXPLAIN content points。没有新增文章生成协议或多操作调度。 |
| `SECTION_DRAFT` | 保留现有 ADD/EXPAND 节草稿行为；新资源内部仍逐节复用原 prose finalizer，未把多个独立节任务拼成文章。 |
| `ContentDraftWorkflow` | 固定离线 writer 返回与真实 provider 相同的 JSON 契约，经过既有严格解析、数值、claim 分类、引用、块/claim 预算和 finalizer。 |
| Evidence Intake | 原限制位于 `core.evidence_intake.native_plan_error` 的单 EXPAND 判别及 ExpandSpecification 重建；保留单操作、全 EXPLAIN、全义务覆盖，增加无嵌套比较表的单 CREATE 支持。 |
| 原生重新核对 | `RetainedIntakePlanWriter` 增加 CREATE 的 page_bindings/resource 字段，继续经原 `ChangePlanWorkflow` 验证，不凭旧 report 或 digest 自动批准。 |
| 人工审核 | 复用 PlanningReviewCandidate、ContentDraftReviewWorkflow、持久化 HistoryReader；补证充分性和文章审核均与执行授权分开。 |
| 导出 | 原有 JSON/文本只读审核可复用；增加 `review --format markdown`，无需加载 `.env`。导出本身不写审核状态，不调用 writer 或 WordPress。 |

发现并修复一处文章组装缺口：旧 finalizer 丢失新资源的 outline 与每节 block 边界。现在保存 `ordered_headings` 和有界 `section_block_counts`，审核可恢复各节实际正文。旧 payload 缺少新增字段时使用空 tuple，继续旧显示方式；不猜测旧正文分节，也不改写旧 artifacts。新增字段沿用既有 V1 可选默认字段兼容机制，不做数据库迁移。

## 演示的证据与执行边界

本场景的网站 P1、研究 S1、客户 E1-E3 都是明确构造的离线材料，`.example` 地址未被访问。网站 fixture 独立包含三组事实，客户文件提供逐字相同的合成声明；网站已经展示声明仍不等于其客户原始证明、适用性和授权已核实，所以补证义务要求文件与人工核对。**没有把客户 E 内容注入 P/S catalog，也没有把 E 改名成 P1。**

三组必需事实分别对应 CL2/F1/E1、CL7/F2/E2、CL10/F3/E3：

- 主轴：8000 rpm、连续额定、DEMO-SPINDLE-1、20 C、不证明切削负载。
- 公差：+/-0.02 mm、铝测试件、20 C、DEMO-TEST-2 protocol、不保证其他材料或生产条件。
- 证书：DEMO-CNC-1、Fictional Lab、DEMO-2026、VMC-DEMO、2027-01-01 到期、明确不是真实认证。

绑定 manifest 保留原 project/customer/task、task/plan/evidence/revision = **1/2/2/3**、完整 snapshot digest、原始五个 artifact ID 与 payload hashes、输出 artifact ID/hash、客户文件 hash/locator/原文 span。逐字断言确认必要事实与限定全部进入最终文章。该绑定供审阅追溯，**不证明客户或 reviewer 身份，不是执行 token，也不是通用 E→claim 语义判定系统**。

演示先使用生产 composition 调用本地 ports，得到 `INTAKE_EXECUTION_BLOCKED`，生产 writer **0 次**；补证与原生重核后自然停在 `UNREVIEWED / HUMAN_SEMANTIC_REVIEW_REQUIRED`。随后仅在演示 harness 中注入明确的 `SyntheticHumanFixture` verdict，核查完整当前绑定后进入现有 `build_isolated_test_planning_workflow`，固定手写 writer **1 次**。生成后再次核查绑定和 TEST verdict，再导出。该 TEST 充分性结果不代表真人签核；文章仍全部 UNREVIEWED，`draft_authorized=false`。

独立重跑两遍，run IDs 不同，原生 Draft 的 SHA256 相同。没有真实网络、DeepSeek、真实客户资料、WordPress 写入、发布、部署或 Git 历史写入。SQLite 和完整运行日志留在 ignored `.data/article-mvp-20261010/`，不复制数据库进 docs。

## 复现与审核

从仓库根目录运行，输出目录必须不存在：

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_seo_article --output-dir .data/article-demo-new
```

读取新目录 `verification.json` 中的 `offline_run_id` 和 `content_draft_artifact_id`，可以重新导出同一篇持久化文章：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent review --db .data/article-demo-new/history.sqlite3 --run-id <offline_run_id> --artifact-id <content_draft_artifact_id> --draft-id D1 --format markdown
```

`article-preview.md` 在通用 Markdown 审核结果外另附合成样本声明和客户绑定摘要。CLI 通用审核不会加载 Intake journal；客户证据绑定需要同时检查 `05-evidence-binding.json` 与 `02-intake-human-review.json`。脚本不接受真实 writer、客户文件、provider 地址或生产执行开关。

## 验证范围

新增 15 个 focused tests：完整文章/节边界、全量事实限定保留、客户 span 与原生来源、Markdown/CLI、只读无状态写入、旧 payload 兼容、畸形节边界拒绝、缺证/未审核/冲突/过期/旧版本/新补证未绑定拒绝、E 伪装 P 拒绝、单操作与 EXPLAIN 限制、标题/outline/来源建议不可在 rebind 中替换、即使 TEST 充分仍拒绝生产 Draft。

实际验证全部通过：原生/Intake/审核组合 **114 tests / 15.290s / OK**；最终 CLI/Draft 边界/只读组合 **80 tests / 20.158s / OK**；完整回归 **1614 tests / 270.689s / OK**，三次退出码均为 0。完整回归较此前 1599 新增 15 项。`git diff --check` 退出 0，新脚本/测试另查无尾随空白。独立演示两次及实际 CLI Markdown 审核退出码均为 0，文章原生 payload hash 一致。完整回归尾部的 Demo/8000 提示来自既有模拟测试，不是实际启动或部署。测试命令、日志路径、耗时、源文件 hashes 见 `seo-article-acceptance-2026-10-10/test-verification.json`。

迭代失败也保留：

1. 最初 topic fixture 使用句点，原生候选文本带标点，与精确 candidate 选择不符；改用契约已有的分隔结构。
2. 固定样本过渡句触发事实分类保护，调整纯编辑过渡句；未删事实。合成编号 `DEMO-TEST-2;` 被现有数值规则判为裸数字，在源资料与文章中一致补全 `protocol` 标注；未弱化数值规则或删编号。
3. 第一轮新测试的全 socket 禁止同时拦截 Windows asyncio 的本地 socketpair，尚未执行测试；修为只允许 loopback，仍拒绝外部 socket。
4. 随后新测试暴露 CLI review 无必要地加载环境文件，现已让只读 review 在加载环境前返回。其他测试报错来自测试构造违反已有 dataclass 一致性及错误异常类型预期，改为一致的负例构造和真实 `MalformedHistoryDataError`，没有放宽生产代码。

## 尚未满足的 MVP 条件与下次最小授权

本轮 **GO 仅限离线结构/引用/审核路径**。短文的事实、句法与建议均为手写 fixture，293 词不代表真实模型能一次产出合格文章；未验证搜索意图覆盖、事实语义充分性、采购转化质量或商业 SEO 效果。仍缺：

1. 原生 Draft 对客户 E 文档的 provider-independent 证据类型、逐项引用与完整覆盖校验。当前模式只能用既有 P/S grounding，再附严格标注的合成客户审核绑定；不能处理“仅 E 有事实、P/S 没有”的真实客户文章。
2. 可信客户提交、材料真实性/适用性复核、可信人审身份和针对当前版本的正式 Draft execution purpose，以及执行前后版本/撤销重验或可靠 lease。当前 production route 与真实 DeepSeek transport 按原规则拒绝，普通批准措辞、digest 或 TEST verdict 都不能打开。
3. 一次受控真实模型实验及文章级人工质量验收。若原生两节、8 blocks、16 claims、单 claim 300 字符和现有输入/输出/token 预算不能容纳任务的完整事实，必须明确拒绝并评估任务/预算合同，不能删必要事实换取通过。本轮预算未提高。

下一次真实模型生成的最小方案是**仅一篇、仅合成 P/S 资料的本地实验**，先实现可审阅的受控实验授权边界，继续复用原生 Draft 契约/workflow；不得把真实 transport 塞进 TEST composition 或 MockTransport，不得改为默认生产允许。授权需冻结项目/任务、输入与证据 hashes、语言、模型、用途、调用/费用上限和有效期；授权使用 `.env` 内凭据调用指定真实 DeepSeek 模型，**一次调用、禁自动重试、120 秒以内、最多现有 3000 output tokens**，仅保存本地候选、净化诊断和逐条引用。真实模型输出需通过原生验证并整体人工审阅，失败即停止。

可供后续用户明确授权的范围文本（**本轮未授权、未执行**）：

> 在受控实验入口与前后绑定核验经本地验证后，允许用本次 NovaCNC 合成 P/S snapshot 为单篇英文文章进行一次真实 DeepSeek 生成，模型及费用上限另行明确，最多 3000 output tokens、120 秒、不重试，仅本地留存候选与审核材料。不访问真实客户站点、不使用真实客户资料、不写 WordPress、不发布部署。生产 Draft、P1 与 PostgreSQL 的阻断继续保留。

这份实验授权不能用于真实客户 E-only 生成或正式 Draft；两者必须先补上相应工程条件与单独具体授权。

## 本轮文件

修改 7 个既有源文件：

- `core/evidence_intake.py`：单 CREATE 原生 intake 复核与 rebind 保留新资源范围。
- `adapters/retained_intake_plan.py`：CREATE 保留规划的原生字段编码（文件在本轮开始时已经 untracked，保留既有实现）。
- `core/content_draft.py`：持久化有界新资源节边界。
- `storage/serialization.py`：旧 payload 默认字段兼容。
- `core/content_draft_review.py`：还原文章节正文。
- `reporting/content_draft_review.py`：整篇 Markdown 与正文 CL 引用、逐项状态和来源。
- `cli.py`：Markdown 只读导出，不加载凭据；保留此前已有 Evidence CLI 修改。

新增 `scripts/demo_seo_article.py`、`tests/test_seo_article_demo.py`、本报告和上述合成验收 artifacts。README、runtime、storage/evidence_intake 及其他本轮开始时已有修改/文件均未改动。未 stage、commit、push、merge 或执行其他历史写入。
