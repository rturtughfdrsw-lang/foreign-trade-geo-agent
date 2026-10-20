# 真实 Draft 失败根因修复与 MVP 收敛

本轮修复 **1 个程序误判**：CL19 的 `6061-T6` 被错误拆分。原始响应重放由 **8 条拒绝变为 7 条拒绝**，Parser 仍 PASS，全文仍为 `DETERMINISTICALLY_REJECTED`，不能标为 READY。没有发现 Parser 章节路由 Bug，也没有修改 CL7、全事实覆盖或章节映射规则。

本轮仅离线操作：真实 DeepSeek、余额、WordPress、部署、生产 Gate/P1、PostgreSQL、Git 写操作、许可签发均未执行。原始 JSON、冻结材料和历史报告不改；没有补引用、改章节、补 proposal、润色或批准原模型输出。测试中的合成 reviewer/临时数据库不代表真人签核或商业交付权限。

## A. 全部实际 Validator 拒绝

以历史 `native-input.json` 重建完整 `ContentDraftInput`，包含 SiteContent、Opportunity、Plan、43 facts、版本与来源绑定、Writing Brief、候选模式。直接使用保存的原始模型字符串运行 `_parse_specification` 和 `inspect_candidate_output`。不刷新审核时间、不调用生成器、不构造新的请求或许可；这是稳定契约离线检查，不声称历史审核目前仍新鲜或可执行。

修复前 `CandidateCheck` **逐字段等于**历史 `candidate-validation.json`。完整诊断表包含 Claim ID、章节、原文、fact_refs、rule_id、原因、原始证据、来源版本/locator/偏移与分类，见 [diagnostics.md](diagnostics.md)。全部 claim 和 proposal 及来源 SHA256 见 [before.json](before.json) / [after.json](after.json)。

| rule_id / 位置 | 实际原因 | 归因 |
|---|---|---|
| `NUMERIC_CONTEXT_NOT_PRESERVED` / CL7，第1章 | 两个重量存在，但新增含数值解释句不是引用中的完整原句 | 模型违反明确契约；未证实数值/型号错误，规则保守性见 C |
| `NUMERIC_NOT_GROUNDED` / CL19，第3章 | 精确原文中的 `6061-T6` 被拆成 `6061-t`、`t6`，整词查找失败 | 程序 Bug，已修复 |
| `CUSTOMER_EVIDENCE_COVERAGE` / 文档级 | 缺 E4.F04、E4.F05、E5.F04；代码要求所有事实 ref 被引用 | 输出遗漏；全量覆盖契约也存在业务设计问题 |
| `SECTION_EVIDENCE_OUTSIDE_QUESTION` / 第2章 CL17/18 | E5 源绑定 F5/F8，与本章 F2 不相交 | 输出不守映射；主轴与型号比较语义重叠 |
| `SECTION_FACT_OUTSIDE_QUESTION` / 第2章 CL17/18 | E5.F03 绑定 F5，本章只允许 F2 事实 | 同上；不是虚构证据 |
| `SECTION_QUESTION_EVIDENCE_INCOMPLETE` / 第2章 | 实际 E1/E3/E5 ≠ 要求 E1/E3；**这里是多出 E5，不是缺证据** | 来源集合严格相等规则；报错名称不能按字面理解为遗漏 |
| `SECTION_FACT_OUTSIDE_QUESTION` / 第4章 CL25 | E3 是合法源，但 E3.F04 仅绑定 F2，本章 F4/F6 | 输出不守事实映射；测量条件映射设计疑点 |
| `SECTION_QUESTION_EVIDENCE_INCOMPLETE` / 第6章 CL38–47 | 实际 E5/E7，缺 brief 要求的 E2 | 模型未按显式集合组织；配置内容跨章重叠 |

以上是全部 8 条原生诊断。两条 claim 错误之外还有一条文档覆盖、五条章节诊断；部分诊断来自同一处错配，不能说成八个独立事实错误。没有出现未知 E refs、错误 P/S、缺 proposal、章节标题不匹配、重复 claim、预算或 snapshot 失败。确定性检查不证明所有英文推论正确。

## B. CL19 复现与最小修复

