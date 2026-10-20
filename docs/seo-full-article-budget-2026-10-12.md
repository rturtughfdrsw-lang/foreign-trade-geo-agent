# 完整采购指南：预算解除、离线压力测试与下一次 Flash 实验准备

本轮原生离线状态为 **OFFLINE_CONTRACT_READY**。真实请求预检仍为 **BLOCKED_TOKEN_BOUND_CONFIRMATION**，没有标记 REAL_REQUEST_PREFLIGHT_READY；真实写作质量为 **REAL_WRITING_QUALITY_UNTESTED**；生产交付为 **PRODUCTION_NO_GO**。

没有真实 DeepSeek、余额或 WordPress 请求，没有部署、commit、push、merge，没有修改生产 Gate、P1 或 PostgreSQL。所有文章、资料和审核演练均为 SYNTHETIC / Mock。TEST-only APPROVE 不是客户批准或可信真人签核。

## 1. 预算审计与旧阻断

[完整预算表](seo-full-article-budget-2026-10-11/budget-audit.md)列出 input material、request envelope、raw output、tokens、claims、blocks、sections、单 claim、premises、文档/事实/引用，以及审核、Web 和 retention 的限制与代码位置。

旧 16 claims、8 blocks、300 字符解释正文不足以容纳此前 19 claims / 13 blocks 的诊断布局。六章最低占六块，几乎没有多段分析的余量。即使只增大 max_tokens，16KB Parser、16KB 审核正文和 Web 原始候选读取仍会拒绝更充分的输出。

已有 JSON 以 fact_ref 输出 premise 引用，程序绑定原文、来源和版本，没有重复输出整套原文。这次继续沿用，未删减关键事实、读者问题或条件，也没有引入短键名/第二套 Draft 格式。结构元数据仍占相当比例，但实际完整 Mock 输出已能容纳，无需按章节生成或建设多 Agent 写作系统。

另外发现审核后 18 条解释回填，原生 user material 达 38,594 chars；旧 26,000 上限阻断完整 workflow 复验。这一问题先失败并定位，再同步扩容输入，未绕过原生检查。

## 2. 最小有界方案

| 项目 | 本轮前 | 本轮后 |
|---|---:|---:|
| claims / draft | 16 | 48 |
| blocks / draft | 8 | 24 |
| E interpretation 正文 chars | 300 | 1,200 |
| 直接事实 / 普通 P/S claim chars | 300 | 300 |
| interpretations / reviewed bundle | 12 | 48 |
| raw output chars / UTF-8 bytes | 16,000 / 32 KiB | 64,000 / 128 KiB |
| user material chars / bytes | 26,000 / 56 KiB | 52,000 / 112 KiB |
| envelope chars / bytes | 36,000 / 76 KiB | 64,000 / 144 KiB |
| provider max_tokens | 3,000 | 16,384 |
| HTTP response bytes | 64 KiB | 256 KiB |

章节最多六章、每章最多四个 paragraph、每段最多四条 claim、每解释最多二十个 premise、资料最多八份/合计 16,000 chars、事实最多六十四条，这些边界不变。多个 claim 可以在一个自然段中组合；一个解释可以有多句、多 premise，章节和 claim 不一一对应。

Prompt 明确容量是上限而非写作配额；要求自然组织不同章节，解释参数的采购意义、条件、未知和验证动作，不强制逐段套“事实→意义→行动”句式。E 分析不要求只复述来源词汇；所有新解释仍待独立语义审核。EDITORIAL/CTA 的事实防伪规则保持不变，不能借标签隐藏参数或承诺。

请求现在显式设置 JSON response_format；原截断、非正常 finish、JSON 错误、超限拒绝继续保留。扩大响应留存上限用于容纳 JSON 转义和 envelope；超限响应仅保留明确标记的有限前缀，绝不当作完整文章成功。

## 3. 本轮修改文件与兼容性

实际变更相对于进入本轮时的工作区，而不是 Git HEAD；已有大量未提交工作全部保留。完整清单见 [changed-from-session-baseline.json](seo-full-article-budget-2026-10-11/changed-from-session-baseline.json)。

