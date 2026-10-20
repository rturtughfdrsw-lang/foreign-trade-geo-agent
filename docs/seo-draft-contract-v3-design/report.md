# SEO Draft Explanation Contract v3 — offline report

最终状态：**OFFLINE_EXPLANATION_CONTRACT_V3_READY**

2026-10-12，Asia/Shanghai。Phase 0 审计先于代码修改完成，之后实现隔离的 v3 采购推理关系模型、严格 sidecar codec、synthetic 示例与真实失败回放。没有接入生产 writer/runtime，没有修改任何原有文件。

## 文件与行为

新增源码 `src/foreign_trade_geo_agent/core/draft_explanation_contract_v3.py`，新增测试 `tests/draft_explanation_v3_fixtures.py`、`tests/test_draft_explanation_contract_v3.py`。其余新增产物全部在本目录。

- [audit.md](audit.md)：v2 parser / sidecar / prompt / writer projection 审计及 A/B/C/D 分类。首个阻断是 explanation parser 的 `EXPLANATION_PART_DEPTH`，实际 Validator 未运行；CL33 标注错位和 S4 无证据的数量比较另列。
- [design.md](design.md)：证据引用→采购决策变化及因果理由→适用边界及认知状态→责任主体/验证材料/下一步决定。保留 buyer_implication、non_applicability、verification_action；不以词数或关键词授予 PASS。
- [prompt-v3-proposal.md](prompt-v3-proposal.md)：采购推理链指令和两个英文 Bad/Good 正例。仅设计文档，未注入生产材料，未构造真实请求。
- [explanation-sidecar-v3.json](explanation-sidecar-v3.json)：新增独立版本，保留 claim/section/selected refs、candidate_hash、text_sha256，增加 decision_object、boundary_type、verification_owner、verification_artifact 及显式关系记录。candidate_hash 绑定确切 native candidate UTF-8 字符串，text_sha256 绑定对应解释正文；同时绑定 selection、snapshot 和 Plan。
- [synthetic-candidate.json](synthetic-candidate.json)、[synthetic-article.md](synthetic-article.md)、[synthetic-check.json](synthetic-check.json)：12 个采购推理链，结构 PASS，状态只有 `PENDING_SEMANTIC_REVIEW`；semantic_approved 和 production_authorized 恒为 false。
- [replay.json](replay.json)：原始真实 v2 envelope 按原字节走原 parser，继续 `REJECTED / PREFLIGHT_RESPONSE_INVALID`，Validator/Finalizer NOT_RUN。v3 严格 codec 另拒绝没有 v3 关系 sidecar 的旧 envelope，错误 `V3_SIDECAR_INVALID`；没有把 schema 不兼容描述成 v3 已完成旧文语义验证，没有迁移、修复编号或延长旧正文。

v3 复用不变的 selection validation、native specification/evidence inspection、章节 selected-only routing、direct-fact coverage、budget 和 explanation reservation。正文必须与显式关系的受控表达完全一致；sidecar 单独加上 actor/artifact 标签不能替正文提供缺失的采购链。严格 JSON codec 拒绝未知字段、重复 key、NaN、越界内容、错误版本或审批字段；失败诊断不携带候选/供应商原文。

## 实际测试

使用 `.venv/Scripts/python.exe docs/seo-draft-contract-v3-design/run_tests.py <label> [modules...]`。Runner 使用标准库 unittest；完整回归通过 `discover(tests, pattern='test_*.py', top_level_dir=repo)` 加 verbosity=2 执行，完整日志落盘。测试进程及 Python 子进程使用外网 socket/DNS guard；本机 loopback 测试可运行。

| 验证 | tests | failures | errors | skipped | exit code |
|---|---:|---:|---:|---:|---:|
| 首次 red：新测试尚无 fixture/module | 1 loader test | 0 | 1 | 0 | 1 |
| 新增 `tests.test_draft_explanation_contract_v3` | 20 | 0 | 0 | 0 | 0 |
| 相关模块回归 | 96 | 0 | 0 | 0 | 0 |
| 完整回归（包含新增测试） | 1998 | 0 | 0 | 0 | 0 |

首个 red 是预期的缺失离线模块/fixture 导入错误，保留 [red.json](red.json) 和 red.log；它不是成功测试。最终运行见 [green-1.json](green-1.json)、[related.json](related.json)、[full-regression.json](full-regression.json) 及同名 .log。完整回归实测 459.821 秒。启动时出现既有 Starlette/httpx 弃用提示，CLI 拒绝路径和 asyncio 调试输出不构成 unittest failure/error。

相关模块实际范围：test_draft_explanation_contract、test_draft_contract_v2、test_draft_selection_contract、test_seo_draft_v2_flash_preflight、test_draft_prompt_contract、test_flash_draft_replay。

新增测试覆盖完整链、多事实、unknown 边界；limitation/action-only、关键词堆砌、无验证主体、unknown 写成失败、未选事实、candidate/context/body hash、claim/section/premise/quote 绑定、覆盖/重复、正文关系不一致、错配 parsed spec、原生 reservation、严格 codec 和真实失败回放。

## 完整性与外部动作

[baseline-sha256.json](baseline-sha256.json) 在任何代码修改前保存 2,586 个既有非 ignored 文件的 SHA256；[preservation.json](preservation.json) 在完整回归后再次核对：**changed_files=[]**，原有生产文件变化数 **0**，旧 sidecar、Gate、Validator、v2、历史冻结包及实验原文全保留。仓库原有 24 个 tracked 修改及原有 untracked 文件没有被覆盖或丢弃。

设计目录以外只新增上述 3 个源码/测试文件，无意外新增文件。新增代码 hash 见 [new-code-sha256.json](new-code-sha256.json)，产物 hash 见 [artifact-sha256.json](artifact-sha256.json)。[static-review.json](static-review.json) 记录 core 没有 outward dependencies，其他生产文件没有引用 v3 模块。

原始 v2 model-output SHA256 回放前后均为 `ece11a7e83225e5a2e4d449b2a8621f9b759aa496b0faefdc45a3622ff8996d6`。

本轮真实 API 调用 **0**、DeepSeek 请求 **0**、真实 WordPress 调用 **0**；测试外部网络尝试 **0**。无爬站、远程 draft、发布、部署、commit/push，未读取凭据、未运行 opt-in live/integration scripts。完整回归中的本地服务/fake transports 不属于真实供应商调用。

## 限制

这是采购推理**结构**的离线原型，受控表达便于审核，不证明任意自然语言的真实含义。结构完整但因果错误、引用不相关或槽位填充空泛，仍可能需要人类发现并拒绝。常见 unknown/failure 与泛化措辞仅作为保守拒绝诊断，可能误报或漏报，绝不作为正向语义证明。当前仅支持 unknown 和 condition_change；观察到真实失败的证据模型未扩展。

S4 历史“样本数量不同”问题保留在旧输出与审计中；新的 synthetic 链围绕 measurement decision rule 表达采购影响，没有改写历史结果。离线正例不构成真实模型行为改善的实验，也未验证模型生成受控关系格式的稳定性。

每个 PASS 仍需人工核对证据相关性、因果机制、unknown/false、适用范围、责任分配和下一步决定。合约未赋予人工批准、商业验收或生产执行权限。