CL19 **逐字等于 E4.F01**（证据 v2，`material-and-cutting-trials`，偏移 `[234:404]`）。原文：

> SYNTHETIC / TEST ONLY: both aluminum trials use 6061-T6 blanks 120 mm by 80 mm by 30 mm and fixture A on pocket drawing A; thin walls and deep cavities remain unassessed.

根因在 `_NUMERIC_SPAN_RE`：原先完整标识符分支只允许字母开头；数字分支读到 `6061-`，unit tail 再吃掉 `T`，下一次扫描又读出 `T6`。随后整词边界检查正确拒绝这两个残片，导致合法原文误拒。

最小修改仅为该正则增加**数字开头、含字母的连字符/下划线复合 token**分支。不使用材料或行业允许列表，不引入新解析框架。现在 CL19 提取为 `6061-t6, 120 mm, 80 mm, 30 mm`。材料、型号、协议编号作为完整证据 token 匹配；真正数量仍按现有单位表达匹配，日期/纯数值范围/分数保留原路径。

这里的 token 识别不是工程语义分类器，不从字符串猜测材料性质、产品性能或适用标准。数字开头复合 token 也**没有获得新解释中免除数值上下文检查的权限**。错误主体/条件仍依靠已有完整句规则和事实/解释契约，语义推论仍待人审。

未增加“精确原文直接放行”捷径：原文继续走通用数字扫描，再走事实引用精确绑定。引用存在/范围、当前 snapshot、native Plan 图及既有来源版本/审阅边界继续检查。改变材料为 7075-T6/6061-T7、尺寸为 121 mm、型号/协议、转速/载荷/公差，或截取其他标识符的前后缀，仍被拒绝；错误引用和错误 snapshot/native binding 也被回归覆盖。现有 source/task/Plan/evidence version 与撤回审核测试保持。

先新增测试并实测 RED：5 个测试方法，3 个失败记录（6061-T6、7075-T6 两个 subtest 与真实 CL19），其余负例通过；再修改正则，单元与旧数字边界模块 15 项通过。没有删除旧断言。

## C. CL7 准确归因

原始文本：

> The 520 kg fixture points to exclusion of NCX7 on the supplied envelope, while the 180 kg fixture keeps both models conditionally in scope. Fixture clearance and dynamic loads remain unassessed. Send the fixture layout for configuration review.

| 核对项 | 证据及结论 |
|---|---|
| 520 kg 属于什么 | E5.F01：**800 × 480 mm 夹具总重**；超出 NCX7 台面宽度及拟议载荷，NCX10 待行程/接近性/动态载荷检查。不是设备自重、额定载荷或 NCX10 参数 |
| 180 kg 属于什么 | E5.F02：**400 × 250 mm 夹具总重**；在两型号名义台面及居中静载提案范围内，路径/刀具可达性/加工适用性待审 |
| 引用了什么 | E5.F01、E5.F02、E2.F01、E2.F05。前两条直接支持条件筛选结论，后两条提供两型号行程；未直接引用台面 E2.F02/F06、载荷 E2.F03/F07，但它们已在本章其他直接事实出现 |
| 数字、型号是否错 | 两个量及型号 token 均在引用中，未见跨型号借值。不能把这次拒绝写成“重量错误”或“拿了另一台设备数据” |
| 条件是否完整 | “supplied envelope”“conditionally”保留了条件性，且明确 clearance/dynamic loads 未评估；但解释句未逐项重述尺寸、居中静载、路径/刀具及 machining suitability。引用事实及本章原文保有这些条件；尚不足以确认模型作了无条件承诺 |
| 实际拒绝点 | `_validate_claim_evidence` 对 proposal 正文及元数据逐句检查：含数量的句子必须完整出现在某个所引 quote。第一句不满足，因此拒绝；不是数值找不到，也不是 Parser 路由错误 |

结论：**确定的输出契约违规，保留拒绝；没有证据确认事实数值或归属写错。** 上轮报告把“拒绝合理”直接等同于内容错误不够准确：该规则刻意比事实支持更严格，禁止即使有依据的含数量摘要。当前 Prompt 已明确要求原句/定性分析，模型未遵守；Validator 按契约工作，没有确认程序 Bug。