- `core/content_draft.py`：有限容量、派生 repair/material 预算、仅 E 解释的长度分支。
- `core/draft_customer_evidence.py`、`core/evidence_intake.py`：解释正文/数量同步，事实和 premise 边界不变。
- `core/content_draft_review.py`：审核正文与决定容量同步。
- `adapters/deepseek_content_draft.py`：自然写作指导、JSON mode、原生 tokens 参数。
- `adapters/retained_deepseek.py`：256 KiB 有界响应留存；允许旧实验指定更小上限。
- `web/candidate_review.py`、`web/generation.py`、`web/experiment.py`、`web/mvp_routes.py` 和 `templates/{mvp,mvp_candidate,mvp_generation}.html`：同步读取/编辑/显示预算，freeze manifest 读取实际请求参数。
- `scripts/accept_autonomous_interpretation.py`：复用原生验收器，支持独立 Mock 响应工厂，计数/预算动态计算。
- 新增 `scripts/accept_full_article_budget.py`、`tests/test_full_article_budget.py`；更新原预算边界和 Web 回归断言。
- `scripts/prepare_seo_article_experiment.py`、`prepare_seo_e_only_experiment.py`：历史短实验明确保留 3,000 tokens / 64 KiB 响应限制，不随新默认值漂移。

原生 V1 JSON/Draft 字段、artifact payload_version、SQLite schema、追加写语义均未变。历史 V1 SQLite 复制到临时目录后，当前 codec 成功读出旧六块文章；历史冻结文件进行会话前后逐文件 SHA256 核验。新大产物不承诺被旧版本程序接受。

没有降低数字/单位/型号、原文精确引用、条件、来源独立性或版本要求。未审解释仍拒绝正式 Finalizer 准入，旧 text/premise/reasoning/Plan/来源绑定变更使旧意见无效。生产运行入口与 WordPress 边界保持原状。

## 4. 六章压力测试实际结果

最终冻结：[final-v2/readiness.json](seo-full-article-budget-2026-10-11/final-v2/readiness.json)。

| 场景/环节 | 实际结果 |
|---|---|
| A：E1-only 要完整采购指南 | BLOCKED，F1–F8 均有具体缺口；writer calls=0 |
| A 的缺口 | 型号/夹具、主轴功率及 loaded 条件、材料切削、测量方法、条件筛选、RFQ/FAT 责任、交付培训服务、版本适用范围 |
| B：丰富资料 | 七份独立资料、43 facts、六章原生 Plan；输入预写解释为零 |
| Mock 全文 | 1,850 空格分词，12,884 正文字符；旧 Mock 为 368 词 |
| 原生结构 | 25 claims、19 blocks、18 个新解释候选，段落长度不同、六章问题不同 |
| 输出 JSON | 27,163 chars / UTF-8 bytes；完整尾部 CTA 保留 |
| Parser / candidate Validator | 通过，PENDING_SEMANTIC_REVIEW |
| 未审核 Finalizer | INTERPRETATION_PENDING_REVIEW，不能准入 |
| 明确 TEST-only 审核 → 原生 Finalizer / Workflow | success；不是生产或真实客户签核 |
| SQLite / 独立 Reader | 原始输出、逐条决定、18 条解释和原生 Draft 完整重读 |
| Markdown / Web | 全文、最后 CTA、全部 fact refs、原文、来源、版本和哈希展示成功；重启重读成功 |
| 边界 | 48 claims / 24 blocks 正好通过；49 claims / 25 blocks 拒绝；解释 1,200 / 1,201；premise 20 / 21；input/envelope/raw chars/bytes 正好触顶与超限均验证 |
| JSON / 截断 / 响应超限 | 明确拒绝；原始输出或有限前缀按状态保留，没有静默切尾后成功 |

六章分别讨论型号和夹具、主轴额定和 loaded 试验、材料与切削 recipe、工件测量和验收、RFQ 与责任、dispatch/training/support。稿件有条件比较、测试局限、未知事项、具体验证建议和 CTA，没有为字数新增无依据参数。它仍是人工脚本模拟，不能证明真实模型能达到相同解释深度。

