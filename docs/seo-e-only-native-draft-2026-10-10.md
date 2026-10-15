# 客户 E-only → 原生 Draft：离线工程验收

日期：2026-10-10，Asia/Shanghai。范围：一个虚构 NovaCNC 客户、一个 CREATE_NEW_RESOURCE、一个 UTF-8 客户文本文件、一篇英文候选。**工程 PASS 仅限明确隔离的 TEST-only 路径；不是客户签核、人工语义证明、商业质量批准或生产执行授权。**

## 原阻断位置与选择

Intake 已能登记客户 E、版本、客户/任务归属、requirement、locator、文件 hash、审核 span，并支持单 CREATE 原生重核。上一份 numeric 修复报告末尾称其仅支持 EXPAND 已过时；本轮以实际源码和文章 MVP 报告为准。

真正缺口在 `ContentDraftInput` 无 E catalog；`DraftClaimSpecification`、Parser 和持久化 `DraftClaim` 只有 page_refs/source_refs；`_validate_claim_evidence` 的第一方事实和数字只能取引用 P；Finalizer、Review 也不保存和展示 E。上一篇文章依靠 P 本来就有全部参数，不能证明 E-only 支持。

本轮复用同一个 ContentDraftWorkflow、严格 JSON Parser、Validator/Finalizer、ContentDraftReport/DraftItem、SQLite codec 和只读 Review，没有平行文章系统。使用可选 `customer_evidence` 输入/输出绑定和可选 claim `customer_refs`；旧 P/S JSON 仍可省略它们，旧 P/S 序列化也不额外写入空字段。保留原 8 blocks、16 claims、300 字符/claim、输入和输出预算。

## 信任边界与最小约束

新增 provider-independent `DraftCustomerEvidence` / `DraftCustomerSource`，保留客户/项目/任务、task/Plan/evidence/revision、完整 snapshot digest、原生 P/S/operation scope digest、审核身份/时间/状态、原文全文、UTF-8 hash、locator、requirement 和字符 span。

当前唯一可用 review profile 为 **TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF**。生产没有对应可信审核/执行目的，因此只在 `scripts/demo_seo_e_only.py` 的固定合成 harness 中组装 E 输入。CLI 只接受新的输出目录，不能选择真实客户文件、provider、审核人、网络 endpoint 或 live 开关。

演示时钟固定为 `2026-10-10T06:00:00Z`（北京时间 14:00），审核有效期测试相对于该 TEST 时钟；记录不是运行时发生的真人签核。

受控入口从 Intake journal 读当前版本，检查客户/任务/Plan、当前 snapshot、plan_bound、所有 requirement 的 SUPPORTED decision、span 和原文、五分钟审核有效期及 reviewer 可用性。生成前后重新从当前 journal 和 TEST reviewer 重建输入，逐字段比较；版本更新、撤销/不可用、替换 locator、伪造版本/requirement/审核状态均不能依靠自报 hash 通过。失败候选不进入保存步骤。该机制是固定离线演示，**不提供生产并发 lease、可信真人身份或授权平台**。

原生校验再检查 E ID 存在、原生 operation scope 绑定，E claim 类型必须为 OBSERVED_PRODUCT_FACT，且整句必须等于一个完整已审 span；每个必需 E quote 都要进入正文。这样防止把型号、测试条件或限制删除后仍称通过。数值规则仍使用原算法，取当前 claim 引用的 P/E 原文，S 不能替代第一方依据；型号、协议/证书编号、单位、日期和裸数字仍校验。E 数字诊断标识 CUSTOMER_EVIDENCE，不伪称 P。

**逐字保留、存在性和 hash 只证明结构、版本绑定与文本保留，不证明源资料真实、语义正确或测试适用。** 自由改写、跨段推断、多来源合并关系不在本轮能力内，仍需人工审核。核心 validator 对冻结输入做确定性检查；“当前状态”由 TEST 入口对当前 journal 重验完成。历史 Review 明确显示 historical binding，不宣称重新认证了当前源或审核权限。

生产 runtime、真实 DeepSeek adapter 和 Intake Draft admission 保持拒绝。额外拒绝把 TEST-only E Draft 构建成 WordPress 请求，避免演示候选被误用于交付。P1 没有修复或绕过，PostgreSQL 仍 BLOCKED。

