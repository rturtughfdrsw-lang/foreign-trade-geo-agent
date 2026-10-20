# 最小签核 host/client：TEST 实现与生产部署缺口（2026-10-09）

这是开发/验证报告，不是审核授权或 Windows 部署验收。**仅单进程隔离 TEST 可运行；生产入口锁定拒绝。**真实 O1–O6 和七项决策继续 NOT_REVIEWED；writer=0。未创建账户或生产 key，未修改 ACL、服务、注册表或执行策略，未调用外站、付费 LLM 或 WordPress，未 commit/push/reset/clean。

## A. 实际实现与复用

已读取 AGENTS.md、single-admin design、Windows deployment runbook 和 resume report，以实际代码为准。当前没有启用的 Superpowers skill，未虚构其调用。复用 `EvidenceReviewReceipt`、`ReviewPrincipal`、`VerifiedReviewRegistration`、`AuthenticatedEvidenceReviewLoader`、`RegisteredEvidenceReviewLoader` 和两层既有 preflight。receipt cache、HistoryStore、artifact codec、Draft API/schema、CLI/Web/runtime 均未改动。

新增最小应用层闭环：

1. 公钥验签使用 Windows BCrypt，固定 RSA-3072、exponent 65537、SHA-256、PSS salt=32；仅接受严格 DER rsaEncryption SPKI 和 384 字节 proof。没有算法/key URL协商、私钥加载或密码学回退。
2. host-only `BCryptRsaPssSigner` 消费独立 host 已持有的 native private-key handle，调用原生 PSS 并用固定公钥复验。它不创建、发现、打开、导出或持久化私钥。TEST fixture 用临时 native key handle 实测此适配器；生产 current-user **NCrypt named-key custody/provider 尚未实现**，不能把 BCrypt handle 当成 runbook 的 named CNG key。
3. `EvidenceReviewHost.seal(target, record, confirmation=..., session=...)` 从可信会话 port 获取调用者身份；仅固定审核身份可以进入。调用者明确提交原始记录内每项 verdict/reason，原 loader/preflight 在签名前验证全部批准、完整冻结目标、输入、scope、版本、用途与义务。缺项、NOT_REVIEWED、REJECTED 或空 reason 拒绝，未自动填写或批准。reviewer_id 只与可信身份核对，绝非身份来源。
4. 人工最终确认绑定 `SHA256(CONFIRM-domain + canonical frozen bytes + original record bytes)`。reviewed_at 不得未来或超过五分钟确认窗口；注册/审计使用 host 当前 UTC。签名是 `RECORD-domain + original record bytes`，记录内签入完整冻结目标与 DraftInput digest，消费端再精确重建验证。确认摘要本身不证明真人操作，需要后续 owner-local 审核工具。
5. host query 是独立的只读入口；仅固定 Agent 会话可查。拒绝请求中的 reviewer_id、action、approved 等额外字段。注册、撤销及署名不暴露为 Agent query RPC；撤销要求授权审核会话和明确 reason。receipt 只在 authority 原子注册成功后返回；ID 不复用、撤销不复活。
6. `EvidenceReviewClient` 同时实现既有 authenticator 和 current registry ports，仅持有两把固定公钥及只读 transport/clock。每次重新读取当前 key/grant/review 状态；使用新的32字节随机 challenge、单独 registry key/domain、认证 server SID、exact schema、五秒响应窗口和完整记录/proof/frozen摘要绑定。没有批准缓存。进程内拒绝 revision/time 回退。
7. `production_preflight()` 当前**始终拒绝**且没有用户可注入参数、环境开关或 verified=true 标记。`isolated_test_preflight` 只接受 TEST client 并仅返回 SYNTHETIC_GREEN。新 core authority port 是现有签核状态的原子读取/注册/撤销边界，新增它是为了避免非原子读取授权与撤销状态；没有另建审核记录或业务 schema。

## B. 信任边界与证明范围

| 边界 | 单进程 TEST 能证明 | 本轮不能证明 |
| --- | --- | --- |
| 非对称密码学 | 真 BCrypt PSS、原始字节/domain/公钥绑定，.NET 双向互操作 | 独立账户私钥 custody、named-key 非导出与 Agent 无署名能力 |
| 调用者与服务身份 | 应用接口只取 session port；payload reviewer_id 不授权；server身份不符拒绝 | Windows token impersonation/revert、真实 client/server SID、pipe劫持/远程访问防护 |
| 当前权限/撤销 | 当前已撤销/过期/缺状态拒绝；错误binding和nonce重放拒绝 | 真实受保护 state、跨进程一致性、断电事务、重启revision/UTC高水位、备份回滚检测 |
| 人工审核 | 缺明确全项 verdict/reason 或冻结确认时不签署 | 真人人工阅读/输入/最终确认及真实业务授权 |
| composition | 缺根拒绝；生产不能注入 TEST ports/锚；TEST proof在生产domain下无效 | 受保护代码、解释器/依赖、锚安装、effective access及ACL完整父目录链 |
| 时钟 | TEST异常、naive UTC、回拨和慢响应拒绝 | 当前Windows时钟可信、认证时间来源、同步期限及跨重启回拨保障 |

