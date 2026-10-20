# Evidence Sufficiency Gate：正例候选整理与实施前 STOP

日期：2026-10-08（Asia/Shanghai）。**已整理一个有直接原文的受控站点任务候选，但未找到“已获授权、审核完成、绑定合法匹配 Plan”的可信充分正例。STOP：不进入 Gate 实现或真实 Draft 质量验收。** 没有用 Mock、模型结论、未验证市场声明或虚构签核补成 GREEN。

本轮交付：[候选证据矩阵与原文 span](evidence-sufficiency-candidate-matrix-2026-10-08.md)、[待授权审核 brief](evidence-sufficiency-review-brief-2026-10-08.md)，以及 ignored `.data/evidence-sufficiency-candidate-20261008/` 内的冻结快照、绑定、未填审核模板和离线核验材料。这些材料可以帮助授权人员作决定；整理者未取得或自称取得审核权。

## A. 查找范围、真实证据与契约核对

先阅读[边界设计](evidence-sufficiency-gate-boundary-design-2026-10-08.md)、[根因审计](seo-draft-quality-root-cause-audit-2026-10-08.md)、[真实 Draft 验收](seo-draft-live-acceptance-2026-10-08.md)及相关离线验收；核对当前工作区的 Planning/Draft/core validation/fixed workflow/codec 和相关测试。

以 SQLite `mode=ro`（辅助脚本额外设 `query_only=ON`）检索 `.data` 下 **58 个 SQLite 文件、76 条 run 记录、369 个 artifact**：74 SITE_CONTENT、74 SITE_AUDIT、73 INDUSTRY_RESEARCH、66 CONTENT_OPPORTUNITY、49 CHANGE_PLAN、33 CONTENT_DRAFT。按完整 canonical payload 去重得到五版 SITE_CONTENT：两版 Demo、薄 chemical compatibility fixture、一组早期受控站点 packet、一组较新受控站点 packet。去重是定位工具，不是充分性评分。[inventory.json](../.data/evidence-sufficiency-candidate-20261008/inventory.json) 保存逐库索引。

对全部保存 Plan 的 operation 做去重阅读（14 种完整 operation）；真实 EXPLAIN 候选主要是 P3 制造方案但挂统计标题的 C3，以及依赖未验证 automation sources 的新资源/段落。Demo 的 EXPLAIN 来源为 curated fixture。逐项筛选没有发现一份已有受信人工审核的正例。

| 候选来源 | 核对所得 | 本轮用途 |
|---|---|---|
| 薄证据 live Draft run | provider Draft 确为真实一次请求，但 crawl/search/Planning 准备是合成 fixture；同库还有 mock Draft | 保留真实模型失败的负例；不当真实技术事实 |
| Demo runs/fixtures | manifest 的 source revision 明写 unknown；边界由固定 provider 产生 | 机器契约参照，不是可信真实正例 |
| 受控站点较早 automation Plan | 原 point 依赖外部未验证描述；缺少可靠的机制解释与人工审核 | 不准入为充分正例 |
| post-structure-fix run | 有 DESCRIBE 和市场 SUMMARIZE，支持材料/目的不等同 EXPLAIN | 历史非解释型参照，不偷换为 Gate 正例 |
| post-budget run | P3 保存六组输入及用途；本地受控源码逐字对应；C3 则为统计指南 | 主候选原文来源；原任务/Plan 不被认证 |
| fresh-cli run | 同样保存五页受控原文，Plan 为 DESCRIBE/统计背景且含 comparison；run failed | 交叉参照，机器阶段记录不是成稿质量 |
| 本地 `geo-test-site` | clean worktree；已读 solutions、产品/关于/声明、完整买家文章、实验基线；来源声明 fictional | 核验已保存内容出处和限制；未抓公网、未把未入 packet 的文章加入 Draft 证据 |
| crawl-seo-audit | 提取成功、robots/title 等观察有记录 | 抓取健康辅助证据；不证明工程真实性/任务充分/审批 |

current `ContentPoint` 仍只有 intent/subject；`ContentDraftInput` 不含原任务/必答范围；subject occurrence 投影的 required refs 不是 entailment。普通 claim validation 核 ID、scope、第一方/数字等边界；workflow 在 stable input 后逐项调用 writer，没有可信人工 task-evidence preflight。证据枚举有界、来源未验证标签和历史 codec 均应保留，不把已有机器校验当充分性结果。

