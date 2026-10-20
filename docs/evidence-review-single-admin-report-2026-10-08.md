# Evidence Sufficiency Gate：单管理员持久化 preflight 本轮报告

本报告只记录离线实现和测试，不是 O1–O6 审批记录。真实六项均 NOT_REVIEWED；没有生成正式 Draft、真实签名或注册批准。部署设计见 [single-admin-design](evidence-review-single-admin-design-2026-10-08.md)，人工材料沿用 [owner-obligations](review-packages/evidence-sufficiency-2026-10-08-trusted-preflight/owner-obligations.md)。

## A. 当前实现与差距

已读取 AGENTS.md、README.md、上轮 preflight 报告、owner-obligations、原 excerpt-v2 包和实际代码。开始工作时分支 `feat/live-site-analysis`，HEAD `fedcb3b7a8ffb3e3480c9807d5831ddd89dfc148`，逐文件 porcelain 状态 216 项。最终状态 224 项，仅新增本轮 8 文件；原 216 项全部保留。开始时记录的 347 个已存在、未忽略文件逐字节不变，HEAD 不变；没有覆盖既有 tracked/untracked 修改或恢复已有删除。最终证据及日志 SHA-256 见本轮 verification JSON。

上轮已有严格 review contract、冻结目标 codec、AuthenticatedEvidenceReviewLoader、EvidenceSufficiencyPreflight，以及 tests-only 的 synthetic HMAC authenticator。现有 HistoryStore 是业务历史，不是签核权限源。本轮通过新模块复用原 loader/preflight；没有改原模块或业务 History schema。实际 CLI、runtime、Web composition 没有接入 preflight、signer 或 registry：入口仍是显式 Python 调用和离线单测，不存在生产 owner 签署命令。

数据流：不可信 SQLite receipt → 完整 canonical 冻结对象一致性 → 原 loader 验原始 record/proof、当前身份/权限、时间及所有义务 → 包外当前注册源验 record/proof/frozen 摘要及身份/任务/版本/撤销 → 原 preflight 全量覆盖校验 → 仅返回状态。这里的 authenticator、当前 registry 都必须由受保护 composition 注入可信实现；本轮没有这样的生产实现。

真实审核目标仍是 `T-P3-SIX-RELATIONS-ATTRIBUTED-EXCERPT-v2`，task/Plan/evidence 版本 `(2,2,1)`，P3、R1→C1、一个 operation、六义务七 span。冻结目标 SHA-256 为 `146cd906b1fce15a21a6f26f50224e09182a1d0b7ed934df1e7ccba826972c1d`；DraftInput 为 `a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2`。模板六个 verdict 和七个 decision 均 NOT_REVIEWED。原生 Draft 仍 FIELD_CONTRACT、writer=0。

## B. 最小信任模型及局限

生产方案是单项目、一个独立 Windows 审核账户/本地小服务，Agent 在另一个受限账户运行。owner 通过独立 Windows 交互登录建立身份；私钥、固定公钥/owner 绑定、task/purpose 权限、当前注册/撤销状态、验证代码与配置，都必须位于 Agent 无写权的边界。软件私钥可由独立审核账户的 current-user DPAPI 保护，但同 Agent 账户的 DPAPI/HMAC 不证明人工 owner 审批。固定 trust anchor 不能从包或 receipt 自行导入。

当前进程与仓库 owner 是同一 Windows 用户，当前 token 非管理员；未配置独立审核身份根。没有安装签名依赖、创建账户/密钥/服务或修改 ACL，也没有查找/使用用户私钥。缺少可信来源时停止于设计和端口消费实现，没有以可编辑 JSON、SQLite flag 或 tests-only HMAC 代替真实认证。

威胁与响应：修改 JSON、审批字段、record/proof/digest/frozen 对象、恢复旧 receipt 备份、冒用审核者、跨项目/任务或复用 EXPLAIN 许可、遗漏义务/decision、输入/版本/span 变化、过期、撤销、旧响应或身份服务不可用，全部拒绝。每次检查 fresh challenge、当前状态和最多 ±5 秒响应时间；回显 nonce 本身不提供认证，服务身份/IPC 响应真实性属于强制可信端口前置条件。registry 禁止 ID 复用、revival 和 revision 回滚；consumer 的 revision 范围校验本身不证明单调性。

