# SEO Draft Explanation Contract v3 Integration

最终状态：**OFFLINE_V3_INTEGRATION_READY**。

本轮完成隔离的 v3 离线实验链；synthetic candidate 的状态只有
`PENDING_SEMANTIC_REVIEW`，`semantic_approved=false`、
`production_authorized=false`，仍需人工语义审核。未验证真实模型是否遵循 v3。

## 新增文件与实现

- `src/foreign_trade_geo_agent/workflows/draft_contract_v3_experiment.py`：有界、无 I/O
  的实验 workflow，输入已解码的 Selection Artifact 和 synthetic envelope，逐步生成
  不可变 JSON 快照。不接受 Writer、transport、审批决定或交付对象，不注册 runtime。
- `tests/test_draft_contract_v3_experiment.py`：23 项集成/产物测试，涵盖完整链、拒绝路径、
  权限边界、原生兼容、落盘重放、防覆盖及失败诊断脱敏。
- 本目录新增审计、架构说明、本地 create-only artifact driver、受外网 guard 保护的
  unittest runner，以及实验输入、输出、中间状态、测试日志与完整性记录。

既有生产 Writer、Validator、Parser、Gate、runtime、v2、storage codec 和 native JSON
schema 均未修改。所有本轮新增文件都位于上述两个源码/测试路径或本目录。

[audit.md](audit.md) 在源码/测试修改前完成，回答了 v2 入口、v3 调用方式、native schema
及兼容边界。详细结构见 [architecture.md](architecture.md)。

## 实验链与正例结果

```text
Selection Artifact（原有 storage codec 解码）
  -> 原有 v2 Writer Projection（selected-only）
  -> 独立 Prompt-v3 material
  -> Synthetic LLM envelope
  -> v3 sidecar codec / hash prechecks
  -> 原有 Native Parser（仅 candidate JSON）
  -> 完整 v3 Explanation Contract
  -> 原有 Native Validator 的未批准 candidate review 检查
  -> PENDING_SEMANTIC_REVIEW / human review required
```

现有 `inspect_explanations_v3` 必须接收已解析的 specification，且内部复用原生校验。
因此 v3 检查分为 parser 前的格式/哈希检查和 parser 后的关系/正文检查；最后另行记录
一次原生校验结果。没有改 contract 来规避这个依赖，也没有声称完整 v3 检查先于解析。
未调用需要人工批准的 admitted DraftItem finalizer，未构造获准交付的 DraftItem。

正例含 **6 sections、12 explanation chains、38 claims、20 blocks、25 个独立 selected facts**。
每条链均包含 selected_fact_refs、decision_object、boundary_type、verification_owner、
verification_artifact，并在正文中实现 Evidence → Decision impact → Boundary condition
→ Verification action。正文、claim/section、source quote、selected refs 和各项 hash 均绑定。

candidate 保持 `{ "draft": ... }` 原生结构及既有 proposal metadata；所有 v3 关系字段只在
独立 sidecar 中。注入 v3 字段到 native claim，即使重算 hash，仍被原生 parser 拒绝。
没有补写、修复、迁移或重新编号旧模型输出。

| 验收项 | 离线结果 |
|---|---|
| Evidence 与上下文绑定 | ✅ |
| Selection Contract | ✅ |
| Writer Projection，未选事实/审计理由隔离 | ✅ |
| Explanation Contract v3 | ✅ 结构完整 |
| Experimental pipeline / 中间状态持久化 | ✅ |
| Native parser compatibility | ✅ |
| Native validator review compatibility | ✅ |
| 真实模型生成稳定性与语义质量 | 尚未验证 |

独立落盘核验见 [acceptance.json](acceptance.json)。失败实验 wrapper 的状态为
`OFFLINE_ONLY`，非空 errors 和 accepted=false 表示拒绝；成功仅进入待人工审核。
原生/历史诊断的既有拒绝状态保留在各自回放记录中。

## 实验产物