核对路径：`core/site_content.py::SiteContentEvidence`、`core/content_opportunity.py::ContentOpportunitySourceMaterial`、`core/change_plan.py::ContentPoint/_validate_content_points/finalize`、`core/content_draft.py::ContentDraftInput/_content_point_payload/_validate_claim_evidence/stable_content_draft_input_error`、`workflows/content_draft.py::_run`；读取 `test_change_plan_material_availability`、`test_content_draft_core/workflow` 和历史序列化测试。未改这些模块。

## B. 新候选任务、Plan 与证据矩阵

主来源 DB `.data/smoke/post-budget-cli-20261007-b3326475cd2f43c68a86e3aa59c7620a.sqlite3`；run `8cf30f2d-6f5f-4698-951c-30b427853a94`；SITE_CONTENT `f1e2e071-68e8-44c8-919a-92ab03a4a10b`；CHANGE_PLAN `58b02400-284f-4d16-affd-c9c523241901`；均 version 1。run 时间、所有五类 artifact ID/时间/digest、全量快照在 manifest/binding 中。

候选 `T-P3-EQUIPMENT-BRIEF-CANDIDATE-v1`：**按演示 solutions 页解释六组设备 brief 输入，以及各组服务哪项决策/规划。** 六个有限必答项 O1–O6 是零件定义、工序、质量、生产模式、工厂条件、出口范围；每项要回答“哪些输入 → 什么用途”，不只报主题。对应原文、字符区间、field/quote digest 与源码对应见独立矩阵。12 处 span 逐字可回切；额外一处虚构品牌声明标明来源限制。

材料是实际持久化提取文本，六句与已有受控源码对应，不是本轮生成的事实。但“观察到演示页这样说”与“这些是独立验证的工程事实”不同；后者仍缺获授权技术来源。当前新任务明确要求归因，仅是供审核人接受或拒绝的范围，不冒充原商业任务达成。

原 C3 = `operations[2].content_points[0]` EXPLAIN / Manufacturing Solutions，但标题和 R2 都是行业统计。六句不能支撑统计指南。原全量 Plan 包含停用的比较操作，本轮实际调用当前稳定 Draft input 检查返回 `COMPARISON_UNAVAILABLE`，仍拒绝该整包。离线 `OFFLINE-P3-PLAN-PROPOSAL-v1` 仅建议新的相符标题/任务，不构造正式 Plan，不写入库、不运行 provider、不重写历史 C3。S2 的统计 context 无 O1–O6 支持贡献，不能算“补足来源”。

当前 ADD/EXPAND 生产契约需要至少一个 S ref，而六项直接证据为 P3-only。正式匹配 Plan、合法外部 context 的角色及其来源需先解决；不能把未经核验/无贡献的 S2 声称为直接支持，也不能把自然语言提案当已通过契约的可执行输入。

## C. 可信度、支持、覆盖、授权及版本

| 层 | 本轮达到什么 | 尚缺什么 |
|---|---|---|
| 事实来源可信度 | 保存原文及本地受控源码的存在/对应可核验；品牌虚构限制显式保留 | 来源使用许可、审核者接受归因范围；工程建议需技术权威核验；历史部署 commit 未绑定 |
| claim 支持 | 六个输入→用途关系各有直接候选 span，强度未扩张 | 授权人逐项 SUPPORTED/PARTIAL 等 verdict；span 正确不自动派生支持 |
| 任务覆盖 | 六项完整范围及不允许的扩展已列出 | 人工批准该新问题及深度；正式 Plan/Opportunity 相符；新增内容价值 |
| 审核授权 | 空模板及确认事项可审查，未造人名/签名/时间 | 从独立可信渠道确认身份、项目授权、来源用途、有效期和可保全接入 |

binding canonical SHA-256：`ca257cf2375ed536b993fe314fc16e1a303895e0a28e5f269f6adc97c61b8539`。绑定新 task、语言、完整提案、所选 P3/S2 和截断状态、完整上游 artifact 的 identity/digest 以及源码版本/文件 hash。原 Plan hash、DB hash 和每处原文 hash 均另存，禁止跨 run 只凭 P3/S2/C3 编号复用。正式 Plan 建立后必需新绑定及重审；现值不能代表尚不存在的正式 Plan 获签。