[Mock 文章](seo-full-article-budget-2026-10-11/final-v2/mock-article.md)、[待审 Markdown](seo-full-article-budget-2026-10-11/final-v2/native/B-rich-evidence/candidate-pending.md)、[待审 Web HTML](seo-full-article-budget-2026-10-11/final-v2/native/B-rich-evidence/candidate-pending.html)和原生 SQLite 均已保存。

## 5. 下一次真实 Flash 实验材料与预算

新独立目录为 `seo-full-article-budget-2026-10-11/final-v2/`，不能复用历史请求许可。75 个产物的独立 SHA256 清单为 [artifact-sha256.json](seo-full-article-budget-2026-10-11/final-v2/artifact-sha256.json)。

确切 request SHA256：`7163ba11207bed8636053ce39779c5fc4d424933b23c3cce22d99295f6573bb9`。

原生 web bundle SHA256：`e1a416ed8794d86c8e4f656eac7fb47b8076d9639422c993ec27ce39c9d0e043`。

冻结包含目标/搜索意图、六章原生 Plan 和 writing brief、七份来源原文与 43 facts、审阅快照、确切 System Prompt/User Material/request、V1 codec 和 Validator 源码哈希、输出/usage/失败留存方案。请求为 `deepseek-flash`、temperature=0、thinking disabled、JSON、一次、60s、无自动重试。

最终输入 user material 为 22,264 chars，System Prompt 为 7,828 chars，实际 request 为 31,919 chars / bytes。两条消息合计 30,092 chars，粗估约 7,523–15,046 tokens。输出粗估约 6,791–13,582 tokens，相对 16,384 留约 2,802 的估算余量。

各组件均单独记录在 [budgets.json](seo-full-article-budget-2026-10-11/final-v2/budgets.json)：task/Plan/brief 5,868 chars、客户 facts 10,804、来源引用 2,162、空解释目录 2、P/S planning context 1,692、input JSON wrappers/metadata 1,736；输出正文 12,884，refs/proposals/JSON metadata 14,279。组件拆分用序列化片段/残差核算；估算不包含精确模型消息 framing tokens。

采用的 2–4 chars/token 是明确标记的离线启发式区间，不是 DeepSeek tokenizer、官方精确计数或经证明的上界。没有可信适用的本地 tokenizer 验证，服务端实际 usage=null。因此 structural budget 已解除，但 REAL_REQUEST_PREFLIGHT_READY 仍未成立。

[公开官方价格记录](seo-full-article-budget-2026-10-11/public-api-notes.md)于本次审计查询，无鉴权。保守使用峰值 cache-miss input/output USD 0.30/1.20 每百万 tokens；在“输入最多 65,536 tokens”这一待确认预算假设下，单次估算 USD 0.0393216。拟议费用上限 USD 0.05，不是账户或服务端硬限额，实际授权费用为零。旧验收器嵌套目录中的归档 CNY 估算仅为旧 harness 演练，不是本次真实实验报价；以顶层 [real-request-preflight.json](seo-full-article-budget-2026-10-11/final-v2/real-request-preflight.json) 为准。

准备有效期到 **2026-10-13 00:10:31（Asia/Shanghai）**，没有签发 LIVE permit。到期必须重新核对并冻结。授权前还须确认 tokenizer 或明确接受估算风险、重查价格/model alias/模型限额、验证全部哈希和当前 Plan/资料/范围审核。五分钟 TEST 复核新鲜度不等于二十四小时调用许可；执行前必须重查。

未来单独授权的准确范围只能是：针对以上 request 与 bundle，进行一次 SYNTHETIC Flash 质量测试，最多 16,384 output tokens、60s、零重试、拟议 USD 0.05；安全私有留存完整原始响应、usage、失败信息和待审候选。超时/断线/未知结果不重试。任何新解释继续等待真人语义审核。授权不包括余额查询、真实客户发布、WordPress、部署或生产交付。本轮没有请求或获得该授权。

## 6. 质量验收与剩余阻断

