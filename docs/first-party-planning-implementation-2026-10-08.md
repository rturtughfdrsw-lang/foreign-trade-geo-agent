# 条件 P-only 规划工程实现（2026-10-08）

本轮是通用、离线、仅规划的最小能力实现。**不是 Evidence Sufficiency Gate 实现，不是 P3 当前候选的业务签核，没有 Gate GREEN。** 先读取 AGENTS.md、v2 主审核包与附件，并核对当前代码和 Git 状态；工作树已有大量未提交修改，本轮只在下列文件上追加本次改动，没有 commit/push。

## A. 授权声明保全

新增 [owner-authorization-statement.json](review-packages/evidence-sufficiency-2026-10-08-p-only/owner-authorization-statement.json)，逐字保全本次用户消息转述的项目所有者声明，引用 `ESG-OWNER-REVIEW-20261008-v2` 及原 binding digest。

- D01：记录所报使用权，仅本项目受控演示和离线验收；对外商业展示仍 NOT_REVIEWED。
- D02：仅记录演示用途及不作真实工程技术认证的边界；完整题目、义务、输出约束没有被批准。
- D03–D08 与 O1–O6 全部 NOT_REVIEWED。没有 reviewer、原确认时间、有效期或签名的虚构填充。

来源限制：Codex 收到的是当前人类用户消息对先前 ChatGPT 人类消息的转述及保全指令。未提供可独立读取的原消息 ID/链接、原始时间或身份认证资料；不能声称已独立核验原所有者消息。本记录是转录，不是验证签名或 runtime approval。原 v2 包、空模板、绑定和历史结果均未改写。

## B. SOURCE_REFERENCE_REQUIRED 的根因

`core/content_opportunity.py::validate_content_opportunity_specification` 在引用 namespace/known/duplicate 校验后，对所有 Opportunity 无条件执行非空 S 检查，然后仅从被引 S 的 title/content 对 topic 作连续文本 grounding。v2 P3 候选在前一检查就返回 `SOURCE_REFERENCE_REQUIRED`。

原契约链还包括：

1. `ContentOpportunityTopicCandidate`/Prompt 只接受 S-origin topic，workflow parser 要求 topic origin 出现在 source_refs。
2. Opportunity SUCCESS report 原来必须带 S display sources。
3. `validate_change_plan_input` 重验 finalized Opportunity、证据、固定 limitations 和派生文案。
4. `_OPERATION_PREREQUISITES`/`_derive_allowed_operation_types` 对 EXPAND availability 要求 S；`validate_and_finalize_specification` 的 EXPAND 分支再次要求 S。
5. Draft stable validator 使用默认 Planning 重验；既有 P-only claim 支持不能让上游 P-only Planning 自动合法。

因此不能只删除一个 validator 的长度判断，更不能挂无贡献 S 来通过主题匹配。本轮原默认 S 约束保留；例外是下面完整限定的显式输入。

## C. 实现范围、契约与文件

新增纯 core `FirstPartyPlanningScope`/`FirstPartyExcerpt`。它是操作者显式传入的**规划技术输入**，不从 provider JSON、页面或历史 artifact 中加载授权。无 approved/sufficient/trusted 状态，不消费上述授权转录作为权限。

最小任务类型为 `ATTRIBUTED_EXCERPT`：仅呈现本页实际观察到的逐字摘录；不接收任意解释问题或认证义务。要求完整 packet 等值绑定、另行传入相同 task_id、成功 P 提取、确切字段/Unicode 半开 span/quote、一处既有 observed heading、一页、一个 R、无 S/A、仅 EXPAND。每条摘录遵守既有 120 字符 ContentPoint 上限，1–5 个；不放宽原预算。完整 structured text 可用，即使 body 截断；被选择字段截断则拒绝。body_text 仅用于无歧义的单 H1、无 H2/其他 structured heading 页面；structured text 必须有匹配 heading，不接受 image-alt/metadata 替代原文。