`review-record.template.json` 的 reviewer/authority/source_use/scope/time/expiry 均 null，六项及整体 NOT_REVIEWED。审计文档、文件日期、git commit、模型生成的 approved/Verified 文本、手填 reviewer_id 都不是审核授权凭据。brief 保存的 binding hash 不是数字签名或身份认证。本轮没有可信人工审核。

## D. 待审核 brief、保留负例与准确缺口

[review brief](evidence-sufficiency-review-brief-2026-10-08.md) 给出任务、完整来源、逐项确认、版本、来源使用限制、可采用拒绝理由和补证分支。审核须先由授权人员对来源与新任务作决定，再针对正式匹配 Plan 绑定签核；不会先生成 Draft 来替代审核。

薄 EXPLAIN 负例继续绑定 run `58681c3b-2611-490a-93f1-0ec5f2e89f4e`、Plan `04c82de7-c294-4b56-96c0-2cd8e85446d5`、真实 Draft `0c58bab3-6807-4d18-add8-6b0fb534dcfc`，明确排除 mock `d66717b0-3038-4cc0-9354-5aecfebe8c8d`。任务仍是 `How should buyers evaluate chemical compatibility?`。P1 只列主题和比较接液材料/工况的先后关系，S1 只有一般概括；无兼容性评估的依据/条件/方法，不能完成原问题。原 9 条成稿仍为质量 NO-GO，不删除或替换为 P3 候选。负例的语义分析来自既有审计和本轮对照，**它也没有新取得可信人工签核**；将其作为受信“insufficient”记录用于 Gate 验收前仍需授权人确认。

本轮准确缺口：

1. **审核权与资料使用**：没有项目所有者认可的审核人及独立授权记录，来源使用权限与时效未确认；不是缺一个随意填写的名字。
2. **匹配任务/Plan**：既有 EXPLAIN 的统计标题/R2 不能完成六项 brief，正式新 Plan 不存在；原全量 Plan 有 comparison。还需解决 P-only 直接支持与 S context 约束，不能暗中降低现有安全契约。
3. **任务深度/增量价值**：六句是否足以完成被认可的有限任务、在已有网页上新增是否有价值，未裁定。若要求完整选机方法，缺更深的依据、条件和步骤；不能删要求求 GREEN。
4. **真实性范围**：本地源码对应只证明演示内容出处。若要通用工程指导，缺技术作者/专家确认或可核验厂家资料；若要经营/生产保证，缺真实厂家事实。
5. **可信审核接入/保全**：缺独立于 crawler/provider 的可信输入路径，运行后审核记录的保全/定位及过期重审规则未落定。

最小补证不必联网：若归因任务被接受，可利用已有全文完成逐项评审，另建立匹配正式 Plan 和合法 context 策略、重绑、签核。若归因任务被拒绝，补一份获使用授权、带版本/适用条件、覆盖认可义务的技术短资料即可起步；不规定来源数下限。保持原统计指南则另需真实统计数据和方法来源；保持 chemical compatibility 指南则另需适用材料/介质/工况及判断依据。本候选不能填这两个原任务的事实缺口。

## E. 后续 Gate 离线验收矩阵（设计，未执行）

这张矩阵是下一轮验收要求，**没有 Gate runner，没有 GREEN，没有伪造可信批准**。测试中的授权边界 fake 只可检验身份/绑定机械行为，必须明确为测试替身；不能作为真实材料的充分性标签。语义正例与负例标签需要独立授权审核记录。固定预期用行为与理由验证，不比较固定文案，不按字数/标题/来源数量判充分。