TEST sessions 是 object-token 映射，authority 是内存事务替身，transport 是 loopback 函数，clock 是受控时间。它们**没有模拟ACL，也不构成跨账户验收**。签名/SQLite receipt 是实际操作，其他根明确为测试替身。测试密钥仅临时内存存在，私钥未导出或写入文件；TEST/PRODUCTION 和 RECORD/REGISTRY/CONFIRM 的domain全部区分。公钥字节本身没有“测试出生标志”，生产安全来自受保护固定登记及拒绝caller提供key；当前没有任何可接受TEST key的生产加载入口。

包内JSON、receipt SQLite、报告和验证JSON不提供授权。host state port 要求保护状态原子snapshot、commit时重新核验权限及expected revision、追加actor/time/action/reason/digest审计、不可复用ID、不可恢复撤销及持久UTC guard。本轮只有其测试实现，**没有生产持久化authority DB**。当前两把公钥固定；registry key 更换/撤销还需受保护锚的更新/停用流程，不能由待验response自宣称解除撤销。

系统管理员/SYSTEM、同审核账户恶意代码、可写验证程序、供应链替换和全盘快照回滚不受此本机模型保护。进程内高水位不等于跨重启/外部追加日志锚。

## C. 本轮文件与工作区安全检查点

仅新增以下文件，所有既有文件保持原字节：

| 文件 | 用途 |
| --- | --- |
| `src/foreign_trade_geo_agent/core/evidence_review_authority.py` | 原子当前授权/注册/撤销 ports |
| `src/foreign_trade_geo_agent/adapters/evidence_review_cng.py` | 严格 SPKI + BCrypt 公钥PSS验证 |
| `src/foreign_trade_geo_agent/adapters/evidence_review_signing.py` | host持有private handle的PSS适配器 |
| `src/foreign_trade_geo_agent/adapters/_evidence_review_protocol.py` | 有界协议、固定锚、签名domain和可信session/transport契约 |
| `src/foreign_trade_geo_agent/adapters/evidence_review_host.py` | seal/query/revoke应用接口及签名前验证 |
| `src/foreign_trade_geo_agent/adapters/evidence_review_client.py` | 公钥-only、fresh response/current-state消费 |
| `src/foreign_trade_geo_agent/evidence_review_composition.py` | 锁定生产入口及显式TEST装配 |
| `tests/evidence_review_host_fixtures.py` | 临时keys和明确TEST身份/state/transport |
| `tests/test_evidence_review_host_client.py` | 31项实际密码学/协议与拒绝边界测试 |
| 本报告及同名verification JSON | 结果、文件保留证据和部署缺口；无授权能力 |

分支 `feat/live-site-analysis`，HEAD `fedcb3b7a8ffb3e3480c9807d5831ddd89dfc148`。起始逐文件Git状态229项：79 modified、149 untracked、1 deleted，没有staged项。按目录为README 1、docs 105、scripts 4、src 55、tests 64。现存360个非忽略文件已记录SHA-256，最终全部逐字节一致；既有删除 `tests/test_history_migration_v1_to_v2.py` 保留。旧变更涵盖 planning/numeric/comparison/core-contract、workflow/adapters、storage/history migration、CLI/runtime/Web、review packages/部署文档及测试；本轮没有把它们混入新增组件修改。仅新增11文件，最终240项（79 modified、160 untracked、1 deleted），无staged项；逐字节复核见verification JSON。

建议的后续安全检查点（未执行commit或归档）：owner先核对本轮baseline、完整逐文件status及所有untracked review packages；独立备份到新目录并恢复核对hash，不含.env/私钥；按依赖顺序评审既有core/schema+storage、workflow/adapters、UI/CLI/runtime、离线证据/签核持久化，再单独评审本轮host/client和TEST。每组保留针对性测试与最后整体回归证据。特别检查既有migration删除、新migration、History schema与CLI/Web路由，以及所有审核包未签状态。提交之前再做secret扫描和tracked/untracked差异核查；不得把受保护授权根、私钥、.env或.data日志打入提交。本轮只记录检查点方案，未改Git历史。

## D. 正负例测试

31项新测试实测：PSS proof=384字节；签名/验签与.NET RSACng双向互操作；receipt落盘/读回；每次current重查；原生Draft拒绝且writer=0。负例包括伪造/错误key/错误domain/原始字节变化；mock未授权调用/冒用reviewer_id/错误server身份；缺项/非批准/空reason；确认和target/Input错误binding；task/三个版本/span/context/purpose变化；review/key/grant撤销、过期、缺注册、服务/state失联；UTC异常/回拨、慢响应、旧challenge响应重放、revision回退；exact-schema/重复字段/超限；注册失败和模拟并发grant撤销；生产拒绝TEST proof、key/port注入及synthetic开关。模拟身份负例只证明应用接口拒绝逻辑。

