# SEO Draft Contract v2 — REAL FLASH EXPERIMENT PREFLIGHT

日期：2026-10-12（北京时间）。最终状态：**REAL_REQUEST_PREFLIGHT_READY**。

## 是否准备好真实实验？

**已完成可审阅、可冻结的单次 Flash 实验离线准备。** 本轮没有调用真实模型/API，没有真实 v2 输出，没有 WordPress、部署或 Git commit/push。`live_authorized=False`、`production_authorized=False`、`semantic_approved=False`。READY 表示请求与评估入口已准备，不授予执行权限，也不证明模型会遵循合约或文章有商业价值。

活动请求：[request-body-template.json](request-body-template.json)。SHA256：

`67556e8190c96aa554dd7cadbfc40c30a4e96513e23de6e5c27c29426e4dea40`

[manifest.json](manifest.json) 在本报告完成后最后封存；每个条目包含 filename、sha256、size、created_time、version。manifest 本身不能自包含 hash；其独立 hash 在 [manifest.sha256](manifest.sha256) 及最终聊天消息公布。使用可信渠道固定的 hash 做只读验证，不能将同目录可同时改写的 hash 文件当作自行授权。

## 改动文件与实现

仅新增 58 个文件：本目录 56 个实验输入/文档/测试记录/冻结文件，以及两个独立脚本/测试文件。没有修改或删除既有文件。完整清单见 [file-changes.json](file-changes.json)，2,505 个既有文件的 SHA256 保留检查见 [preservation.json](preservation.json)，最终实现/测试及 frozen-v1 共 344 个文件另由 [source-integrity.json](source-integrity.json) 绑定。

| 文件 | 行为 |
|---|---|
| scripts/prepare_seo_draft_v2_flash_preflight.py | 纯离线 selection 校验、Writer 请求构建、严格解释 envelope 适配、输入一致性审计、create-only 导出、manifest 封存及可信 hash 复核；没有 transport、凭据读取或 live runner |
| tests/test_seo_draft_v2_flash_preflight.py | 23 项预检测试，覆盖稳定请求、控制变量、选择/Plan/snapshot/证据绑定、防泄露、解释正文绑定、旧 V1 保留、清单失效和无外部调用 |
| 本目录 run_tests.py / network_guard/sitecustomize.py | 标准 unittest 执行日志与 socket/DNS 守卫，继承到 Python 子进程；新增与合约测试禁止所有网络，完整回归仅允许本地 loopback |
| current-architecture.md / success-criteria.md / failure-taxonomy.md | 架构事实、采购价值评审和 A/B/C/D 失败归因；不将 Validator PASS 当作商业成功，不因一次失败自动换模型 |

没有更改 production workflow、现有 Writer、Prompt、Parser、Validator 放行规则、runtime、SQLite schema 或 WordPress 交付。完整冻结内容含 system/user prompt、Writer material、selection artifact、explanation contract、task、Plan、完整本地 evidence snapshot、request template、experiment config，以及预算、合成验证、保留和测试证据。

## 架构检查结论

详见 [current-architecture.md](current-architecture.md)：Evidence → Selection Artifact → Writer Projection → Prompt → LLM（待授权）→ Parser → Validator → Review。

- 既有 V2 仅用于离线投影/回放，尚未接入生产真实 Writer。本轮将已验证 Selection Contract 接到具体的实验请求模板；生成请求前检查 snapshot、evidence hash、Plan hash、selection、section routing 与预算。
- Writer 的客户事实仅来自 25 个 selected_facts；整个 material 仍保留 P/S 规划上下文、brief、章节和 Validator 约束，不能谎称 material 只有事实数组。完整 E 内容、未选事实及 selection reasons 均不发送。测试也覆盖未选事实隐藏于规划上下文的情况。
- 模型仅可使用 selected_facts，禁止重新寻找或补充事实、扩大数字意义、生成认证/客户案例/性能保证。第一优先级是采购决策价值；每章必须回答 buyer question，包含 Evidence、Interpretation、Boundary、Verification，并解释具体 why。
- 原 Parser 保持顶层仅 `draft` 的严格规则。实验外层只有 candidate / explanations；candidate 沿用原生文章 schema。显式解释三部分必须拼成实际正文；本地绑定 claim_id、section_id、全部 selected_fact_refs、candidate hash、正文 hash、selection/Plan/snapshot hash。模型不计算可信 hash，不自动补齐、拆分或修复解释。
- 封存前重建所有活动输入并逐字节比对；封存后任何文件内容变化、额外文件、删除、清单/锚点变化或源码漂移使实验失效。prepare/freeze 拒绝覆盖已封存包，旧授权不继承。`unsealed-history/` 只保留实施中的非活动源码快照。

## Controlled comparison

基线严格使用 `docs/seo-flash-contract-quality-live-2026-10-12/frozen-v1/`，不混用父目录另一次实验。保留 model=deepseek-flash、temperature=0、thinking.disabled、response_format=json_object、max_tokens=16384、topic、任务/Plan/P/S/brief 和客户证据。

仅记录三组变化：**Selection Contract、Writer context、Explanation requirement**。JSON mode 与 native article schema 相同，新增解释 envelope 属于第三组变化，完整应用层响应形状存在差异并已记录。

