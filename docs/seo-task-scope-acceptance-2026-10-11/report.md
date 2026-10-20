# 文章目标、证据与规划匹配：根因与最小离线验收

日期：2026-10-11，Asia/Shanghai。结论：当前问题由**目标与标题错位、过窄的资料义务、固定规划策略、受限背景与不充分的写作要求/审核**共同造成，不能归结为“换模型”或“仅证据太少”。本轮复用现有 Intake / Planning 完成两条业务路径的离线验收，**没有修改生产逻辑**。

本轮新增 `scripts/accept_seo_task_scope.py`、`tests/test_seo_task_scope_acceptance.py` 及本目录。没有调用 DeepSeek、查询余额、执行 WordPress 写入或再次运行模型对比；没有编辑生产 Gate、P1、PostgreSQL，没有部署或 Git 写操作。保留既有未提交改动。SYNTHETIC 材料、模拟确认和结构检查均不是工程事实、商业质量证明、人类签核或执行权限。

## 检查的原始材料

- [冻结 snapshot](../seo-model-comparison-preflight-2026-10-11/baseline/snapshot.json)：sha256 `c9edae44515a6a54e6d74873a45f8298545808ffce81cf62e44f6a57d50e6963`，包含原任务、Opportunity、Plan、Intake、P/S 和 E1 原文及来源；本轮只读。
- [历史 Flash request](../seo-model-comparison-preflight-2026-10-11/baseline/request.json)、[Pro request](../seo-model-comparison-live-2026-10-11/attempt/request.json)：检查冻结 system/user messages、预算和 Draft 输入，不执行请求。
- [Flash 输出](../seo-model-comparison-preflight-2026-10-11/baseline/model-output.txt) / [文章](../seo-model-comparison-preflight-2026-10-11/baseline/article-body.md)、[Pro 输出](../seo-model-comparison-live-2026-10-11/attempt/model-output.txt) / [文章](../seo-model-comparison-live-2026-10-11/attempt/article-body.md)，以及既有 [原生结果和评分报告](../seo-model-comparison-live-2026-10-11/report.md)。153/170 词和解释深度 1/4 是既有结果，本轮没有重新评分。

## 根因及证据矩阵

