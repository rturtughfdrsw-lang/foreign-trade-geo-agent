# SEO Draft Contract v2 离线实现报告

日期：2026-10-12（北京时间）。范围：provider-independent contract 与 offline verification。

最终状态：**OFFLINE_SELECTION_CONTRACT_READY**。新增测试 54 项、相关模块 162 项、完整回归 1,955 项全部通过，exit code 均为 0。汇总见 [verification.json](verification.json)。

## 修改文件与架构

仅新增以下 8 个实现/测试文件，原有 2,445 个文件的保留检查见 [preservation.json](preservation.json)。

| 文件（仓库根目录相对路径） | 实现 |
|---|---|
| src/foreign_trade_geo_agent/core/draft_selection_contract.py | DraftSelectionContract、SectionEvidenceBudget、FactSelectionReason；selection/routing、snapshot/Plan/证据内容 hash、预算预检 |
| src/foreign_trade_geo_agent/core/draft_explanation_contract.py | ExplanationContract、ExplanationAnnotation；三部分解释、claim/section/refs/正文及候选 hash 绑定 |
| src/foreign_trade_geo_agent/storage/draft_selection_contract.py | 独立 V2 JSON artifact 与解释 sidecar 严格编解码；selection 文件 create-only 写入 |
| src/foreign_trade_geo_agent/workflows/draft_contract_v2.py | 显式调用的离线材料投影和候选回放；没有 Writer、provider client、runtime 注册、重试或交付 |
| tests/draft_v2_fixtures.py | 只读加载现有 synthetic design/frozen fixtures，转换为 V2 类型 |
| tests/test_draft_selection_contract.py | 集合、路由、hash、预算、审计记录及非法输入测试 |
| tests/test_draft_explanation_contract.py | 三部分正文绑定、遗漏/重复标注、前提及 sidecar 严格解析测试 |
| tests/test_draft_contract_v2.py | artifact、受限投影、V1 不变性、frozen-v1/v2 回放、实际超预算和软诊断测试 |

本报告目录新增基线、执行计划、测试日志/JSON、网络阻断器、可重跑脚本和可审阅 artifact。未引入新依赖。core 仅依赖标准库及既有 core；storage/workflows 向内依赖 core。

没有修改 production workflow 主链、现有 Writer、Prompt、Validator 放行逻辑、SQLite schema、V1 payload。没有添加新 Agent 或模型调用。没有 WordPress、部署、Git commit/push。按用户约束自行审查，没有另行委派模型审查。

## 行为

- 生成前必须满足 selected ⊆ required ∪ optional、required ⊆ selected、required_direct ⊆ selected；未知事实和非法类型拒绝。
- 与原 Plan 的 section 顺序、heading/question、requirements、sources、limitation/action 一致。每个 required/optional fact 都先检查 source 和 requirement 路由，selected 的 source 集合必须等于章节要求，并覆盖 requirements。
- artifact 绑定 evidence snapshot、规范化完整 Plan/P/S/brief hash，以及证据内容/位置/版本 hash；不能只替换 snapshot 字符串来重新绑定旧材料。
- P0/P1/P2 与选择/省略理由覆盖 43 个事实，存在内部 artifact。Writer view 不含这些理由，也不含未选事实、完整 E source 内容或完整 fact bank；保留 P/S context、原 validator contract、已选事实原文/source/version/location/source hash、章节边界。
- 硬上限 48 claims、24 blocks；逐章显式预算和必要 claims 的最低 block 容量在生成前检查。解释数量按章节显式 reservation 检查；全局直接事实 ≤30、解释 ≥12、CTA=1 只是诊断，不是额外拒绝规则。专门用显式允许的 11 条解释、2 个 CTA 正例验证这一差异。既有原生规则继续原样执行。
- 设计输入的 direct_fact_budget 上限合计 32，故预检有软提示；实际 mock 是 25 直接事实、12 解释、1 CTA，无实际软预算提示。
- explanation sidecar 与具体 claim ID、section、全部事实前提、候选 hash、selection hash、Plan/snapshot、正文 hash 绑定。三部分必须拼接为读者实际看到的正文；固定 limitation/action 位于对应部分。不能用 proposal.reasoning 或关键词标签代替正文。
- 解释结构沿用设计中的英文 20/12/20 最少词数、总 60–160 词及 1,200 字符上限；这只是结构代理，不证明推理正确。检查通过最多进入 PENDING_SEMANTIC_REVIEW；production_authorized 和 semantic_approved 固定为 False。
- malformed JSON 容器、深层 JSON、非法 Unicode、输出超长等在新增离线入口 fail closed；没有修订旧 Parser/Gate。