这是 **Controlled comparison**，不是 strict A/B 或 causal proof。多项变化一起发生；历史输出与未来单样本不能隔离原因，模型别名后台也可能随时间变化。

frozen-v1 原输出 SHA256：`880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747`。原始 50 claims 继续 DETERMINISTICALLY_REJECTED，CLAIM_BUDGET 及其他原生错误保留，见 [package-audit.json](package-audit.json)。没有改写旧输出或重新放行。

已有设计 mock 经新输出入口回放：Parser PASS、Validator PASS、selection/routing/explanation structure PASS，38 claims / 20 blocks；仅 PENDING_SEMANTIC_REVIEW，见 [synthetic-offline-validation.json](synthetic-offline-validation.json)。它不是本轮真实模型输出，也不是人工质量审批。

## 实测与失败记录

标准库 unittest 的实测日志与 JSON 均保留。下表各组存在重叠，不相加计算独立测试数。

| 验证 | 数量 | failures / errors | exit code | 结果 |
|---|---:|---:|---:|---|
| 初次新增测试 | 21 | 1 / 1 | 1 | 嵌套 manifest 文件误排除；测试误用不存在的字段。已分别修复并保留 initial-red.json |
| 首轮修复后新增 | 22 | 0 / 0 | 0 | new-green.json |
| 首轮合约相关 | 76 | 0 / 0 | 0 | contract-final.json |
| 其他相关模块 | 85 | 0 / 0 | 0 | related-final.json；补强前运行，最终全量再次覆盖 |
| 首次完整运行 | 未完成 | 不作完整结论 | 1 | 为补强封存前所有输入一致性而本地停止，full-interrupted.json；不计为通过 |
| 最终新增 | **23** | **0 / 0** | **0** | new-final.json；严格禁止网络，网络尝试 0 |
| 最终合约相关 | **77** | **0 / 0** | **0** | contract-verified.json；严格禁止网络，网络尝试 0 |
| 最终完整回归 | **1,978** | **0 / 0** | **0** | full-final.json；0 skipped，453.735 秒 |

汇总：[verification.json](verification.json)。真实模型/API 调用 **0**；真实 WordPress 调用 **0**；最终各组外部网络尝试 **0**。相关测试记录 65 个 loopback 事件，完整回归记录 1,955 个 loopback 事件（socket/DNS 事件，不是 API 请求数）；它们属于既有本地 HTTP 单测，不能描述为全量完全无网络。MockTransport/fake 调用不计作真实请求。没有执行真实 opt-in live/integration 请求。

当前依赖的弃用提示、asyncio 耗时诊断、CLI 参数负例输出另见 [console-notes.md](console-notes.md)，未据此升级依赖或绕过测试。首次失败和中断均如实保留；最终没有未解决的离线测试失败。

封存前的额外文件集合检查曾 exit 1：导入网络守卫生成了目录内被 Git 忽略的 .pyc 缓存。检查在 manifest 创建前拒绝了它；只清除该生成缓存，并在最终封存/验证进程中关闭 bytecode 写入，未修改实现或已通过的测试。记录见 [seal-attempt.json](seal-attempt.json)。

## Token 与费用边界

见 [token-budget.json](token-budget.json)：输入 **estimated 7,778–15,556 tokens**，按字符 /4 至 /2 的启发式估算，包含的 chat framing 不精确；没有 tokenizer API，不能冒充精确值或证明上界。max_output_tokens=16,384。

worst_case_cost 字段为明确标注的**历史费率规划场景估算**：65,536 输入 + 16,384 输出，USD **0.0393216**。建议预算 USD **0.05**，尚未授权。当前价格/别名/参数未通过网络核验；该数字不是当前报价、真实账单或硬上限。执行前若获授权核验后条件不满足，应停止，不修改冻结包或换模型。

## 如果失败，失败在哪里？

当前离线预检无阻塞失败。实施中曾发现本地 manifest 完整性缺陷和测试字段错误，已修复；完整运行一次中断后重新完成。没有真实 v2 结果，因此不能评价真实模型是否失败或商业质量是否改善。

未来依 [failure-taxonomy.md](failure-taxonomy.md) 分开记录 Contract failure、Instruction following failure、Reasoning quality failure 和 Validator issue。引用/结构问题先复现接口和合约，指令遵循问题优化 prompt，解释浅薄由人工评审后考虑模型能力，Validator 缺陷单独处理；不凭一次失败自动切换模型。

## 下一步需要什么授权？

停止在 **REAL_REQUEST_PREFLIGHT_READY**，等待人工明确授权以下具体动作，见 [review-and-authorization.md](review-and-authorization.md)：

1. 本次可信 manifest hash 与上述 request hash 所绑定的**一次** Flash 请求；重试 0、fallback 0、模型切换 0。
2. 明确预算及接受 estimated token/费用边界；可同时授权执行前只读核验供应商官方当前参数/别名/价格。若条件不满足，停止。
3. 仅为该 synthetic 实验保留原始响应、规范化 candidate 和绑定 sidecar，再运行原生 Parser/Validator 与人工 Review；不得记录凭据。

本轮“确认”不包含上述真实调用授权。后续单模型实验不包含 WordPress、发布、部署或 Git commit/push。Validator PASS 仍不等于商业成功，任何通过结果仍须人工审核。