| 问题 | 具体输入/代码依据 | 能确认的结论 / 边界 |
| --- | --- | --- |
| 为什么宽泛 buyer guide 能进入生成？ | 原 `task.goal` 是 `create one English resource explaining spindle performance for export buyers`，Opportunity R1.topic 也是 `spindle performance`；Plan 标题却为 `NovaCNC machining center buyer guide`，scope_consents=[]。[EOnlyPlan](../../scripts/demo_seo_e_only.py:69) 复用 [TITLE](../../scripts/demo_seo_article.py:46) | 演示 fixture 的窄目标沿用了宽标题；不是已有完整指南目标获得了完整证据审核。旧任务未记录范围变更确认。当前模板匹配仍接受这个原图，不能将其解释为搜索意图匹配成功 |
| 标题为何通过原生检查？ | [proposed_label_is_grounded](../../src/foreign_trade_geo_agent/core/change_plan.py:2622) 按非结构词校验标题；buyer/guide 等是 proposal words；旧 S1 本身包含完整标题。[资源 Finalizer](../../src/foreign_trade_geo_agent/core/change_plan.py:3593) 校验标题、提纲及内容点 grounding | 词汇存在和结构合法不证明标题承诺与证据/采购意图一致；没有自动的完整指南语义检测 |
| Evidence Sufficiency 到底核对什么？ | 原 Intake requirements 只有 F1：参数、型号、运行方式、条件、限制；[check](../../src/foreign_trade_geo_agent/workflows/evidence_intake.py:172) 逐项检查对应材料、人工 verdict、native binding；[validate_assessment](../../src/foreign_trade_geo_agent/core/evidence_intake.py:568) 校验 digest、时效、全部 requirement IDs 和原文 spans | 只会覆盖已登记的义务；不能发现未登记的其他采购问题。协议 [EvidenceSemanticReviewer](../../src/foreign_trade_geo_agent/core/evidence_intake.py:476) 明确要求人工审核深度、适用性、权威性和冲突，但没有生产实现 |
| 旧“通过”是否来自生产语义 Gate？ | [SyntheticEOnlyReviewer](../../scripts/demo_seo_e_only.py:82) 是对固定 E1/F1 的脚本 verdict。[MockArticleExecutor.input_for](../../src/foreign_trade_geo_agent/web/generation.py:71) 只匹配固定 task/native graph/文档 bytes/requirements；输出 `TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF` | 没有可信人类签核，也没有把宽指南语义充分性判为真。另一个 [EvidenceSufficiencyPreflight](../../src/foreign_trade_geo_agent/workflows/evidence_sufficiency.py:11) 是限定 P-only attributed excerpt 的独立离线分支，校验签名/版本/义务/范围，不是这次 E-only 文章的采购指南判断器。生产 Draft 仍拒绝 |
| 为什么只有一个点？ | [EOnlyPlan](../../scripts/demo_seo_e_only.py:69) 显式只选 `spindle performance`；Intake 也仅 F1。生产 [MAX_CONTENT_POINTS_PER_OPERATION](../../src/foreign_trade_geo_agent/core/change_plan.py:67)=5 | 不是整个系统只能写一个点，也不能据单样本判断模型不会规划；输入根本没给出采购问题链 |
| 为什么固定两节？ | [deterministic_outline_headings_for](../../src/foreign_trade_geo_agent/core/change_plan.py:1050) 取前 MIN_OUTLINE_HEADINGS=2；[parser](../../src/foreign_trade_geo_agent/workflows/change_plan.py:1280) 使用这两个值；[outline candidate builder](../../src/foreign_trade_geo_agent/core/change_plan.py:2875) 从 S 标题/片段提取 | 两节是原生确定性策略，不是模型能力上限。本轮仍两节，但可以覆盖五个问题；分节数量不等于解释深度。另有每 R 12 个候选、按来源交错排列的上限，长单源末尾的问题可能进入不了候选池 |
| 什么事实不足？ | P1 只是主题介绍且页标题为 VMC-DEMO；E1 却只涉及 NCX7 的 7200 rpm continuous、20 C、NOVA-TEST-7、unloaded bench 和排除项；旧 S1 为 example 域合成背景、UNVERIFIED_SEARCH_RESULT，content_truncated=true，750 字符，末尾 `tooling a` | 不能据此判断 NCX7 实际工况适用性、切削负载性能、加工公差、采购验收、认证和服务承诺；不能认为 VMC-DEMO 页名证明 NCX7 配置。证据薄是真问题，但不是全部根因 |
| Prompt 是否诱导复制或泛泛罗列？ | [EXTERNAL RULE](../../src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py:58) 已要求简明改写、禁止长复制；[末句](../../src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py:61) 又要求每条 short / lexically grounded。固定两节、单 EXPLAIN 点，没有事实→意义→决策动作或必需 CTA 约定。E 规则强制完整原句 | 没有明确命令复制 S1；短陈述与词汇 grounding 可能鼓励保守摘句，但仅凭现有样本不能证明因果。输出确有多条 S1 原句；现有原生校验没有背景相似度、解释深度、采购覆盖或 CTA 质量判定。E 原句复制则是必要的安全要求 |
| 是输出长度预算截断吗？ | 冻结请求 max_tokens=3000；既有输出分别只有 611/733 completion tokens，3/4 blocks、10/9 claims；许可上限 8 blocks/16 claims | 没有输出上限直接截断的证据；增加最低字数、标题数或换模型没有在本轮获得依据。未来完整指南能否装入当前预算仍需按确认问题和限定检查 |

原生 Parser/Validator/Finalizer PASS 表示格式、引用、数值及支持边界等技术规则通过。它不证明 E1 真实、S1 权威、解释正确、任务承诺充分兑现或客户可交付；本轮维持这些区别。

## 路径一：保留完整采购指南

先请客户确认实际读者、型号/选件、应用与采购决策问题，核对标题/goal/Opportunity/Plan 一致，再为这些问题登记资料义务。具体材料清单、适用条件和写作用途见 [writing-brief.md](writing-brief.md)。核心请求为：

1. 拟加工材料、零件几何/尺寸、工况、刀具与装夹、循环和目标；决定是否需要进一步索取行程/轴配置、扭矩/功率等参数。
2. 对应型号/配置的技术参数及原始测试依据：方法完整内容、负载/温度/运行条件、结果和排除项；额定值不能自动变成实际切削能力。
3. 与目标相关的精度/试件测试、测量方法、环境、结果与适用限制；明确各指标的测量对象。
4. 买卖双方拟议/已确认的验收依据、代表性工况、判定方法与责任，未确认处明确标注。
5. 文件原文、签发责任人、版本、日期、型号与配置范围；只在文章涉及相应主张时索取认证和售后/质保条款。