最小后续方案是让直接事实承载完整数量/条件，解释做有边界的定性采购判断，并明确各前提为何相关。若业务将来要允许有据的数量摘要，须另行定义何种条件保留才充分并提供正反例；本轮没有足够依据改规则，也不进行 Schema 重构。

## D. 六章映射逐项核对

Parser 接受六个原始英文标题；spec 顺序、Plan outline、section_briefs、proposal.reader_question 一致。Validator 按相同顺序消费，没有重新排序/标题猜测/行业专用路由。

| 章节 / claims | brief requirement_ids；要求来源 → 实际来源 | 核对结论 |
|---|---|---|
| 1 配置与型号 / CL1–12 | F1/F5；E2/E5 → E2/E5 | 路由通过。E2.F09（选配/F1/F8）放在 CL12，符合本章 F1；CL7 另有数量原句违规 |
| 2 主轴与试验 / CL13–18 | F2；E1/E3 → E1/E3/E5 | CL17 原样引用 E5.F03“空载转速不能排名钢去除/周期”；CL18 再引用它。语义高度相关，但 F5 映射禁止在本章使用，产生三条诊断 |
| 3 应用匹配 / CL19–24 | F3；E4 → E4 | 路由通过；CL19 程序误拒已消除。缺两型号周期事实是全文覆盖/内容缺口，不是本章来源缺失 |
| 4 测量验收 / CL25–31 | F4/F6；E3/E4/E6 → 相同 | CL25 的 E3.F04 是热身30 min、冷却、20 C环境及非热漂移测试限制；语义关联 F4 的方法/环境，但 fact map 只有 F2，产生一条 fact 级诊断 |
| 5 采购协议 / CL32–37 | F6；E6 → E6 | 路由通过；与第4章共享 F6/E6，分别处理测量判据与下单责任，本身允许重叠 |
| 6 交付服务 / CL38–47 | F7/F8；E2/E5/E7 → E5/E7 | E2.F09 已在第1章，未在本章引用；E5.F05、E7 仍覆盖 F7/F8，因此缺的是强制源 E2，不是整个 F8 未回答 |

分类：模型没有遵循冻结的硬映射；但第2章的型号/主轴比较、第4章的测量环境、第1/6章的选配，以及第4/5章验收确有业务重叠。不能把这些自然放置一律定为“内容放错了”或事实造假。`supporting_evidence` 精确相等还会把多出的相关证据报成 INCOMPLETE，属于契约/诊断语义疑点，未确认执行 Bug。

必要 Prompt 改进建议：针对每章列出当前**合法 fact_refs**，说明来源合法不代表该源所有事实合法；用本案 CL17/CL25 展示事实映射与主题语义不同；解释来源集合必须相等，以及跨章共享源也须在相应章真实使用。不要靠堆无关 refs 达标。若这些例子在业务上应允许跨章，最小候选是经审阅调整事实的 requirement 归属/章节 brief，或明确“必须来源”与“允许补充来源”的含义；本轮不改历史映射，不重设计 Planning，也不硬编码 CNC 标题。

## E. 三条未引用事实及覆盖规则

| fact_ref | 原始事实要点 | 业务意义与义务 |
|---|---|---|
| E4.F04，F3/F4 | NCX7 铝件 drawing A，三次均值42 s，不含装卸；小样本不建立通用产能优势 | 本次 F3 明确包含 cutting cycle，不能只列刀具/材料却不说明已有周期及局限 |
| E4.F05，F3/F4 | NCX10 同图铝件，三次均值40 s，不含装卸，同样无通用产能结论 | 与上一条构成有限可比的记录；不能以两秒差异作持续节拍、统计优势或采购排名 |
| E5.F04，F5 | 只有铝件 drawing A 有两型号配对试验；小样本不支持显著性、耐久性或全寿命成本排名 | 限制跨型号比较范围，对 F5 条件筛选重要；不宜把钢件/可选配置也视为配对验证 |

完整原文、版本、偏移见诊断表。Plan 强制的是 F3/F4/F5 采购问题，不逐条枚举这三个 fact ID 为独立义务；**代码额外将全部43个 refs 设为必须使用**。E4.F04/F05 对本案 cutting-cycle 回答尤其重要；E5.F04 的部分限制在其他句有相近表达，但配对试验范围没有清楚交代。三者都不是明显无关的可选资料；遗漏损害完整性/决策价值，尚未直接制造一个错误周期断言。