## 实际文章与逐项来源

候选标题：NovaCNC machining center buyer guide。235 个英文空白分词、两节、四个 paragraph blocks、13 条 claim。固定 writer 一次返回完整原生 NEW_RESOURCE_DRAFT JSON；不是模型生成。

文章及审核材料见 [article-review.md](seo-e-only-acceptance-2026-10-10/article-review.md)、[原生 Draft](seo-e-only-acceptance-2026-10-10/05-content-draft.json)、[逐条来源核查](seo-e-only-acceptance-2026-10-10/07-evidence-binding.json)。

关键事实 CL3 仅引用 E1，page_refs/source_refs 都为空：

> SYNTHETIC ONLY: NovaCNC NCX7 spindle rated 7200 rpm continuously under NOVA-TEST-7 protocol at 20 C on an unloaded bench; applies only to NCX7 and is not a cutting-load or production guarantee.

E1 来自 `customer-E1.txt`，locator=`synthetic:novacnc/NCX7/spindle-v1.txt#paragraph-2`，字符 span `[46:239]`，record version=2；task/Plan/evidence/revision=1/2/2/3。全文件 UTF-8 hash 和 snapshot/scope hashes 保存在原生 Draft，SQLite 重开后等值保留。

| Claim | 引用 | 校验与含义 |
| --- | --- | --- |
| CL1 | 无 | 编辑开篇，无事实引用 |
| CL2 | P1 | 网站普通采购背景；不含 E 参数 |
| CL3 | E1 | 完整型号、7200 rpm、测试方法、20 C、空载条件及限定；原生数值校验、完整 quote 和 F1 绑定 |
| CL4–CL12 | S1 | 行业解释及采购核对建议，未验证外部背景；没有 E 产品参数 |
| CL13 | 无 | 结尾 CTA，无事实引用 |

独立断言 P/S 完整 native packet/material 中不含 NCX7、7200 rpm、NOVA-TEST-7、20 C、unloaded bench 或完整 E 事实，没有向 P/S 注入客户内容或改名。审核文件逐 claim 展示 E 原文、locator、span、版本、审核状态及 SYNTHETIC reviewer；全部文章 claim 仍 **UNREVIEWED**。

## SQLite、导出与复现

最终本地数据库在 `.data/e-only-20261010/final-v2/history.sqlite3`，Intake journal 同目录；不复制数据库进 docs。原生 encode/decode 等值，新 SQLite reader 重开等值，实际 `review --format markdown` 导出与原生 Markdown renderer 逐字一致。客户文本文件的实际 UTF-8 字节、hash 与原生 source content 完全一致；旧 P/S 文章 decode/encode 后的原生 payload 字节也与历史样本一致。