SQLite 仅为可篡改凭据缓存：固定 schema/trigger、只读 reader、重复 ID 拒绝、字节/SQL 大小限制、100,000 VM steps 预算、写事务防 schema 校验到 INSERT 之间的并发替换。触发器不是授权来源。合法 ACTIVE 记录的重复只读检查是幂等的；没有 Draft 一次性消费语义。被撤销/替代/过期的旧记录及旧注册响应不能复活。

残余风险：同审核账户恶意代码、管理员/SYSTEM、受保护服务/验证代码被替换、系统时钟或完整服务状态回滚。不可信进程可伪造注入端口对象，因此代码/composition 与 trust anchor 必须一并受保护。服务应保留单调 revision 和 last-seen UTC、拒绝回拨，并接受重启/备份恢复验收；抵御本地管理员/完整磁盘快照回滚需要额外独立设备或外部日志锚。本轮没有实现或验证这些部署保证。

## C. 具体改动

全部是新增文件；原 public API、schema/codec、普通 P/S、EXPLAIN、comparison、历史 artifacts 均未改。

| 文件 | 用途 |
| --- | --- |
| `src/foreign_trade_geo_agent/core/evidence_review_registry.py` | 有界 receipt、经过外部认证的当前注册 DTO、reader/registry/persisted loader ports；不引入具体 I/O |
| `src/foreign_trade_geo_agent/storage/evidence_review_receipts.py` | 独立 append-only SQLite 缓存，拒绝覆盖/迁移/错误 schema，关闭连接及执行资源护栏 |
| `src/foreign_trade_geo_agent/adapters/registered_evidence_review.py` | 重用原 authenticated loader，再验当前注册、fresh response、身份/对象/字节/生命周期绑定 |
| `src/foreign_trade_geo_agent/workflows/persisted_evidence_review.py` | 接收 target/review_id，composition 提供 clock/ports；默认拒绝 synthetic 和缺根情况，无 writer |
| `tests/test_persisted_evidence_review.py` | 23 项新增离线测试；真实 synthetic HMAC、临时 SQLite、明确仅测试的注册状态 double |
| `docs/evidence-review-single-admin-design-2026-10-08.md` | 当前部署事实、最小身份隔离设计、密钥/信任锚/撤销前置条件和 owner 签核步骤 |
| 本报告及 `docs/evidence-review-single-admin-verification-2026-10-08.json` | 结果、日志摘要和工作区保存证据；不具有审批权限 |

独立代码审查发现不可信 SQLite trigger 可无限执行的问题，已用新增 RED 用例复现后修复，另补事务并发负例。复审无遗留 critical/important finding；独立复审运行 36 项相关测试全部通过。复审不涵盖尚不存在的生产身份/服务部署。

## D. 由 owner 本人逐条审核与签署

目前可执行的是人工核验；目前不能执行真实可信签署。请先打开 owner-obligations，本地逐项比对原文、上下文、source locator、Unicode 零基半开区间、Plan/C1 点位及覆盖索引。O1 的两个连续 span 必须完整重组；O2–O6 各核验一个完整 span。核对虚构品牌声明及仅带归属逐字摘录的范围：不得扩展为工程事实、SEO 效果、自由解释或 EXPLAIN/comparison 授权。每项由本人作出 verdict/reason，未决定的项保留 NOT_REVIEWED。

随后逐项审阅七项 decision：SOURCE_USE、TASK_AND_DEPTH、OFFLINE_PLACEMENT、P_ONLY_CANDIDATE、FROZEN_CONSUMPTION、REVIEW_AUTHORITY、VALIDITY_AND_STORAGE。确认 task/Plan/evidence 版本、完整冻结对象及 DraftInput 摘要；任一关键字段变化必须新审核。人工决定可以作为待签核信息，编辑 UNSIGNED 模板不能形成批准证明。

真实签署前必须先完成：独立账户/设备；验证过的 ACL；owner 人工生成/保管签名 key；独立核对固定公钥指纹与权限；认证 IPC/签名响应；受保护当前注册/撤销及审计事件；可信时钟/恢复验收；仅 owner 可用的交互签核工具。部署设计提供逐步验收条件，本轮没有 signer/service 命令。

