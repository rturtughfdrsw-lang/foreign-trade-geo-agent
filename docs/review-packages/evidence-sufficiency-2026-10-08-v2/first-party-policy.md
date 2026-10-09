# P-only 产品需求核对与最小兼容方案（待决，未实现）

当前 S 约束完整保留；没有添加新 S、把 P 伪装为 S 或产出例外 Plan。默认行为不变。

## 产品需求证据与适用范围

项目目标要求基于网站证据规划/起草内容。`core/content_draft.py::_derived_support_kind` 已支持 `FIRST_PARTY_OBSERVED`，第一方/数字仍有 P grounding 边界。前包历史 C1 的 P4 DESCRIBE、C3 的 P3 EXPLAIN 说明内容点可来自 P，而 Opportunity topic/operation 仍挂市场 S。这是已有功能与任务之间的真实约束不匹配证据，不是客户调研或已批准需求。

企业原文忠实整理有合理用途：整理已有产品描述/申请 brief、压缩重复或转换呈现。需要使用权、目标/增量、原文支持与适用条件；无关 S 不增加事实支持。**这些是待所有者确认的产品需求，不声称客户验证/商业收益。** 当前 P 是网站观察模型；企业离线手册/上传文档不能伪造为现有 P，若以后接入另设计来源/提取边界。

演示任务只解释虚构页面说什么。真实企业资料可支持“企业声明什么”；通用技术选择/实际性能保证仍需作者/厂家授权、型号/条件、专业依据及审核。P-only 是来源路线，不是权威等级。

## 当前精确阻塞

| 代码边界 | 现有约束 / 本候选影响 |
|---|---|
| `content_opportunity.py::validate_content_opportunity_specification` | 所有类型要求 nonempty source_refs；实际 pure probe 返回 `SOURCE_REFERENCE_REQUIRED` |
| 同函数后续 grounding | topic 要出现在所引 S title/content；P3 H1 不能凭 P 通过。未挂 unrelated S 替代支持 |
| `ContentOpportunityTopicCandidate`、Prompt/__post_init__、builder | topic origin/候选池为 S；单改空 S 校验仍不能合法选 P3 topic |
| `change_plan.py::_OPERATION_PREREQUISITES/_derive_allowed_operation_types` | EXPAND availability 也要求至少一个 S，不能宣称 P-only 已可选 |
| `validate_and_finalize_specification` EXPAND 分支 | page>=1/source>=1、origin/locator/point 仍要合法；没有合法新 Opportunity，未调用 Plan finalizer |
| `validate_change_plan_input/finalized_content_opportunity_error` | 稳定 report 再验 topic/refs/派生文案，手工 SUCCESS report 不是合法方案 |
| Opportunity 派生 actions/rationale/reporting | 文案目前描述外部 context；条件分支须真实说明第一方贡献，不能空 S 或假称外部认证 |
| Draft stable/claim/finalizer | revalidate Plan，已有 P-only claim 不等于 P-only Planning 已可用，不认证权威性 |

旧 ADD_SECTION 还受新标题 S grounding/现有 H1 重复约束，CREATE_NEW_RESOURCE 标题/outline 也来自 S。选 EXPAND 现有 H1 避免扩展新标题契约；一个 EXPLAIN point 绑定 O1–O6，不以六 points 超过五上限。

## 建议最小切片

保留默认 S 约束，只给**可信人工范围/支持审核过的第一方 observed EXPAND_SECTION**显式、绑定当前输入的条件上下文（概念名 `FirstPartyObservedExpansionContext`，尚非接口）。provider/crawler 不能设置；默认 None 走旧逻辑。

全部条件必需：

1. 所有者确认有权用途、问题/义务/深度/增量；真实人类通道的审核记录可保全。
2. P 成功提取、原文/version/span 精确，全部必答关系有直接来源且获实际支持审核；截断外事实不能补入。
3. P-origin topic/point、observed 既有 locator；只 EXPAND_PAGE_SECTION/EXPAND_SECTION，refs scope 一致。
4. 绑定 task/义务/language/Plan/evidence/用途/政策版本；工程内容须有适用专业来源，owner 身份不代资质。
5. 原数字/first-party/claim-type/竞争方/scope/预算/重复/comparison 禁用校验保留；空 S 不等于空证据或容忍装饰引用。

不涵盖 ADD_SECTION、CREATE_NEW_RESOURCE、structure-only 例外、comparison、发布或通用技术权威。新标题/资源需求另做契约工作。

## 未来最小必要改动与兼容

- Opportunity：可信 context 下的 P-origin candidate/validation；仅限定 EXPAND 满足条件时空 S。同步 candidate origin、Prompt、provider parser 引用解析、派生文案；先查 parser 路径再改，不只给 validator 留后门。
- Plan：同 context 进入 input validation、最终 catalog availability、EXPAND finalizer；S minimum 例外局限确切 R/action/P，不改全局 `MIN_SOURCE_REFS_PER_OPERATION=1`；稳定/报告重验也须取得同 context，否则拒绝。
- Draft/报告：复用 P-only claim/数字检查，真实呈现来源贡献；所有需重新验证新 report 的入口显式接收 context，不由 artifact 上 provider 可填 bool 授权。
- 保存：优先保持 V1 payload，独立 immutable sidecar/envelope 由 runtime 选定；随报告重载仍可定位，缺失不得默过。历史 decode/review 不升级语义。若入口无法可靠传 sidecar，先设计最小版本化 envelope，不先产生无法重验的 report。
- 后续 focused 验证：默认无 S 拒绝；可信限定 EXPAND 允许；未审/无权/过期/错绑 writer=0；其他 action 拒绝；六义务缺一拒绝；原数字/first-party/scope/availability/comparison/历史兼容保留。本轮不编写正式 tests。

风险是可信审核与 context 传递，不只是删除两条长度判断。D04 可接受限定方向、拒绝 P-only 或要求真实相关 S；D03 可因无增量取消。接受方向后仍需实现、合法 report 与重绑签核；不能改题为 S3 的宽泛主题/市场指南求通过。

## 避免审核/Plan 的循环前置

未来可信上下文须区分两种用途：`PLANNING_SCOPE_ONLY` 先绑定已冻结 specification/P 原文及所有者真实范围/用途决定，只允许限定离线 finalization，不能调用 writer；`DRAFT_ADMISSION` 必须绑定生成后的合法正式 Plan、实际证据与完整逐项审核。前者不能成为后者的默认值。新 Plan 与候选不一致即重新审范围；生成准入必须重绑/签核后才开放。这样不要求“有已签 Plan 才能先创建该 Plan”，也不以预先批准方向冒充正式充分性认证。这两个标签只是设计，没有已实现的权限模式。
