# 原生 SEO 文章范围与多事实解释：离线交付报告

本轮的 **READY 仅指有明确范围、已审阅事实和已审阅解释的离线契约**。E1-only 完整采购指南为 BLOCKED；七份合成资料的完整输入为 READY。模型自主产生新采购推论的能力仍为 **BLOCKED，阻断层为 Evidence contract**。没有把 Mock 成功宣称为真实 DeepSeek 写作质量，也没有把语义审阅替换成自动评分。

1. **文章目标、Plan、Evidence 的数据流**

   既有 `EndToEndRunRequest.research_question` 经运行输入保存为 `seo_goal`；`PlanningEvidenceWorkflow.register` 将其绑定到 `EvidenceTask.goal`。既有 Crawl → Audit / Research → Opportunity → ChangePlan 链保持不变。Opportunity 表示选定主题、操作与 P/S/A 引用，本来没有独立搜索意图字段；Plan 的 `resource_purpose` 是资源用途，`EXPLAIN` 是内容点深度，二者均不能代替文章类型或完整读者问题。

   现在由原生 `EvidenceTask` 显式承载范围；`CustomerPlanningContext` 将范围、证据义务、完整客户资料交给现有 ChangePlanWorkflow。原生 Parser / Validator / Finalizer 生成带章节 brief 的同一份 Plan。Intake 对当前快照审阅，`reviewed_draft_input` 将审阅过的原文 span 和解释投影为原生 `ContentDraftInput`。Draft admission 仍独立于证据充分性；Mock 执行前后均重新检查范围与解释审阅。最终仍经过既有 Draft Validator / Finalizer → SQLite → Review → Markdown / Web。

   | 用户关心的问题 | 原生字段 |
   |---|---|
   | 客户要解决什么问题 | `EvidenceTask.goal`、`reader_problem` |
   | 搜索意图 | `EvidenceTask.search_intent` → `ArticleWritingBrief.search_intent` |
   | 文章类型 | `EvidenceTask.article_type` → `ArticleWritingBrief.article_type` |
   | 必须回答什么 | `ArticleSectionBrief.reader_question`、`explanation_goal` |
   | 需要什么证据 | `EvidenceRequirement.required_fact / intended_use`、章节 `requirement_ids` |
   | 实际有什么支持 | 章节 `supporting_evidence` → 审阅 span → `DraftCustomerFact.fact_ref / requirement_ids` |

   范围问题和义务需显式提供并审阅；本轮没有增加根据目标字符串自动理解采购范围的分类器。没有 buyer guide / NovaCNC / CNC 关键词分支。未知范围或缺失审阅不能自动成为充分证据。

2. **新增或修改的原生结构与文件**

   没有第二套 Planner、Evidence、Draft 或 Quality 系统，也没有数据库 schema 迁移或新依赖。

   | 原生位置 | 本轮增量 |
   |---|---|
   | `core/change_plan.py` | `ArticleSectionBrief`；同一 `NewResourceSpecification / NewResourceSpec.section_briefs`；按显式范围形成 2–6 章；保护 Intake 必须保留的内容点免遭预算裁剪 |
   | `core/evidence_intake.py` | Task 范围字段；`ReviewedInterpretation`；解释 premise 必须属于同一当前审阅的 SUPPORTED spans；历史默认值 digest 兼容 |
   | `core/draft_customer_evidence.py` | 每份文档多个精确 `DraftCustomerFact`；`DraftInterpretation`；文档身份、完整原文、SHA256、偏移、事实与义务映射保留 |
   | `core/content_draft.py` | `EVIDENCE_BASED_INTERPRETATION` 与独立 support kind；既有 Finalizer 内最小质量检查；不放松数字、引用、预算或宣传限制 |
   | `core/content_draft_review.py`、`core/draft_revalidation.py` | Review 显示质量缺口；本地重新核验支持事实级引用与偏移 |
   | `workflows/change_plan.py`、`workflows/evidence_intake.py`、`workflows/planning_evidence.py` | 复用原生重规划；同一任务范围下派生章节；无损审阅投影；生成前拒绝缺少解释或无法容纳的 brief |
   | `adapters/deepseek_content_draft.py`、`adapters/retained_deepseek.py` | 对齐 E 解释规则；显式且有界的请求上限；旧 16,000-byte 默认不变，丰富 Mock 输入受现有原生 envelope 限制 |
   | `storage/serialization.py` | 新可选字段严格编解码；旧 V1 默认字段不进入原始编码 / digest |
   | `reporting/content_draft_review.py`、`web/generation.py`、`web/templates/mvp.html`、`web/templates/mvp_scope.html` | 多事实 Markdown / Web 来源映射、章节问题和限制、质量预检；当前审阅撤回即阻止再次生成 |
   | `scripts/accept_rich_buyer_guide.py` | 仅增加可选 scope / reviewer 注入，保留既有诊断回归 |
   | `scripts/accept_evidence_backed_article.py`、`tests/test_evidence_backed_article.py` | 新正反离线验收及负面测试 |
   | `tests/test_seo_e_only.py` | 独立重构旧 V1 无新增默认字段的形状，保留旧 digest 相等断言并增加默认字段未写入的断言 |