[简洁人工验收表](seo-full-article-budget-2026-10-11/quality-review.md)统一使用事实准确性、解释深度、采购价值、搜索意图/结构、原创/重复、CTA 六个维度，保留 170 词真实 Flash 历史样本，要求具体段落/claim 和来源依据。资料、Plan、Prompt、生成契约均改变，不能宣称单变量模型对照。

剩余阻断是可靠 token 计数或明确接受估算不确定性、执行前最新价格与绑定复核、新的单次真实实验授权，以及真实生成后的专业人工质量验收。当前没有真实新稿，不能宣布商业文章质量合格。生产事实审核/执行权限仍为 NO_GO。

## 7. 实际验证与中途失败

**最终完整回归：1,871 tests，534.542s，OK，退出码 0。** 实际命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q`。首次完整回归的失败与修复保留如下。所有日志位于 `seo-full-article-budget-2026-10-11/verification/`。

- `01-capacity-before.log`：新增容量测试先失败，1 failure / 1 error；复现旧上限与缺少 JSON mode。
- `02-targeted-first.log`：59 tests，10 failures / 3 errors；硬编码旧预算断言、历史实验参数漂移和 UTF-8 边界样本过小，分别修正；原有效断言保留并移至新边界。
- `03-full-guide-probe.log`：Mock “missing torque curve” 触发现有 absence guard；调整 Mock 为尚待应用审核的表述，没有放松 Validator。
- `04-full-guide-probe.log`：审核解释回填后 material 38,594 超旧 26,000；扩大有限输入后原生复验通过。
- `05-targeted.log`：118 tests，3 failures；测试重复 claim 先于总 block 检查、旧 retention 默认值漂移。改为唯一 claim，并为旧 runner 显式传 64 KiB 限制。
- `06-full-guide-probe.log`：完整六章原生离线验收成功。
- `07-targeted.log`：118 tests，28.757s，OK。
- `08-full-article-tests.log`：11 tests，1 failure；新测试修改版本后却回放未变的旧输入，修正测试对象，没有更改准入逻辑。
- `09-targeted-expanded.log`：192 tests，1 failure；Web 超限断言仍用 16,001，更新为 64,001，并同步实际 textarea/响应限制展示。
- `10-targeted-final.log`：82 tests，78.471s，OK。
- `11-additional-boundaries.log`：3 tests，8.542s，OK，覆盖旧 V1 SQLite、请求双边界和长截断/超限响应留存。
- `13-final-freeze.log`：冻结脚本退出码 0；无真实调用许可。

FastAPI/Starlette 的 httpx TestClient 弃用提示与 Git CRLF 提示保留记录，本轮没有为此改依赖或进行无关重构。

- `12-full-regression.log`：1,863 tests，436.350s，1 failure / 1 error。总 claim 测试仍构造旧 18 条；旧丰富资料诊断请求因重复预算元数据达到 16,059 bytes，超过其 16,000 bytes 界限。总 claim 断言移到 50 条、每段仍合法的布局；E 专用长度元数据仅提供给结构化 E 文章，旧诊断的资料/Brief 与上限都保持不变。
- `15-legacy-rich-diagnostic.log`：独立复现 full Brief 19,450 bytes 被拒和旧短诊断 16,059 bytes 被拒，定位明确。
- `16-regression-repair-targeted.log`：100 tests，33.432s，OK，包含全部旧 rich buyer guide 测试及核心/完整文章/历史实验回归。
- `18-final-v2-freeze.log`：最终源码状态重新冻结，退出码 0。先前 `final/` 与所有探针保留，当前授权前检查只能针对 `final-v2/` 的新哈希。

- `17-full-final.log`：最终完整回归 **1,871 tests，534.542s，OK，退出码 0**。
- `19-final-v2-independent-hash-check.json` / `21-post-regression-integrity.json`：最终 75 个冻结文件、源码哈希和 1,088 个历史文档文件核验一致。
- `20-frozen-request-refresh-check.json`：刷新 TEST 审阅时间戳后确切请求 bytes 不变；没有签发许可或请求模型。
- `git diff --check`：退出码 0；仅有已有 CRLF 提示。