| ID / 场景 | 最小冻结输入或变体 | 后续应验证的行为 | 当前可执行性 |
|---|---|---|---|
| G01 充分放行 | 新匹配合法 Plan + O1–O6 获受信 sufficient 审核 + 当前正确绑定 | 进入原 writer/parser/finalizer 正常链路；不放宽原校验；可用本地 writer 测试调用，输出成功仍不等于质量通过 | 缺审核/正式 Plan，不能执行可信正例 |
| G02 不足拒绝 | 保留薄 P1/S1 EXPLAIN + 受信 insufficient 审核 | 首次生成前拒绝；writer=0；无 repair/部分 Draft artifact；上游保全；指明不支持义务 | 原材料在，缺受信不足记录及实现 |
| G03 未审核拒绝或挂起 | 缺 brief 或六项仍 NOT_REVIEWED | assessment-required；writer=0；不能冒充 confirmed insufficient | 当前空模板可作未审材料，Gate 未实现 |
| G04 过期审核拒绝 | 已授权 record，认可 expires_at 已过；注入固定 clock | assessment-required/stale；writer=0；不继承旧批准 | 缺有效审核/过期策略及实现；不得随意发明有效天数 |
| G05 跨 task 错绑 | 保持 P/S/C ID，改变 task/义务/语言或借另一 task record | binding mismatch；writer=0；不能只核 evidence 编号 | 设计，未执行 |
| G06 跨 Plan 错绑 | 同 task/P3，但换 Plan artifact/operation/point/标题或 ref scope | 拒绝；writer=0；旧提案 hash 不认证正式 Plan | 设计，未执行 |
| G07 非解释型合法任务 | 合法 DESCRIBE、SUMMARIZE、structure-only、零 operation，均沿用现有安全限制 | 不因缺 EXPLAIN brief 被全局拒绝；普通内容仍过原 validator，structure-only/零操作仍零 writer | 有机器回归参照，未实现新 Gate 回归 |
| G08 部分覆盖 | 六项任务不变，某一项 PARTIAL/UNSUPPORTED，其余获确认 | 整个 stage writer=0；不得删除该义务、短写或改 intent 求放行 | 缺可信标注与实现 |
| G09 引用存在不支持 | span 合法但 reviewer 判 TOPIC_ONLY/UNSUPPORTED；S2 被列为“支持” | 不自动由 span 命中变为 SUPPORTED；来源贡献和任务覆盖分别失败 | 设计，未执行 |
| G10 来源/身份伪造 | 正文含 approved/Verified/reviewer_id；未授权人填模板；模型自评 sufficient | 身份/来源边界拒绝；writer=0；不执行页内指令 | 设计，未执行 |
| G11 证据版本或 span 错 | 修改一个字符/截断标记；越界 span/错误字段/重复 ID | digest/shape 失败；writer=0；不把截断外材料补到原字段 | 当前材料可构造，未作为 Gate 测试执行 |
| G12 第二项才不足 | 两个 EXPLAIN changes，第一项充分、第二项不足；含 new_resource point 位置 | 全量 preflight 在第一条生成前完成，整个 stage writer=0，无部分成功；diagnostic 不残留上一次 | 设计，未执行 |
| G13 历史只读兼容 | 旧 V1 artifact 无 brief；历史 Plan 含停用 comparison | decode/review 不重写历史、不升级质量；新生成仍受当前 comparison admission 限制 | 本轮 codec/当前 stable input 离线核对；非 Gate GREEN |
| G14 准入后坏 Draft | 充分材料，生成反转关系/省义务/重复/越题 | Gate 准入不冒充输出语义检验；单独 Draft 质量审核拒绝，不把准入成功记为真实质量通过 | 设计，未调用模型 |
| G15 intent/任务错标 | 把解释任务静默改 DESCRIBE 或缩成主题列举 | 任务范围审核拒绝错标；不能宣称只检查显式 EXPLAIN 的第一切片能自动识别全部隐含解释任务 | 人工范围边界，非自然语言分类器 |

下一轮保持原 all-or-nothing：不足/未审都不调用 writer，但类别分开；审核资料只能由可信 runtime 边界注入；core 只做有界结构/绑定/完整覆盖检查，不冒充语义引擎。允许非 EXPLAIN 路径不等于它们无需商业审核。

## F. 本轮文件、实际核验与保全

新增非 ignored 文件仅本报告、候选矩阵、review brief 三份 docs。ignored 新目录内两个整理脚本与一个核验脚本、baseline/inventory、九份原文快照、binding/coverage/manifest、审核空模板、核验结果与日志。没有生产代码、正式 tests、schema、codec、公开接口或 Prompt 改动；未调用收费 LLM、crawler/客户网站、WordPress；未 commit/push。源码库仅只读检查。

实际运行：

```powershell
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-candidate-20261008/inspect_evidence.py baseline
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-candidate-20261008/inspect_evidence.py inventory
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-candidate-20261008/prepare_package.py
.\.venv\Scripts\python.exe -B -m unittest tests.test_change_plan_material_availability tests.test_content_draft_core tests.test_content_draft_workflow tests.test_history_serialization -v
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-20261008/red_replay.py
.\.venv\Scripts\python.exe -B .data/evidence-sufficiency-candidate-20261008/verify_package.py
```