- [experiment-config.json](experiment-config.json)：contract_version、selection_hash、
  snapshot_hash、plan_hash、candidate_hash、sidecar_hash、envelope_hash、两项 false 授权标志。
- [synthetic-input.json](synthetic-input.json)、[selection-artifact.json](selection-artifact.json)：
  可通过原有 storage codec 恢复的完整 synthetic 验证输入和 Selection Artifact。
- [writer-projection.json](writer-projection.json)、[prompt-v3-material.json](prompt-v3-material.json)：
  原有 projection 与新增 v3 指令；不是供应商请求包。
- [synthetic-output.json](synthetic-output.json)、[synthetic-candidate.json](synthetic-candidate.json)、
  [synthetic-article.md](synthetic-article.md)：保留完整 envelope、独立 native JSON 和可读正文。
- [v3-sidecar.json](v3-sidecar.json)、[v3-contract-result.json](v3-contract-result.json)、
  [native-validation-result.json](native-validation-result.json)、[pipeline-result.json](pipeline-result.json)。
- [stage-index.json](stage-index.json) 与 `stages/01-...` 至 `stages/08-...`：所有步骤独立快照及 SHA256。
- [replay.json](replay.json)：原始 v2 envelope 和 frozen-v1 原字节的拒绝回放。

candidate_hash 绑定 canonical native candidate 的 UTF-8 字节，不包含外层 envelope 或 sidecar；
sidecar_hash 绑定完整 canonical sidecar。验证阶段不自动重算、修复这些输入绑定。
driver 写入前检查全部目标；相同内容可核验重放，已有内容不一致则拒绝覆盖。

## 拒绝与权限测试

以下均已通过，详细断言见新增测试及 [new-hardened.log](new-hardened.log)：

| 输入/行为 | 结果 |
|---|---|
| 缺少 v3 sidecar | 拒绝 |
| sidecar 引用本节未 selected 的 fact | 拒绝 |
| 正文无 decision chain，即使同步更新 hash | 拒绝 |
| verification_owner 为空 | 拒绝 |
| unknown 被写成 failure，即使正文/sidecar 同步绑定 | 拒绝 |
| sidecar digest 或 selection/snapshot/Plan/candidate hash 错误 | 拒绝 |
| candidate 内容修改但未更新绑定 | 拒绝 |
| 原始 v2 envelope | 原 parser 仍 PREFLIGHT_RESPONSE_INVALID；v3 不接纳旧 envelope |
| frozen-v1 输出 | 原 native 仍 DETERMINISTICALLY_REJECTED，保留 CLAIM_BUDGET 等原始问题 |
| semantic_approved=true 或 production_authorized=true，含两者同时 true | 拒绝 |
| sidecar 擅加审批字段、非 boolean false 授权标志 | 拒绝 |
| native 校验有错误 | 不被 sidecar 的结构信息覆盖 |
| 失败诊断附带自由文本标题/详情 | 实验快照移除自由文本，仅保留编号/错误类别 |

sidecar 的 PASS **只代表结构完整**。它不产生 semantic approval、生产授权或人工审核记录。

## 实际测试与失败记录

实际使用 `.venv/Scripts/python.exe docs/seo-draft-contract-v3-integration/run_tests.py <label> [modules...]`。
Runner 使用标准库 unittest；全回归实际执行 discover(tests, pattern='test_*.py')、verbosity=2。
每次计数与 exit code 保存到同名 JSON，逐项结果保存到同名 log。

| 验证 / 文件前缀 | tests | failures | errors | skipped | exit code |
|---|---:|---:|---:|---:|---:|
| 初始 red，模块尚未创建 / red | 1 loader | 0 | 1 | 0 | 1 |
| 第一版新增测试 / green-1 | 20 | 0 | 0 | 0 | 0 |
| 增加落盘重放测试 / new-final | 22 | 0 | 1 | 0 | 1 |
| 首次相关回归 / related | 116 | 0 | 1 | 0 | 1 |
| 修复输入编码后的新增测试 / new-fixed | 22 | 0 | 0 | 0 | 0 |
| 修复 loopback guard 后的相关回归 / related-final | 116 | 0 | 0 | 0 | 0 |
| 最终新增测试，含诊断脱敏 / new-hardened | 23 | 0 | 0 | 0 | 0 |
| 首轮完整回归，启动于脱敏补充前 / full-regression | 2020 | 0 | 0 | 0 | 0 |
| **最终源码版本完整回归 / full-final** | **2021** | **0** | **0** | **0** | **0** |