这些条件满足后，owner 工具必须展示完整最终记录，经本人交互确认才签名：记录独立 review_id、reviewer、实际 UTC 审核时间、最长 24h 有效期，以及全部义务/decision/任务/版本/frozen/record/proof 绑定；独立服务注册并持久化。不得提供自动填 APPROVED、伪造批量 owner approval 或复用历史 EXPLAIN 许可。owner 撤销时追加 actor/time/reason 审计事件，当前服务状态变为撤销；旧 receipt 不改写，下一次 preflight 拒绝。

## E. 正负例测试

最终针对性命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_persisted_evidence_review tests.test_evidence_sufficiency_preflight tests.test_first_party_excerpt_capacity tests.test_first_party_planning tests.test_content_draft_core tests.test_content_draft_workflow tests.test_history_serialization tests.test_sqlite_history_store tests.test_runtime tests.test_cli -v
```

观察结果：187 tests / 10.840s / OK / exit 0。包含 23 个新增持久化用例、原 13 个 preflight 用例，以及 planning、Draft、codec/history/runtime/CLI 兼容性用例。

正例是明确 unrelated synthetic 材料、真实随机 test HMAC 签名验证、临时 SQLite 重开及仅 tests 内模拟可信当前注册语义；同 ACTIVE 记录两次检查均 SYNTHETIC_GREEN，每次重新验证当前源。生产默认不接纳 synthetic，测试 registry double 不是已验证的生产 IPC。

负例覆盖持久化缺失/错库/重复 ID、修改 record/proof/frozen/审批字段和重算 digest、旧备份撤销重放、旧 nonce/响应时间、注册根缺失/失联/异常、身份/项目/任务/purpose/版本/摘要错绑、跨任务和 EXPLAIN、未审/部分/遗漏、输入/Plan/span/义务变化、权限/key 撤销、过期/无效时钟、字节边界/类型、附加/变造 schema/trigger、无限 SQL 预算及并发 schema 替换。正负例均验证该 P-only 输入的原生 Draft writer=0；没有正式 Draft 或生产批准记录。

调试失败如实保留：初始 TDD 因新增模块未实现为 RED；首次实现测试暴露 Windows SQLite 连接未显式关闭，已修复并增加回归；审查后新增资源负例原实现 5 failures、并发负例原实现 1 failure，修复后上述最终针对性结果通过。日志在忽略目录 `.data/evidence-review-registry-20261008/`。

原冻结包 verifier 再次 PASS：六义务七 span、一个 Change；五个历史 V1 roundtrip PASS；O1–O6 NOT_REVIEWED，Gate NOT_GREEN，native Draft FIELD_CONTRACT，writer=0。

## F. 完整回归

修复后最终命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

实际观察 **1430 tests / 219.909s / OK / exit 0**，相对上轮 1407 增加 23 项。日志 `.data/evidence-review-registry-20261008/full-final-after-review.log`。修复前本轮另跑过 1427 tests / 220.193s / OK，最终验收使用修复后的 1430 项结果。测试输出中的 Demo/端口提示来自已有测试的受控场景，不是本轮启动生产服务或调用 WordPress 的证据。

## G. 下一步及 GO/NO-GO

| 对象 | 结论 | 条件/含义 |
| --- | --- | --- |
| synthetic P-only 持久化 preflight | GO（仅离线 SYNTHETIC_GREEN） | 单测证明消费与拒绝逻辑，不证明真实 owner 身份/注册源 |
| 真实 O1–O6 审批 | NO-GO / NOT_REVIEWED | owner 尚未逐项签核，生产身份/权限/key/service/revocation 根未成立 |
| 商业 Content Draft | NO-GO / writer=0 | 当前未开放正式 writer；未来还需同冻结输入消费、输出全覆盖验证与商业验收 |

下一步只部署并验收上述单管理员信任根/签核服务，再由 owner 实际逐项审核签署并做真实 preflight。之后另行实现同冻结输入 Draft 消费及生成输出覆盖校验，不提前改变普通 P/S、EXPLAIN/comparison 或 WordPress create-only/draft-only 边界。没有付费 LLM、外部网站访问、WordPress、正式 Draft、自动审批、commit 或 push。