Plan 只允许 `EXPAND_SECTION / EXACT_OBSERVED_HEADING`，所有摘录必须按顺序完整绑定为 P-origin ContentPoints，intent 仅 DESCRIBE/SUMMARIZE。EXPLAIN、COMPARE、ADD_SECTION、新资源、重排、链接均不走此例外。availability 从最终候选池推导，裁剪掉任何必需摘录即不可生成。finalizer 保留全部原引用、grounding、locator、operation、预算及 comparison 禁用规则。

修改生产文件：

- `src/foreign_trade_geo_agent/core/first_party_planning.py`（新增）：限定输入与字段绑定。
- `src/foreign_trade_geo_agent/core/content_opportunity.py`：显式上下文校验、P topic candidate、严格空 S report 结构、真实第一方来源派生文案和 finalized 重验。
- `src/foreign_trade_geo_agent/core/change_plan.py`：可选上下文、全量 stable validation、最终候选池/availability 与 EXPAND finalizer。
- `src/foreign_trade_geo_agent/workflows/content_opportunity.py`、`workflows/change_plan.py`：贯通显式参数；P-only 不借 Research 失败 fallback，必须传 None，且无 audit；错绑调用 writer 前拒绝。
- `src/foreign_trade_geo_agent/adapters/deepseek_content_opportunity.py`、`adapters/deepseek_change_plan.py`：仅显式模式的条件提示与实际请求预算；没有真实 API 调用。
- `tests/test_first_party_planning.py`（新增）：正式 unittest 验证。

关键契约改动已在生产修改前向用户说明：可选参数默认 None；transient catalog 保留 packet 供准确重验；SUCCESS Opportunity 只在受限结构下可空 S。**SQLite/schema/codec/payload version/public artifact fields 未修改，无迁移。** 旧合法对象的解释及默认路径不变。新 P-only report 本身不携带权限，重载若无显式匹配 scope 仍拒绝；其规划 scope 不传入 Draft。本轮不声称已实现可信 sidecar/重启恢复、CLI/UI/runtime 产品入口或充分性准入。

补充材料在独立目录，未加入旧 v2 manifest：[原生合成示例](review-packages/evidence-sufficiency-2026-10-08-p-only/native-planning-example.json)、授权转录及本轮验证记录。示例是正式生产 workflow + 注入 fake writer 的合成离线测试，不是 NovaCNC、新抓取页面、真实厂商资料或已批准 Plan。

## D. 本轮测试及历史兼容性

最终命令/数量/结果见 [verification.json](review-packages/evidence-sufficiency-2026-10-08-p-only/verification.json)。不引用历史测试成绩作本轮结果。

| 本轮实际验证 | 结果 |
|---|---|
| 首批相关模块（当时 8 项新测试及 Opportunity/Plan/availability/comparison/两 adapters） | 256 tests，OK，21.412s |
| 最终 15 项 P-only + 22 项 Plan adapter | 37 tests，OK，1.019s |
| 第一遍完整回归（运行期间新增 adapter 测试，尚非最终版本） | 1386 tests，OK，302.145s |
| 最终版本完整回归 | **1387 tests，OK，300.334s，exit=0** |
| 当前代码重验旧 P3 v2 默认候选 | SOURCE_REFERENCE_REQUIRED；finalizer/provider/Draft/WordPress=0 |
| 原生合成离线导出、旧 v2 摘要/绑定检查、差异/新增文件空白检查 | 通过；不认证充分性或人类身份 |