机械全量覆盖规则确实存在于 `draft_candidate_review.inspect_specification` 和 `content_draft.finalize_draft_item`；构造 `DraftItem` 时也保有相同不变量。不是报告臆测。实际 Prompt 的 `customer_coverage_rule` 同样要求全部 refs 作为直接事实或真实解释前提，上一轮 Prompt 修复报告和 Mock 验收也明确保留该约束。因此不能为了本样本通过就删除它。

现有材料能证明“实现/冻结契约如此”，不能证明“所有未来客户资料都必须用于一篇文章”是已批准的通用业务需求。它与按搜索意图选择相关事实存在张力，也可能诱导列资料或挂无关前提。**本轮记录为契约收敛议题，不放松强制证据义务。** 下一轮可以先明确本篇必答问题及其相关证据，保持必要条件/采购限制，不能把 43/43 本身当质量目标。

## F. 本轮实际文件增量

| 文件 | 必要性 |
|---|---|
| `src/foreign_trade_geo_agent/core/content_draft.py` | 仅修改 `_NUMERIC_SPAN_RE` 的完整 token 分支及注释；保留该文件此前所有未提交改动 |
| `tests/test_flash_draft_replay.py` | 5 个 focused 测试：完整标识符、错误数值/型号/协议/材料、真实原文、引用及 snapshot/native 绑定；测试变体只在内存构造，不改历史 |
| 本报告目录 `replay.py`、before/after/diff JSON、diagnostics、测试日志与完整性结果 | 可复查的离线重放、47条逐 claim 差异、全部拒绝归因和验证证据；不是新冻结/权限框架 |

没有修改 adapter、Prompt、Planning、review、schema、数据库设计或生产边界。其余已有工作保留。

## G. 实际验证

先执行 RED，再执行单元/数字模块、相关 Draft/Validator 集成，最后历史原样回放及一次完整 discover。未每次修改运行全套。命令/结果：

| 层级 | 实测 |
|---|---|
| 新回归 RED，`unittest tests.test_flash_draft_replay -v` | 5方法，3失败记录，预期失败；[日志](tests-red.txt) |
| 单元/数字模块，`tests.test_flash_draft_replay tests.test_content_draft_numeric_boundaries` | 15项，0.047s，OK，exit 0；[日志](tests-unit.txt) |
| 相关模块/集成 | 121项，34.732s，OK，exit 0；[日志](tests-targeted.txt) |
| 原始历史响应 | before 与历史结果相等；after 仅移除 CL19；7拒绝保留 |
| 完整回归 | **1892项，434.350s，OK，exit 0，0失败/错误**；[日志](tests-full.txt) |
| Web 启动配置 HTTP smoke | 临时离线目录四页面200；提交合成E1/recheck后仍禁生成，Mock writer=0；[结果](web-smoke.json)；本轮未操作浏览器 |

保留既有 Starlette/httpx 弃用提示和 asyncio 慢任务诊断；测试日志末尾的 launcher 端口占用/启动文字来自对应测试桩，不是本轮部署。未删除旧测试或有效断言。最终核对 1883 个历史 docs 文件全部不变；174个历史源码中只有本次数值正则所在文件变化，逆向移除该局部补丁后 SHA256 与历史源码完全一致，证明该文件既有未提交内容保留。证据：[verification.json](verification.json)、[本轮独立源码补丁](source-change.patch)。