这些是**待客户确认的案例资料需求**，不是自动填参数的字段，也不是所有采购都必需的通用模板。客户不能用提交 JSON 自行赋予材料权威或审核状态。

本轮 [guide-requirements.json](guide-requirements.json) 对应新合成 Plan 的五个内容点，并通过既有 Intake 输出 [02-customer-request.json](02-customer-request.json)。它不能直接套用旧单内容点 Plan；旧已登记 F1 任务不允许原地改写 requirements。若实际目标扩大为指南，应先形成新 planning task，再用现有 `evidence open/submit/recheck/review` 绑定新 run / Plan artifact 和义务。未开发第二个 Intake 或自动语义分类器。

## 路径二：现有 E1 支持的明确范围

提案标题：**Spindle test conditions and scope**。解释记录中的参数、测试条件与排除项，整理适用性待确认问题，提供请求相关资料的下一步。它不承诺整机选型、切削负载性能、加工精度、认证或验收结论。

E1 中已有的限制可以准确引用；为什么某种工况会导致何种工程差异等额外解释，仍需要独立、可靠的通用技术依据。不能从方法名、空载温度和转速推导未提供的技术关系。若只有当前 SYNTHETIC E1，只能做合成流程演示，不能交付真实客户工程事实。

先获得真实用户/客户的明确确认，再重新形成 Plan 和证据绑定。本轮在 TEST 数据中模拟了明确同意，真实任务未变化。

现有 [rebind_preserves_task](../../src/foreign_trade_geo_agent/core/evidence_intake.py:293) 保持标题、提纲、P/S/A 和目标操作不可变；`ScopeAdjustment` 只允许经确认删除完整内容点，不能删掉保留内容点的部分事实义务。因此模拟确认先令旧 task_version 1→2、plan_bound=false，再建立新 task `SPINDLE-NOTE` 和新 native Plan，重新提交 E1、重新绑定，保存 [06-lineage.json](06-lineage.json)。新任务不继承旧审核或执行权；[07-append-only-history.json](07-append-only-history.json) 保留旧目标及版本历史。

## 本轮实际业务验收

| 场景 | 实际结果 | 证据 |
| --- | --- | --- |
| 指南 / 只有旧 E1 | BLOCKED；F1 待人工核验，F2–F5 MISSING_CUSTOMER_EVIDENCE；Draft=false | [01-guide-only-E1.json](01-guide-only-E1.json)、[02-customer-request.json](02-customer-request.json) |
| 指南 / 增加独立的 E2–E5 合成文档 | 原五个内容点保留，Plan v2→v3、evidence v2→v3；五项资料均有绑定，但仍全部待人工核验、BLOCKED | [03-guide-more-materials-unreviewed.json](03-guide-more-materials-unreviewed.json) |
| 未同意缩小范围 | 拒绝提交，旧快照未变；无确认不能执行新任务 handoff | 新增 test_narrowing_without_explicit_consent... |
| 模拟明确同意缩小范围 | 旧任务 v2，原 Plan 绑定失效；新任务/新标题/新 Plan v2，重新绑定 E1，仍 BLOCKED/HUMAN_SEMANTIC_REVIEW_REQUIRED | [04-consented-old-task-unbound.json](04-consented-old-task-unbound.json)、[05-new-note-plan-unreviewed.json](05-new-note-plan-unreviewed.json) |
| 旧 Plan / 旧 digest / 跨任务审核复用 | 拒绝原链偷换新标题/研究、过期 CAS、旧审核与旧 E bundle；保留内容点的事实义务不能部分删除 | 新增版本、scope 与 native binding 回归 |
| Draft 安全边界 | 现有生产 admission 在 writer 前拒绝，调用数 0；E 客户独有事实未混入 P/S | 新增 Draft tripwire 与 E-only 隔离回归 |

E1 完全保留历史原文、来源 locator 和 hash；“evidence v2”是 Intake 收录版本，不是工程文件修订号。E2–E5 每条都有独立文档名/来源、NCX7 型号、revision A、条件/适用范围、SYNTHETIC 标记和完整 UTF-8 sha256，见 [synthetic-supplements.json](synthetic-supplements.json)。它们是四份独立虚构记录，不是四次独立工程验证。

**不能按五份材料齐全就判充分。** E2 的刀具和循环未确认，E4 只是验收提案，E5 不证明认证/服务承诺，E3 的虚构方法名不是可核验试验方法。新 S1/S2 也只是明确的本地合成规划标签，来源为 synthetic-context.example、仍标 UNVERIFIED_SEARCH_RESULT；没有升级成可靠通用技术依据。本轮不伪造 semantic SUPPORTED，不生成待交付文章，不优化合成短文。