三个早期 error 均有留档，不能视为当时通过：

1. red 为新实验模块尚未实现导致的导入错误。
2. new-final 暴露 driver 用通用 asdict JSON 编码 datetime，而原 storage decoder 要求 UTC `Z`。
   已改为复用原 `_encode`，再由原 `_decode` 成功重放。初始不合格 synthetic 输入保留为
   `initial-synthetic-input.codec-rejected.json`，仅用于失败诊断，不作为最终 pipeline 输入。
3. related 的 strict guard 阻止了 Windows asyncio 内部 socketpair 的 loopback connect。
   相关/完整回归允许 loopback，仍禁止全部外网；新增实验测试继续 strict 禁止全部网络。
   被阻断的那一次是内部 loopback，不是供应商 API 请求。

相关 116 项实际范围：test_draft_explanation_contract_v3、test_draft_explanation_contract、
test_draft_contract_v2、test_draft_selection_contract、test_seo_draft_v2_flash_preflight、
test_draft_prompt_contract、test_flash_draft_replay。

最终完整回归实测 **459.765 秒**，见 [full-final.json](full-final.json)、
[full-final.log](full-final.log)、[full-final.console.log](full-final.console.log)。
既有 Starlette/httpx 弃用提示、asyncio debug 和 CLI 预期拒绝输出均未造成 unittest failure/error。
本轮之后没有继续修改源码或测试。

## 完整性与外部动作

[baseline-sha256.json](baseline-sha256.json) 在任何源码/测试修改前记录 **2,615** 个既有
non-ignored 文件。最终 [preservation.json](preservation.json) 核对 **changed_files=[]**、
unexpected_new_files=[]，原有 24 个 tracked 修改及所有既有 untracked 文件均保留。
生产源码、本次前已存在的 v2/v3 文件、历史输出和冻结实验包的 SHA256 变化数均为 **0**。

[new-code-sha256.json](new-code-sha256.json) 记录四个新增 Python 文件的最终 hash，
在最终回归前锁定并在回归后复核。[static-review.json](static-review.json) 记录新 workflow
无 adapter/storage/network 依赖、其他生产文件无实验入口引用、runtime 未注册。
[artifact-sha256.json](artifact-sha256.json) 记录最终本目录产物 hash（排除自身）。

原始 v2 output hash 回放前后均为
`ece11a7e83225e5a2e4d449b2a8621f9b759aa496b0faefdc45a3622ff8996d6`；
frozen-v1 output hash 回放前后均为
`880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747`。

真实 API 调用 **0**、DeepSeek 请求 **0**、真实 WordPress 调用 **0**。
最终回归的外网 guard 阻断尝试 **0**，loopback events **1,955**（本地 HTTP 测试和内部
socketpair 等；不是真实 API 调用）。guard 由 Python 子进程继承，新增实验测试无网络事件。
没有爬真实客户站点、真实远程 draft、发布、部署、commit/push，也没有读取凭据或执行
opt-in live/integration checks。完整回归中的供应商/WordPress 行为使用既有 mocks/fakes。

## 剩余限制与停止点

这是 synthetic 的结构、绑定、路由和 native review 兼容验证。受控正文表达便于审核，
不能证明事实相关性、因果正确性、采购价值或任意自然语言的含义；这些仍由人判断。
本轮没有生成真实模型响应，也未证明模型会稳定遵循 v3 或改善真实文章质量。

离线链已完成。停在人工语义审核与独立真实请求授权之前，等待下一次明确授权。