再次独立执行得到不同 run/artifact IDs，但正文 SHA256 同为 `4e9d0695fffec040863b4cc13640f3be182044513013613d88d2e3dbcec46679`。完整 Draft hash 因包含独立 provenance 而不同，不能把正文一致误称为相同的审核/执行绑定。

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_seo_e_only --output-dir .data/e-only-new
# 从新目录 verification.json 读取 run_id / artifact_id
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent review --db .data/e-only-new/history.sqlite3 --run-id <run_id> --artifact-id <artifact_id> --draft-id D1 --format markdown
```

## 正反例与回归

新增 `tests/test_seo_e_only.py`。覆盖缺 E；篡改数值/单位/型号/协议/日期/证书编号；删改条件/限定；漏写必需 E；E 冒充 P/S 或一般 S 背景；假 E 编号、locator、review state、版本/requirement；当前 E 更新、生成期间更新；错误客户/项目/任务/Plan/版本；未审核/冲突/不相关/缺失；审核超时、不可用/撤销；失配 hash/span；更新文件即使重算 hash 仍不能获得固定 TEST verdict；旧 P/S artifact 和旧 Intake digest/readback；生产模型/Draft/WordPress 拒绝。

旧 Draft 类型、数值边界及 P-only 等既有模块一并回归。最终完整回归 **1677 tests / 386.035s / OK / exit 0**（此前 1648 + 新增 29）。相关组合 164 tests / 15.075s、边界组合 64 tests / 15.502s、最终 UTF-8/Intake focused 47 tests / 9.317s 全部通过；`git diff --check` 与新文件空白检查通过。详细实际命令、退出码、耗时和日志索引见 [test-verification.json](seo-e-only-acceptance-2026-10-10/test-verification.json)。日志的 asyncio slow-task、Starlette 弃用提示和 Demo launcher 模拟提示不是测试失败，没有实际发布或启动服务。

迭代中观察到并修正：第一次 E quote 未按现有 numeric grounding 所要求进行归一化，导致 NUMERIC_NOT_GROUNDED；按 P 的既有归一化路径处理 E，没有改数值提取/豁免规则。新测试最初尝试修改不存在的 ChangeOperation.rationale 字段而报错，改为结构一致的新资源标题变更。首次完整回归 1677 tests / 278.716s 中有一项旧字段数量断言失败（5 != 4）；这是本轮明确获准扩展可选 E 输入导致。更新该测试为核对精确五字段、E 默认 None、旧序列化仍恰好四字段且无损读回，保留其余有效断言。

额外文件 QA 暴露 Windows `write_text` 自动将 LF 转成 CRLF，导致导出的客户文本文件实际 bytes hash 不等于 Intake content hash。改为按原始 UTF-8 bytes 写出，并加入实际文件 bytes/原文/hash 一致性断言；重新生成 final-v2/repeat-v2 后一致性检查通过。没有将旧导出文件重新标成验证通过。

## 实际改动文件

- 新增 `core/draft_customer_evidence.py`：有界原生 E 契约和 scope binding，明确 TEST-only。
- 修改 `core/content_draft.py`：可选 E 输入/claim refs、原生校验/coverage、数值诊断、Finalizer 和 Draft 保存。
- 修改 `workflows/content_draft.py`：Parser 的可选 E 字段及同一 Finalizer 的传递。
- 修改 `adapters/deepseek_content_draft.py`：条件 E prompt 契约，不改真实 transport 拒绝边界。
- 修改 `core/evidence_intake.py`：无 E 旧 snapshot 的 digest 兼容。
- 修改 `storage/serialization.py`：可选字段读写与旧 V1 兼容，无数据库迁移。
- 修改 `core/content_draft_review.py`、`workflows/content_draft_review.py`、`reporting/content_draft_review.py`：历史 E scope 核查、claim 引用和 Markdown 原文绑定。
- 修改 `core/wordpress_draft.py`：拒绝 TEST-only E 进入 WordPress payload。
- 新增固定演示脚本、29 项 focused tests；更新 `tests/test_intake_native_planning.py` 的旧输入兼容性契约测试；新增本报告及合成审核 artifacts。

本轮开始时的未提交修改全部保留；README、cli、runtime、storage/evidence_intake 等此前修改未在本轮改动。没有 stage、commit、push、merge、发布或部署。

## 验收结论与 MVP 余项

**E-only 离线工程验收 PASS。** 只覆盖单任务、单 CREATE、短文本、完整提取式 E quote 与原生文章闭环。当前真实模型调用、客户站点请求和 WordPress 写入均为零。

仍需人工判断原始资料真实性、权威来源、完整条件、跨材料冲突、参数对目标采购场景的适用性，以及英文专业质量、搜索意图、解释深度、采购转化与商业 SEO 价值。本文不能据工程 PASS 获得正式签核。

后续 MVP 的必要条件：

1. **前端**：将补证、缺口、未审/冲突/过期、当前版本、逐 claim P/S/E 原文核对及全文质量决定接成可用交互；当前 CLI/JSON/Markdown 只是工程演示。
2. **真实模型 E-only**：可信客户来源和审核身份、当前 evidence/task/Plan 正式执行 purpose、撤销/时效/并发重验或 lease；冻结输入与具体一次调用授权、模型/费用/时限和无重试边界；通过原生校验后再独立人工质量审核。当前 TEST profile 不可转成生产授权。
3. **WordPress 草稿交付**：正式批准的当前文章、明确目标站与单独写入授权、生产交付 composition，以及整篇 HTML 保留分节标题的适配验收；维持 create-only/draft-only、写后核验和 UNKNOWN/PENDING 禁盲重试。还必须解决既有 P1 阻断；本轮未处理。PostgreSQL BLOCKED 不能被 SQLite 通过替代。

完成此闭环后停止，等待下一轮指令。