## 实际测试与核验

- 新增模块：`python -m unittest tests.test_seo_task_scope_acceptance -v`，**13 项通过，3.398 秒**。
- 相关回归：`python -m unittest tests.test_seo_task_scope_acceptance tests.test_evidence_intake tests.test_intake_native_planning tests.test_planning_evidence_cli tests.test_seo_e_only tests.test_draft_revalidation tests.test_content_draft_core tests.test_content_draft_workflow tests.test_deepseek_content_draft_adapter tests.test_content_draft_word_boundaries tests.test_draft_execution_boundary -v`，**175 项通过，42.198 秒**，包含新增 13 项；[完整日志](regression.log)。有既有 Starlette/httpx deprecation warning。
- `python scripts/accept_seo_task_scope.py --output-dir docs/seo-task-scope-acceptance-2026-10-11`：实际执行成功，结果见 [acceptance-summary.json](acceptance-summary.json)。脚本只接受新目录，复跑需另选目录，不覆盖本验收包。
- `python -m py_compile scripts/accept_seo_task_scope.py tests/test_seo_task_scope_acceptance.py` 通过；`git diff --check` 无 whitespace 错误，有既有 LF/CRLF 提示。该 Git 命令只检查 tracked diff，不能替代新增文件的测试。
- 调试期间出现过脚本构造参数不兼容、合成来源 title/content 不一致、候选池截断，以及 Intake 要求 subject 在 source content 中 grounding 的 fixture 错误。首次新增模块运行 12 项均在 setup 报错；修正后一次剩余失败是网络 tripwire 误拦截 Windows asyncio 初始化的本地 socketpair，另一次错误是验收 JSON 二次编码列表。均只调整新增脚本/测试，未放宽生产验证。最终结果如上。
- 未运行完整仓库测试，不引用历史全套通过数；本轮没有生产源码改动，针对受用流程与安全边界执行上述回归。[verification.json](verification.json) 记录日志核对、原包摘要和验收工件解码核验。

## 兼容性、风险与下一次真实 Flash 前置条件

本轮没有编辑 `src/`、既有演示、冻结请求或原始文章；不改变生产行为、序列化 schema、数据库迁移、E-only 原句约束、Parser、Validator、预算或 Draft 准入。新增脚本仅固定离线场景，不能选择模型、外部接口、凭据、真实客户输入或授权模式；SQLite 使用临时文件，验收快照导出后释放。

剩余限制：原模板的宽标题不会因此自动被修复；当前系统依靠分析员登记义务及可信人工语义审核，没有自动搜索意图/范围充分性检测。旧演示仍是窄目标+宽标题且仅供 TEST，生产仍 NO-GO。两节提纲的确定性选择、12 个候选的截断、16 claims 预算和缺少逐节内容点映射仍需在实际交付 brief 中检查。本轮案例 brief 不会自动进入生产 Draft Prompt，不能声称已改善模型输出。通用技术解释、内容覆盖、复制和 CTA 需要新一次人工质量验收。

下一次真实 Flash 调用前至少需要：

1. 明确选择保留指南还是缩为技术说明。若缩范围，真实确认需绑定旧任务及当前 digest；不能使用本轮模拟确认。
2. 客户确认决策问题、标题与交付范围一致，形成相应新任务/Plan。逐点建立事实/通用依据/采购意义/行动的写作 brief；不能只添加标题或最低字数。
3. 提供并人工核验实际客户资料与必要的可靠通用技术来源，记录型号、工况、版本、完整原文与限制；当前合成 E1–E5 不能支持真实客户技术结论。若仅验证模型解释能力，必须继续明确 TEST/SYNTHETIC，不能称客户商业质量验收。
4. 对实际新 input、Plan、E、Prompt 和 scope 冻结摘要，审阅 S 的完整性/权威性以及写作预算；额外技术推演不得越过 E-only 边界。独立确认语义充分性与商业签核，不以原生 PASS 代替。
5. 若要把本 brief 接入实际 Draft Prompt，应先做限定的离线契约和预算验证并冻结最终请求；本轮没有此生产变更。真实调用另需针对该新请求的明确单次授权与现有执行安全前提，旧 Flash/Pro 许可、旧审核和新合成 Plan 均不能复用。

达到本轮最小验收后停止；无待执行网络调用、模型比较或生产变更。
