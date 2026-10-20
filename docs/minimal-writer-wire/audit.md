# Phase 0 可组装性审计

结论：**可实施 TEST-only 离线原型；现有 Plan 不足以授权生产解释槽位。**

审计读取当前源码、Selection v2 design/input，以及最新真实实验
`docs/seo-draft-v3-repair-2026-10-13/next-results/20261013-122631-flash/`。
用户提及的 Astra Pro 独立报告未随任务提供、仓库文件名搜索未找到；不声称读过该报告，按本轮粘贴的具体要求实施。
全部既有 Git 可见文件在编辑前建立 SHA256 基线（baseline.json，2775 文件，包括未提交文件）。

| 章 | selected assignments | required direct | explanation minimum | claim max | block max |
|---|---:|---:|---:|---:|---:|
| S1 | 5 | 5 | 2 | 8 | 4 |
| S2 | 4 | 4 | 2 | 7 | 3 |
| S3 | 4 | 4 | 2 | 7 | 3 |
| S4 | 4 | 3 | 2 | 7 | 3 |
| S5 | 3 | 3 | 2 | 6 | 3 |
| S6 | 6 | 6 | 2 | 10 | 4 |

selected 共 26 次章节分配、25 个不同事实；E4.F01 同时用于 S3/S4，但只在 S3 直接展示。
required_direct 共 25 条。selection claim ceiling 合计 45，block ceiling 20；direct 预留 ceiling 32 导致现有 soft diagnostic `SOFT_DIRECT_FACTS_OVER_30`，不是实际展示 32 条。
12 个解释 + 25 原句 + 1 CTA = **38 claims**；每段最多 4 claims，确定性分组可得 **13 blocks**，不超过 native 48/24。
6/25/12 是这次 CNC synthetic 验收条件，不是跨行业通用常量。

现有 Plan 每章只有 reader_question/explanation_goal 一对，虽列出多个考虑项，没有两个独立且已审阅的子问题/决策目标。
Python 不得自行拆分并继承审批。本原型只接受显式 `TEST_ONLY_MANUALLY_AUTHORED` 槽位计划；由测试作者写子问题、目标及已知冲突措辞，独立冻结，不修改旧 Plan 或其审批。

## Native 实际要求

- `workflows/content_draft._parse_specification`：严格 native 外壳/字段，章节形状、proposal 五字段；不负责语义或最低解释数。
- `core/draft_candidate_review.inspect_specification`：章节标题/顺序须等于 Plan；24 total blocks、48 total claims、4 claims/paragraph、每章最多 4 paragraph blocks。
- `core/content_draft.article_quality_findings`：每章至少 1 direct 和 1 interpretation（**不是 2**）；来源集合须等于 brief.supporting_evidence；fact requirement 路由及覆盖；最后一个 claim 必须 CTA。
- 引用 direct 必须为一个 fact 的完整精确原句。正文重复按 casefold/空白归一判定；不同章节也不能重复。
- interpretation 必须有 proposal；procurement_question 须等于章节父问题。proposal 的 limitation/action 须在正文可见；native 本身不证明其等于 Plan，两者相等由本实验额外冻结检查。
- numeric grounding 同时检查正文及 proposal。含数量的 inference 句须在实际引用原句中出现，不能仅保留数字后改变主语/条件；模型编号不等于数量。保守正例使用定性推理，数量保留在 direct 原句。
- native Candidate Validator 的 proposal-only 模式允许**待人审**的新推理，不调用 DraftItem finalizer、不向 bundle 注入已批准 interpretation。这是直接调用现有 Candidate Validator 的正常边界，不是 v3 替代逻辑。

## v3 冲突及兼容风险

最新真实输出 33 claims、12 blocks、26 direct、6 interpretations、1 CTA；最后 annotation 指向 CL33 CTA，实际 interpretation CL32；E4.F01 重复；解释数不足；含数值改写。
v3 exact render formula 要求重复 limitation，产生 `The both parties`、`the a ...` 等机械英文；正文与 sidecar 重复表达又导致绑定漂移。
新路径不调用 v2/v3 explanation inspector、render_parts、repair 或宽松替代逻辑，也不宣称 v3 PASS。
正文使用模型提供的一份 implication/assumption/boundary/action，后两项在此最小原型中必须精确等于 Plan；Python 不补写冲突限制语。

可确定性实现：结构/位置/引用范围、原句及版本绑定、编号、预算、hash、正文同源、原生检查、显式拒答阻断。
不能确定性证明：每个 premise 是否真的参与推理、两个自然语言目标是否语义独立、假设是否合理、责任是否充分、自然语言是否暗含矛盾。
已知冲突可用人工编写的禁止陈述阻断；其它风险必须带原文并保持 Semantic Review PENDING。结构通过不提供商业批准。

可行性条件满足：原生契约容许 38/13 组装；继续 Phase 1–3，必须以真实测试结果确认，不改变任何生产文件。