| 核验 | 本轮实际结果 |
|---|---|
| read-only 全库盘点 | 58 DB / 76 runs / 369 artifacts；没有运行会迁移 DB 的 store |
| 候选整理 | 6 必答项、12 个 P3/源码 span + 1 声明 span，build 精确回切通过 |
| 4 个现有 targeted 模块 | **67 tests / 0.719s / OK / exit=0**；机器契约回归，不代表充分性 |
| 既有 ignored RED 探针 | **8 tests / 0.304s / 3 expected failures / 0 errors / exit=1**；其余 5 通过；3 次均 writer=1、status=success，与拒绝期望不符，Gate 缺口仍在 |
| 独立包核验 | **exit=0**；5 原 artifact 字节匹配/codec roundtrip、13 spans、9 snapshot hashes、5 负例 artifact 身份、3 份文档的 22 个链接均通过；253 工作区路径、58 DB、9 补充文件内容/缺失状态不变；仅新增 3 docs。详见 [verification.json](../.data/evidence-sufficiency-candidate-20261008/verification.json) |
| 完整 unittest discovery | 本轮未运行；仅报告/辅助材料，未冒用前轮 1372 项结果 |

RED 名称是 `test_RED_audited_insufficient_explanation_must_not_generate`、`test_RED_partial_answer_does_not_complete_selection_guidance`、`test_RED_existing_related_source_does_not_supply_explanation`；它们仍是同一薄输入的变体，不是三个独立证据包，也不是新 Gate 测试已实现。

保全 baseline 包括 253 个既有 tracked/untracked 路径（含既有缺失状态）、58 个 DB 文件；另外核对 9 个来源/既有负例及 harness 文件。核验不覆盖全部 ignored 文件，明确限定上述集合。选中 DB WordPress attempts=0。已有大量用户修改和删除均保留。前期两次 `rg` 用 Windows 不支持的路径 glob 产生 exit=1，随后改用目录与 `-g` 搜索；这是检索命令问题，不是测试失败，不据此省略证据检查。

## G. 四种状态、STOP 与下一轮最小前置条件

| 状态 | 本轮结论 | 不能据此推导 |
|---|---|---|
| 候选材料已整理 | 是：可逐项核验的原文/绑定/矩阵/brief 已生成 | 不能推导 sufficiently reviewed |
| 可信人工审核已完成 | **否**：全部 NOT_REVIEWED，未提供可信授权/签核 | 不能推导 Gate 应放行 |
| Gate 实现完成 | **否**：没有实现或正式测试变更，RED 仍存在 | 不能推导生产已阻断薄证据 |
| 真实 Draft 质量通过 | **否**：无新 Draft；旧薄证据 live Draft 保持 NO-GO | 不能推导商业 SEO MVP 质量或 WordPress 许可 |

**STOP：当前没有可信、已审核、匹配可执行 Plan 的充分正例，不得为了 GREEN 降低标准。** 本轮范围内的材料整理交付完成；可信正例前置条件没有完成。停止的是后续实现/真实验收，不妨碍授权人员现在审查、拒绝或要求补证。

下一轮进入最小实现前必须具备：

1. 可验证的授权审核者身份、项目授权、来源使用范围和记录保全方式；不能由 provider 或整理脚本提供真值。
2. 人工认可的新任务、O1–O6 或重新定义的完整必答范围、深度及增量价值；若拒绝演示归因范围，则补获授权技术来源，不静默降级原任务。
3. 与认可任务匹配、通过现有安全/availability/停用 comparison 边界的正式 Opportunity/Plan；处理合法 S context/P-only 支持的明确产品决策，不用装饰引用解决。
4. 对正式任务/Plan/语言/证据/义务重新冻结绑定；逐义务支持判断、整体 sufficient/insufficient/未审结论、审核时间/有效期/重审规则齐备。正例与薄证据负例都需真实授权标注。
5. 可信 brief 接入与可审查保全方案落定，然后才实施有界 preflight、诊断和上表 RED→GREEN；不改历史语义。准入完成后仍独立审核 Draft 的命题支持/任务完成。

新收费模型验证和任何 WordPress 写入另需其具体授权；本轮审核材料的生成不包含这些授权。