相关模块命令：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_content_draft_core tests.test_content_draft_workflow tests.test_deepseek_content_draft_adapter tests.test_content_draft_block_budget tests.test_autonomous_interpretation tests.test_evidence_backed_article tests.test_draft_prompt_contract tests.test_draft_prompt_contract_acceptance tests.test_draft_revalidation -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
```

## H. 历史回放前后差异

[diff.json](diff.json) 逐条记录47个 claim 结果：只有 CL19 从 `NUMERIC_NOT_GROUNDED` 变为无 claim 级错误；CL7 不变，其他45条均保持无 claim 级错误。文档级覆盖与五条章节诊断不变。没有新拒绝；绑定摘要不变，六条 proposal 未改变、未获批准。

原始 response SHA256：`9f69992de2e7a9d0c16a66893a07b72dd39cbb8fe5e538f47ed10378383398db`。

原始模型 JSON SHA256：`04c311ca5fc7a85833f3662dd11d21a97aae00cc95a40afe2604dd5e4ba202e0`。

已执行过的 request `8fd2b8834c9aa50f4ebaeba6229b4a9b01b59d033effa8637cce5ed223428431` 没有重新冻结、授权或发送。历史 docs 完整性以会话开始的逐文件 SHA256 检查，不更新旧 manifest 迎合新代码。

## I. 剩余模型错误与文章质量

确定存在的是 CL7 数量句不守契约、三事实未引用、章节证据映射不守契约。后两类既有输出问题，也受严格契约影响；不把所有拒绝笼统称为事实错误。

文章仍以40条精确证据句为主体，六条解释约236词，总正文约1274词（历史统一正则口径）。CL7 基本重复资料已有筛选结论，CL18 概括空载/铭牌信息，缺 drawing A 周期比较；格式合格和有 proposal 不代表采购分析充分。CL47 的询盘资料 CTA 比旧轮更具体，值得保留为质量改进证据。

仍须人工核对的推论疑点：CL31 将 E3.F05/F06 铝试件及 E4.F07 钢试件都称为接近 E6.F03 的 drawing A 标准，未分清方法A/B、材料和适用范围；CL46 正文/reasoning 将交付、培训、support、warranty 整体条件化于签署配置，而明确的 signed-configuration 触发仅见 dispatch。CL18 的 nameplate power = bench conditions 表述也过宽。这些是对原文的语义预审疑点，不能冒充确定性 Validator 新诊断或已确认工程结论；本轮未增加规则去强行判定。

商业可用性仍受采购分析浅、试验可比性未讲清、漏关键周期/局限、未完成人审影响。修复 CL19 不改变这一结论。

## J. MVP 闭环真实状态与最短路径

以下基于当前代码和已存验收材料；本轮不执行新的 live。历史真实模型调用使用合成客户资料，不等于真实客户产品/搜索效果验收。

| 必要业务步骤 | 当前状态 | 真正剩余缺口 |
|---|---|---|
| 1 输入客户网站 | 通用 `/live` URL/目标入口已实现；`/mvp` 仅查询 NovaCNC 保存任务 | 任意分析 run 到同一补资料/写作工作台尚未打通；不能把 URL 查询框当抓取按钮 |
| 2 抓取、SEO审计 | 通用 crawler/Packet/Audit 与独立 audit CLI 已实现；本次可核查验收是本地 fixture/Mock | 真实授权客户站点的静态提取/内容覆盖验收未建立；不能推定各站均可用 |
| 3 行业研究、内容机会 | 固定 workflow、provider ports/adapters、持久化及 Live composition 已实现；有 Mock 集成测试 | 本次证据中没有“真实客户网站+真实搜索+有效内容机会”完整验收，真实业务 relevance 待验证 |
| 4 合适内容计划 | 原生六章/brief/问题/义务重规划已实现并 Mock 验收；真实 Draft 请求确实消费它们 | 六章来自显式合成 scope；未证明能对其他行业独立形成有效问题地图；本案事实归属重叠需收敛 |
| 5 缺资料提示补充 | PlanningEvidence/Intake/Web 保存、缺口、重核对、陈旧拒绝已实现并 Mock 验收 | 真实客户材料的充分性与使用范围尚无验收；默认无 reviewer，不会自动放行 |
| 6 资料充分后生成文章 | **有真实调用验收**：10/11 单E短文 HTTP/Parser/Finalizer/SQLite/Web成功；**已知失败**：本轮六章真实Flash仍拒绝，质量未达标 | 稳定生成有用长文的能力尚未验证；默认 Draft adapter 仍只接受显式 MockTransport，生产 admission 保持阻断 |
| 7 事实检查、保留待审候选 | 数字/来源/版本契约及候选保存已实现；本次真实拒绝候选完整留存，离线可重放；六章候选 Web/语义决定链有 Mock 验收 | 确定性检查不证明语义；真人人审还未完成，不应继续扩建检查平台代替文章质量 |
| 8 Web 阅读、修改、确认 | **已有实际浏览器操作验收**：历史真实模型短文的阅读/来源展开/编辑/追加版本/本地完成/导出/重启恢复；新解释候选可查看原 JSON、逐条来源并保存修订，主要 Mock 验收 | 通用客户 run 导入及自然正文编辑体验不统一；复杂改写仍待重新核验；本地确认不是商业签核 |

证据入口：[只读审计验收](../readonly-seo-audit-acceptance-2026-10-10/report.md)、[范围/证据Mock验收](../seo-evidence-backed-mvp-2026-10-11.md)、[候选实现验收](../seo-autonomous-interpretation-2026-10-11.md)、[真实Web短文实验](../seo-web-deepseek-live-2026-10-11/report.md)、[真实候选质量实验](../seo-flash-contract-quality-live-2026-10-12/report.md)、[Web实际修订验收](../seo-article-review-mvp-2026-10-10.md)。旧报告中的“未实现自主候选”等结论须按后续实现更新，不能照抄为当前状态。

必要收敛只有三类：先得到一篇有用且可核查的真实模型待审长文；再把已有通用分析 run 与同一任务/Plan/补资料/候选工作台接通，移除演示入口的单fixture绑定；用第二个行业/站点及对应可信资料验证可迁移性与 Web 人审体验。正式商业使用还需要明确客户资料用途及人工确认的适用授权；这不能从 TEST-only 演示推导，但不要求为本地演示先建设多租户/签名平台。

WordPress自动发布、多租户、PostgreSQL迁移、复杂身份/权限/审核平台、GEO扩展、更多评分/冻结设施均可延期，不是上述演示闭环前置条件。现有生产阻断如需调整，必须是另行明确范围的任务；本轮不绕过。

现有 Web 可以这样验证**离线阅读/修改/本地确认**，不改变生产权限（新目录；已有目录不覆盖）：

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_web_mvp --output-dir .data/seo-mvp-root-cause-demo
.\.venv\Scripts\python.exe -m scripts.web_generation_demo --directory .data/seo-mvp-root-cause-demo --port 8025
```