3. **低资料案例**

   最终验收中的 E1 原文保持历史字节和来源身份不变。对于完整采购范围，只有卸载主轴转速记录，F1–F8 均未完整满足，输出 BLOCKED，writer 调用数为 0。F2 是部分有材料但义务未完整满足，不能把已有转速当成所有性能证据。

   明确要求补充：型号尺寸 / 载荷 / 配置；主轴功率定义与加载条件；材料、工件、刀具、冷却和加工周期；测量方法 / 样本 / 条件 / 限制；可核验型号差异；RFQ 和验收责任 / 标准；交付、培训、服务提案；版本有效性和选配适用范围。旧 E1-only 控制案例也保留，仍报告 F2–F5 缺口。

4. **丰富资料案例**

   七份 SYNTHETIC 文档、43 条独立事实全部进入 writer material，未压缩成七条文档摘要。每条 span 可回到原文偏移和 SHA256，且保留对应义务。输入包含正确 goal、reader problem、search intent、article type、原生章节 brief、writing brief 和事实级 evidence map。

   一次 MockTransport 请求经过 Parser、Validator、Finalizer、SQLite 保存 / 独立重读、Markdown 与 Web，全部通过；重复提交未重发，审阅者或解释许可撤回后不可生成。请求大小 **33,814 bytes**，SHA256 为 `72242073e52d3079390328bc2e1fa6ea06df096c4648d14aaac94cb0e4649333`。没有真实模型或 WordPress 请求。

   43 条事实全部可见 / 可引用，并不表示正文逐字复制 43 条。Mock 正文采用六条直接事实、六条多事实解释和一条采购 CTA；43 条事实均成为直接引用或解释 premise。

5. **Planning 是否改善**

   原生 Parser 不再把所有新资源固定为两个章节。对于本案例，当前明确读者问题通过现有重规划形成六章：配置与型号限制、主轴 / 试验证据、应用匹配、测量与验收、采购责任、交付与服务。每章有问题、解释目标、义务、可用 E 来源、限制和行动。

   章节数量仍受既有六章上限约束，保留内容点 EXPLAIN 深度和原始目标 / P/S/A 图。支持不同主题的结构化任务，没有行业词硬编码。该能力是基于显式范围的原生结构形成与分配；不是已经证明模型能从一句宽泛目标独立产生完整采购问题地图。缺少显式地图时仍需范围审阅。

6. **Evidence-backed explanation 是否实现**

   实现的是受审阅约束的版本：直接事实必须精确引用一个事实；解释必须引用全部多个 premise，并与当前审阅明确批准的解释一致；没有证据或未经批准的新推论拒绝。解释同时保留未知 / 限制和具体采购行动。更改措辞、删掉 premise、错引事实、将推论伪装成直接事实、混用 P/S，均不能通过。

   重要限制：目前不是开放式模型推理。模型可以选用已审阅解释并组织事实，但不能自行写新解释后仅凭引用列表自动获准。这样没有用“解释”标签放松 Validator，也没有声称结构检查能证明语义真实性。