最终相关命令：`.\.venv\Scripts\python.exe -m unittest tests.test_first_party_planning tests.test_deepseek_change_plan_adapter -v`。最终全量命令：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`。完整日志在 ignored `.data/first-party-planning-final-full-regression-20261008.log`，摘要/digest 保存在补充 verification.json。全量输出的 launcher/port 文本是既有测试的预期输出，unittest 最终为 OK。

开发过程真实失败：首轮 8 项 RED 因新 scope 模块尚未实现报 ModuleNotFoundError；第一版实现剩两项失败（测试 Plan fixture 错用顶层 `plans`，及 P-only COMPARE 拒绝类别未明确），随后修正；新增 mock adapter 测试发现 Plan system prompt 超过原 8000 字符预算，改为 104 字符条件说明，不扩大上限，最终 7996 字符；辅助示例脚本首次未加仓库根目录到 sys.path，导入 tests 失败，修正后成功。这些不被抹去或当成 Gate RED。

最终验证摘要首次生成时错误地尝试以 UTF-16 读取无 BOM 的 UTF-8 日志，结果断言失败，未写出摘要；改为先判断 BOM 后按正确编码读取，生成成功。这是辅助保全脚本错误，未重写日志或改变测试结果。

正式测试覆盖：合法 P-only/native workflow；无证据、非法/跨作用域引用、错 task/packet/locator/point；装饰性已知 S；题目相关但缺要求原句；选择字段截断/image context 边界；所有摘录不可漏/不可裁；混合 P/S、comparison 拒绝；provider 不得写 scope/approval；Draft 准入仍关闭。mock HTTP 测试仅使用注入 `httpx.MockTransport` 和占位 key，真实网络/付费调用为零。

五类冻结 V1 artifact 实际 decode→encode JSON 等值，旧 comparison 仍拒绝。旧 v2 manifest 列出的全部文件摘要及空审核模板保持一致；不运行会改写旧 verification.json 的材料脚本，也不修改生产 SQLite。完整回归仅使用仓库正式 unittest。

## E. 能否原生生成合法 P-only Opportunity/Plan

**可以，针对本轮限定的通用摘录任务。** [合成原生示例](review-packages/evidence-sufficiency-2026-10-08-p-only/native-planning-example.json)实际由两个生产 workflow 生成 SUCCESS，稳定 Planning 输入重验通过，availability 只有 EXPAND_SECTION，page_refs=[P1]、source_refs=[]，两个 fake writer 各调用一次。没有手填绕过校验的 SUCCESS。

例子没有 scope 的 Planning 重验与 Draft stable validation 都返回 FIELD_CONTRACT，真实模型/Draft writer/WordPress 调用数均为零。Planning SUCCESS 只表示受限规划契约合法；没有充分性 verdict 或技术真实性认证。

**P3 v2 当前候选仍不构成可执行签核对象。** 其 EXPLAIN/页标题→六义务映射超过本次逐字摘录能力；未改写问题、减少义务、替换为 SUMMARIZE 或用六个 ContentPoint 绕过五点上限，也未为它创建正式匹配 report。D04 仍 NOT_REVIEWED。

## F. 仍需所有者确认

独立可核验的原人类消息记录及审核权限/保存/时效（D06/D07）；完整任务、深度、输出边界及每 O 的支持判断（D02/O1–O6）；增量与 placement（D03）；当前 P3 EXPLAIN 候选及条件 P-only 业务方向（D04）；同冻结输入消费（D05）；独立真实 B2B 验收（D08）。对外使用仍需独立确认。不能以本次一般技术实现代替这些决定。

若要推进 P3，最小待决问题是：是否保留当前六关系 EXPLAIN 任务/一个点映射全部义务，以及接受其演示展示价值、EXPAND placement 与来源路线。得到真实确认后，另设计与该任务相符的直接支持/义务契约，不能把本轮固定摘录任务冒充它。这里不要求用户签字绕过技术验证。

## G. 正式 Gate 的前置条件

1. 获得可追溯的真实范围/使用权、完整任务/义务、审核者权限/时效决定；缺项继续未审。
2. 逐 O 对照完整适用原文作真实支持审核；主题匹配、span 命中、P 身份和所有者声明不能派生 SUPPORTED。真实工程扩展须专业适用证据和审核。
3. 为实际批准的任务取得匹配且原生合法的正式 Opportunity/Plan。P3 EXPLAIN 不能复用本次摘录例外；新对象、任务、材料或实际 writer 范围改变须新冻结/重绑/重审。
4. 实现可信 review loader、完整绑定检查及 append-only lineage/重启可读保全，并从冻结对象直接构造同一 DraftInput，不重跑 Planning/选 latest；仅规划 scope 不升级为 Draft admission。
5. 才实现独立 Gate preflight/分类拒绝/诊断，并测试未审、不足、错绑、过期等 writer=0。正式充分性与生成后逐论断质量审核分开；模型调用或 WordPress 操作仍各自另授权。