打开 `http://127.0.0.1:8025/mvp` → `/mvp/evidence` → `/mvp/article`。文章是预生成 TEST-only 候选，不是这次补资料后真实生成。可阅读、修改、保存版本、填写本地结论、导出；这些不授予任何生产权限。`web.__main__` 没有 `--mvp-dir` CLI 参数，默认目录是 `.data/seo-mvp`；上述现有 Mock 启动器可选择独立目录，避免覆盖旧工作台。

`scripts.web_generation_demo --directory <新目录> --port 8025` 会装配 Mock writer，但当前 main **没有注入 `scope_reviewer`**，而 `require_generation_scope` 要求当前范围审阅。因此不能把 README 的按钮流程宣传为开箱即用的全闭环。已有 `tests.test_web_generation.WebGenerationTests.test_new_generation_persists_recovers_citations_and_edits` 使用显式 TEST scope reviewer + MockTransport 在 HTTP 测试客户端验证补资料→重核对→生成→来源→编辑；完整回归包含该用例。它证明现有工程子链可用，不证明默认启动器、任意企业或真实模型质量通过。本轮只记录入口限制，不顺手新增 reviewer 或许可。

**下一步最值得做的一件事：针对本次真实失败做一次小范围 Prompt 改进与受控质量对照。** 重点是把量及完整条件留在事实中、解释围绕实际采购选择；按合法事实映射安排章节；明确试验可比范围与周期局限；减少原文资料清单。先离线用实际 Parser/Validator 检查改进契约，再由用户决定是否授权新的请求或跨模型对照，不能复用本次已消费 request。验收对象是一篇可在现有 Web 阅读、修改、核查的有用英文待审文章，而不是更高测试数量。这直接消除当前 MVP 最大的不确定性——真实模型能否产出值得客户审核的文章；得到这项证据后再接通通用入口，避免继续围绕失败文稿扩建 Validator。

本轮完成后停止，等待项目所有者决定。