初始组件可用性RED测试实际1 error（模块未实现）；实现后31项通过，未删有效断言或绕过安全检查。最终针对性与完整日志、退出码、时间和hash见verification JSON。

## E. 完整回归与真实冻结对象

针对性实际命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_evidence_review_host_client tests.test_evidence_review_windows_inventory tests.test_persisted_evidence_review tests.test_evidence_sufficiency_preflight tests.test_first_party_excerpt_capacity tests.test_first_party_planning tests.test_content_draft_core tests.test_content_draft_workflow tests.test_history_serialization tests.test_sqlite_history_store tests.test_runtime tests.test_cli -v
```

已观测 **222 tests / 17.737s / OK / exit 0**。

完整回归：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

本轮实际 **1465 tests / 228.138s / OK / exit 0**，相对原1434项增加31项host/client测试，无skip。结果由本轮完整进程与日志观测，未用历史结果替代。日志在 `.data/evidence-review-host-client-20261009/`，未调用verify live/integration脚本。日志末尾旧demo launcher负例有端口占用等预期控制台输出，unittest总结仍是OK；不能只用日志最后几行推断测试结论。

本轮真实冻结对象本地读回：task `T-P3-SIX-RELATIONS-ATTRIBUTED-EXCERPT-v2`，版本 `(2,2,1)`；frozen SHA256 `146cd906b1fce15a21a6f26f50224e09182a1d0b7ed934df1e7ccba826972c1d`；DraftInput `a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2`。六义务/七决策全部NOT_REVIEWED，reviewer/time=null，生产preflight REJECTED，native Draft invalid_input、writer_calls=0。没有给真实包生成record/proof/注册。

## F. owner真实部署前置条件与剩余实现

原runbook的系统步骤继续由owner另行执行。本轮不执行这些步骤，也不声称有可启动生产service/signer的命令。

1. owner核准独立标准reviewer与Agent账户、保护Verifier/Anchor/AuthorityState及全部父目录/runtime/依赖；不用editable venv或可写仓库作可信加载源。实际跨账户测effective access、private key打开/署名拒绝、代码/锚/state的替换和写权，不能只查看ACL清单。
2. 补**native Windows authenticated local IPC adapter**：认证client token impersonation/SID且finally revert，校验server PID/token/SID，拒绝remote/anonymous，处理pipe squatting、首实例/ACL、disconnect、消息边界、并发、读/连接timeout和资源上限。测试替身不能启用生产入口。
3. 补**current-user NCrypt named-key provider**：只在审核账户打开owner登记的已存在非导出Signing key，固定provider/公钥fingerprint并核对实际账户及key properties；禁止自动生成/覆盖/遍历用户key。BCrypt TEST signer不负责此步骤。两把生产key需在独立TEST账户验收后，由owner本人生成/核对；本轮没有创建或打开生产named key。
4. 补**受保护durable authority state**：实现新port的原子snapshot和register/revoke/audit、revision CAS、UTC高水位及key/grant当前状态；service重启、崩溃、断电恢复和备份回滚不能恢复撤销。需要外部检查点才能证明完整磁盘回滚；未知恢复状态拒绝。receipt DB始终只是缓存。
5. 补**可信clock适配器**及部署证据：核准认证时间链或独立校准、最大偏差/同步失效期限、失联和回拨拒绝、标准账户无修改时间特权。进程datetime.now/Running W32Time不可直接当可信时钟。
6. 补**owner-local人工审核工具**及受保护composition安装适配器，固定审核SID/AgentSID/项目/task/purpose、两把锚和所有根；工具显示完整目标/每项决策/最终原始字节，owner实际逐项填写和确认。任何缺根仍拒绝，不接受部署verified=true、mock身份或环境变量开Gate。生产factory本轮锁定，解锁必须另行代码审查及实际部署验收。
7. 独立TEST账户/root/key先验上述Windows边界、服务退出、重启、过期/撤销/旧备份/旧response重放，再安排真实业务O1–O6逐项审核。真实业务签核、商业Draft验收和WordPress权限分别授权，不能继承测试结果。

## G. GO / NO-GO

| 验收对象 | 结论 |
| --- | --- |
| 临时密钥、单进程TEST host/client→receipt→preflight | GO，仅SYNTHETIC_GREEN；身份/state/clock/IPC均为TEST替身 |
| 生产host/client软件部署 | NO-GO；上述native identity/key/state/clock/composition适配器未完成，生产入口拒绝 |
| 真实Windows跨账户隔离 | NOT ACCEPTED / NO-GO；未创建独立账户、未改ACL或实测跨账户有效权限 |
| 真实业务签核 | NOT AUTHORIZED / NO-GO；O1–O6、七决策全部NOT_REVIEWED |
| 正式Draft及WordPress | NO-GO；writer=0，无本轮授权或外部调用 |

生产根不成立时停止在组件和缺口方案，未使用弱认证凑GREEN；未扩展GEO、UI或无关功能。