## 离线回放

运行：

```powershell
.\.venv\Scripts\python.exe docs/seo-draft-contract-v2-implementation-2026-10-12/replay.py
```

结果保存在 [replay.json](replay.json)。读取原 mock，不生成新文章。

| 样例 | 结果 |
|---|---|
| frozen-v1，SHA256 880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747 | 原 bytes 保留，50 claims 继续 DETERMINISTICALLY_REJECTED；保留原生预算、路由和其他错误 |
| v2 mock | 38 claims / 20 blocks；25 个独立选中事实；selection、routing、explanation structure 通过；PENDING_SEMANTIC_REVIEW |
| 49 claims / 25 blocks | 拒绝 |
| 未知 fact / 缺必要直接事实 / 跨章 source / 解释引用未选事实 | 拒绝 |
| candidate hash / Plan hash 不匹配 | 拒绝 |

可审阅产物：[selection-artifact.json](selection-artifact.json)、[explanation-sidecar.json](explanation-sidecar.json)、[writer-material.json](writer-material.json)。脚本对已有 artifact 只核对相同内容，拒绝覆盖不同内容。

## 实测与失败记录

所有测试通过本目录 run_tests.py 执行标准库 unittest；守卫阻止外部 socket/DNS/UDP，Python 子进程继承守卫。仅允许既有测试所需的 loopback。MockTransport 等模拟调用不是实际 API 或 WordPress 操作。没有执行 live/integration opt-in 脚本。

| 验证 | 实测结果 |
|---|---|
| 修改实现前的相关基线 | 29 tests，0 failures，0 errors，exit 0 |
| 初次全量基线 | 1,901 tests，0 failures，7 errors，exit 1；运行期间新增源码触发旧实验的 EXPERIMENT_CODE_CHANGED，不能视为既有缺陷或通过基线 |
| 最终新增测试 | 54 tests，0 failures，0 errors，exit 0 |
| 最终相关模块 | 162 tests，0 failures，0 errors，exit 0；包含先前出现冻结错误的 test_seo_article_experiment，已通过 |
| 最终完整回归 | 1,955 tests，0 failures，0 errors，0 skipped，exit 0；468.269 秒 |

开发中的 RED 日志保留：新模块/函数/codec 尚不存在时导入失败；随后曾误用一个不存在的输出长度常量，已修正为现有常量；一个边界负例分段过短，调整分段后验证实际 placement 拒绝。自检发现非法容器可抛 TypeError 和 block 最低容量未预检，均新增重现测试后修复。深层数组保留原生 FIELD_CONTRACT/JSON_FORMAT 拒绝，不更改原生错误语义。最终新增测试全部通过。

真实模型/API 调用 **0**；真实 WordPress 调用 **0**。各组测试与回放外部网络尝试计数均为 0。没有修改生产 Gate，完整文件 hash 对比作为证据，而非仅依靠 Git tracked diff。最终完整回归源码稳定，初次基线的 7 个冻结检查错误没有复现。

## 限制

- 未接入生产链或现有 Writer，也未验证真实模型生成稳定性。
- 测试使用已有合成证据和手工 mock，英文解释长度是结构代理；语义、采购价值和可交付性仍需独立审核。
- 必须向离线 builder/replay 传入当前 native input 和当前 snapshot；artifact 本身不是签名、审批或执行权限。
- Selection 为独立本地 JSON artifact，没有 SQLite 注册或迁移。
- 使用现有 native parser 的内部入口，未来其签名变化时需同步离线适配测试。
- 当前基于作者审查，没有新增审查 Agent。

不进入 REAL_REQUEST。任何后续真实实验等待单独授权。