7. **Draft 是否承载多个事实解释**

   是。同一 claim 的 `customer_refs` 允许绑定 2–20 个事实级引用，support kind 为 `CUSTOMER_REVIEWED_INTERPRETATION`；直接事实仍是单引用和 `CUSTOMER_REVIEWED_QUOTE`。最多八份文档、64 条事实、12 个解释选项，完整文档总字符预算不变；输出仍受既有八块 / 十六条陈述 / 3,000 tokens 上限约束。

   生成前检查有无每章可用解释、审阅 freshness、完整义务和保守输出可行性。超预算拒绝，不静默删事实、删问题或裁剪 brief。结构化文章不能把未经审阅的假设换成 S 背景或 editorial 类型逃过解释边界。

8. **Mock 文章质量分析**

   相比旧参数摘录，正文加入了条件化型号筛选、卸载参数与切削能力区分、试验代表性、测量不确定性与验收约定、商业条款确认，并以提交图纸 / 材料 / 工装 / 周期 / 验收优先级的 CTA 结束。没有靠增长长度或复制 S 背景填充正文。

   最小预检检查章节与 Plan 一致、问题所需义务 / 来源覆盖、直接事实与解释并存、解释内限制和行动、末尾 CTA、重复与预算等明显问题。缺 CTA、错章节解释、参数堆砌都会失败；已审阅选项里的错误新数字仍受独立数字规则拒绝。

   Mock 正文陈述合计 **353 个空格分词**（不含标题和引用清单），有六条直接事实、六条解释、一条 CTA，S 背景陈述为零。43 个引用被覆盖不等于对 43 条 premise 都做了有用分析。

   Mock 只有脚本提供的六条解释，不能证明真实模型会形成深度采购分析；每章目前仍是简短的事实示例和决策提醒。预检也不能判断分析是否足够深入或购买建议是否适合实际客户。人工审核仍必需，不能将它验收为成熟完整的采购指南。

9. **实际测试与验证**

   最终 targeted：68 tests，PASS（`tests.test_evidence_backed_article`、`tests.test_seo_e_only`、`tests.test_rich_buyer_guide`、`tests.test_intake_native_planning`）。其中新模块包含 13 个测试。

   最终全套：**1,839 tests，674.492s，OK，退出码 0**。命令为 `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q`。原生 P1 / first-party、历史编解码、Web 与 WordPress Mock 回归均包含在这次完整运行中；没有执行真实 WordPress。

   初始完整回归实际结果为 1,837 tests、1 failure / 1 error，分别对应旧 digest 测试期望和数字诊断事实级引用；修复后才运行上述最终完整回归。另一次迭代定向运行 176 tests 曾有 1 failure（旧 digest 测试），同样没有隐瞒或算作通过。现有 Starlette / httpx 弃用提示仍存在。

   迭代中实际发现并修复：重规划裁剪丢失必要内容点；旧 16KB 请求下新增说明超预算；数字诊断未接受事实级引用；旧 digest 测试期望没有排除新增默认字段。旧断言保留，更新独立历史形状重建，并验证旧历史文件哈希不变。初始回归的失败会保留在验证记录中。

10. **下一次真实 DeepSeek Flash 实验**

   **已审阅范围 + 已审阅多事实解释选项** 的写作契约实验输入为 READY；正式实验仍需新鲜审阅、重新绑定 / 冻结确切请求，以及另一次明确授权与隔离执行准备。本轮没有发放 live permit、读取余额、修改 P1 或 PostgreSQL、写 WordPress、部署、提交或推送 Git。

   **针对本次“模型依据充分资料自主写出采购分析”的实际目标，下一次真实 Flash 质量实验仍为 BLOCKED：Evidence contract**，因为解释正文仍必须来自预先批准的选项，无法测试模型独立产生新推论的能力。如果仅给一句宽泛目标且要求系统自主补出完整采购问题地图，当前也依赖显式范围审阅，不能宣称自动 Planning 已完成。这些阻断不来自本案例的数据量、SQLite、Markdown 或 Web。按要求到此停止，不继续扩大为新的推理审查 / 评分系统。

验收文件：`docs/seo-evidence-backed-mvp-final-2026-10-11/readiness.json`；完整输入、Plan、事实映射、请求和 Mock 文章位于其 `B-rich-evidence/`。它们全是合成 / 离线证据，不是客户批准或生产授权。

验证日志和机器可读记录：`docs/seo-evidence-backed-mvp-verification-2026-10-11/`。自动审批检查拒绝了清理本轮中间验收目录的删除操作，提示仅为 `blocked by policy`；这些目录已保留，最终验收以名称含 `mvp-final` 的目录为准。
