# Windows 单管理员可信签核：中断续作报告（2026-10-09）

本报告是离线审查/验证记录，不是 owner 授权。生产信任根未部署；真实 O1–O6 全部 NOT_REVIEWED，商业 Draft NO-GO、writer=0。本轮停止在系统部署边界，没有创建账户、修改 ACL/服务/执行策略、创建生产 key 或执行真实签核。

## A. Git 状态与恢复现场

读取了 AGENTS.md、README.md、single-admin report/design、Windows inventory 脚本及 deployment runbook，核对实际代码、review packages 和忽略目录日志。分支 `feat/live-site-analysis`，HEAD `fedcb3b7a8ffb3e3480c9807d5831ddd89dfc148`。起始逐文件 `git status --porcelain=v1 -uall -z` 为 **226 项：79 modified、146 untracked、1 deleted**，没有 staged 项。普通 status 折叠目录显示 147 行不能与逐文件数混用。既有删除是 `tests/test_history_migration_v1_to_v2.py`，保持原样。

上轮 Windows 基线 `.data/evidence-review-windows-feasibility-20261008/baseline.json` 的 355 个文件全部 hash 一致、224 条状态均保留；其后新增的脚本和手册解释当前 226 项。两文件内容都完整，脚本和手册 PowerShell 代码块语法可解析；没有发现中断造成的截断。当前基线记录 357 个现存非忽略文件。本轮只修复其中两个交接文件，新增测试/报告/verification JSON 三文件；最终为 229 项，其余 355 个既有文件逐字节不变。最终实际比对见本轮 verification JSON。

确认上轮中断后的完整日志已经落盘：`windows-feasibility-20261008/full.log` 记录 **1430 tests / 308.549s / OK**，SHA-256 `de54753e704241f138c73c9660dfd6c727e28409c29136a5df26d96a97167a15`。这是本轮检查到的历史日志结果，未找到那次进程退出码的独立记录，不补造 exit 0。其 targeted.log 为历史 36 tests / 2.191s / OK。

此前持久化阶段 `registry-20261008/full-final-after-review.log` 的 SHA-256 与历史 verification JSON 一致，记录 1430 / 219.909s / OK。此结果与上述 Windows 回归是两次不同的历史运行。没有重复实现 receipt、registry、loader 或 preflight。

## B. 本轮 Windows 只读实测与部署条件

- 当前进程 SID 等于仓库 owner；本地 Administrators 直接成员为 true，当前 token 的管理员权限为 false。没有独立受限 Agent 身份。
- 当前仓库与父目录仍有 Authenticated Users 继承的 Modify 权限；不能承载信任锚、可信 composition、解释器或验签依赖。
- E: 与候选根父目录 C: 为本地 Fixed / NTFS；候选根 `C:\ProgramData\ForeignTradeEvidenceReview` 为 MISSING，建议的 FTEReviewOwner/FTEAgent 账户没有创建。
- 本轮 PowerShell 为 7.6.5 / 64 位，CNG/RSACng/PSS 类型可用；另用 Windows PowerShell 5.1 实际执行了只读兼容性测试。未生成或打开任何私钥，不据此宣称 key custody 已验收。
- **本轮 W32Time 为 Stopped，查询为 QUERY_FAILED，错误 0x80070426（服务尚未启动）**。上轮 Running / Local CMOS Clock 是历史事实；当前不能查询同步来源，更不能宣称可信时间成立。没有启动、resync 或联系时间服务器。
- 5.1 的 `-File` 调用被当前执行策略拒绝。本轮没有修改策略；只对已审阅的本地源码使用脚本块执行，并保留模块查询失败为不可用状态。组织级策略禁止时须停止，不能绕过。

本轮本机 inventory 保存在忽略目录，仅供环境调查；它不证明 effective access、跨账户隔离、TPM或可信授权。未知状态和缺根始终 NO-GO。

## C. 本轮实际改动

| 文件 | 实际行为 |
| --- | --- |
| `scripts/inspect_evidence_review_windows.ps1` | 修复 5.1 Windows 检测及 native process 参数兼容；Desktop 使用 .NET 只读 ACL API；增加本地卷事实；缺失/不可读/非目录/reparse point 分开；UNC/网络盘拒绝；账户查询失败返回 null，避免误标受限用户 |
| `docs/evidence-review-windows-deployment-runbook-2026-10-08.md` | 标明历史事实；补执行策略限制、PS7 系统/key 步骤前置检查、引导并发风险、解释器/依赖保护、可信时间要求及部分失败/撤销/恢复规则 |
| `tests/test_evidence_review_windows_inventory.py` | 四项有针对性的只读测试，覆盖 5.1/7、候选目录不创建/文件不修改、未知身份与错误清理、非目录和 UNC 拒绝 |
| 本报告 | 区分历史结果、本轮结果及尚未执行的部署验收 |
| `docs/evidence-review-windows-resume-verification-2026-10-09.json` | 日志/hash/实际退出码、真实冻结目标状态及工作区保留证据；不具有授权能力 |

未修改 core/workflow/adapter/storage 业务逻辑或 public contracts。没有扩大 GEO、UI、普通 P/S、EXPLAIN、comparison、Draft 或 WordPress 权限。

## D. 已实现能力、未实现能力与阻塞

既有代码实现：严格冻结目标/签核 loader、有界 append-only receipt cache、重新验签与当前注册状态消费、任务/版本/身份/用途绑定、撤销/过期/重放拒绝、缺根默认拒绝的离线 preflight。本轮新增的是只读部署调查兼容性和部署/恢复文档，没有新增第二套审批系统。

尚未实现：生产 CNG authenticator、认证 named-pipe registry host、实际审核工具、受保护安装/composition、真实 grant/key/review 撤销持久化与审计、可信时钟运行/恢复保障。这些都只有部署规格，**不存在可用 signer/service 启动命令**。因此“Windows 最小生产闭环”仍未完成，不能把准备步骤或 synthetic HMAC/registry double 当作已部署。

当前真实阻塞是独立身份、保护目录、两把固定公钥锚、生产 host/client/审核工具及可信时间均未建立。当前普通 Agent 进程无提升权限，且本任务明确禁止其执行系统操作。保留此边界，不用 JSON APPROVED、环境开关或可编辑 DB 字段代替身份。

## E. 本轮测试与验证

本轮最终针对性命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_evidence_review_windows_inventory tests.test_persisted_evidence_review tests.test_evidence_sufficiency_preflight tests.test_first_party_excerpt_capacity tests.test_first_party_planning tests.test_content_draft_core tests.test_content_draft_workflow tests.test_history_serialization tests.test_sqlite_history_store tests.test_runtime tests.test_cli -v
```

实际结果 **191 tests / 15.178s / OK / exit 0**，日志 `.data/evidence-review-windows-resume-20261009/targeted-final.log`，进程结果单独保存。四项新 inventory 测试最初暴露 3 failures + 1 error；首次修复后余 1 failure（5.1 Security 模块加载被策略阻止）；改用 .NET Framework 只读 ACL API 后四项及最终 191 项均通过。失败没有通过弱化断言处理。

覆盖沿用既有签核、持久化、身份/权限错误、record/proof/frozen 篡改、过期、跨任务/用途重放、撤销及缓存旧备份边界。Python contracts 不改，没有为增加数量重复添加这些测试。

本轮完整回归命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

本轮实际结果 **1434 tests / 222.761s / OK / exit 0**，相对既有 1430 项仅增加四项 inventory 测试。最终日志和进程结果分别保存为 `full-final.log`、`full-final-process.json`。此结果是本轮观察到的完成结果，未使用历史结果替代。

其他实际验证：

- inventory 及 runbook 四个 PowerShell 代码块在 5.1/7 中 parse-only 均 0 syntax errors；只解析系统/key 步骤，**没有执行这些命令**。key/.NET7 APIs 与 ACL 部署的实际效果仍待 owner 验收。
- 已有 excerpt-v2 `verify_materials.py` 再次 exit 0：六义务七 span、一个 Change、五个旧 V1 roundtrip PASS；P-only 原生 Draft FIELD_CONTRACT、writer=0，EXPLAIN/comparison 负例拒绝。
- 当前 trusted-preflight 包本地读回：task/Plan/evidence `(2,2,1)`；frozen SHA-256 `146cd906b1fce15a21a6f26f50224e09182a1d0b7ed934df1e7ccba826972c1d`；DraftInput `a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2`。六 obligation 和七 decision 均 NOT_REVIEWED、reviewer/time 为 null；实际 default persisted Gate REJECTED、native Draft invalid_input、writer_calls=0。

## F. 必须由项目所有者执行的部署步骤

准确命令、权限矩阵及恢复规则见 [Windows deployment runbook](evidence-review-windows-deployment-runbook-2026-10-08.md)。步骤顺序：

1. owner 核准离线备份并演练到另一个目录的恢复，不把 `.env`/私钥放入 Git、普通归档或报告。退出/隔离不受信任进程，检查 root/父目录没有 reparse points 或替换权限。
2. **提升的 64 位 PowerShell 7、OS 管理员**创建两个新的标准用户和全新受保护目录；不改仓库/profile 既有 ACL，不复用工具账户。名称/路径已存在或部分失败时停止，人工核验，不整段重跑/自动删除。
3. 分别实际登录 reviewer/Agent，核对 SID、组、privileges 和跨账户有效权限。Agent 不能修改 Verifier/Anchor/父目录，不能读取 AuthorityState 或私钥、不能取得签名能力。仅 token 未提升或私钥非导出均不能证明隔离。
4. 用独立 TEST 身份/key/root 完成生产 host/client/审核工具实现与部署验收；安装保护全部 runtime/依赖，拒绝 editable 链接及可写加载路径。query 入口只读，认证 client/server SID 和 challenge-bound signed response；current grants/revocations 必须来自保护边界。此组件开发仍待后续，不是 owner 复制本手册就能启动。
5. owner/系统管理员按核准时间策略处理 W32Time；核验认证/独立校准来源、漂移与失效期限，并做回拨/陈旧/重启验收。该操作可涉及系统和网络，必须由 owner 另行执行；本轮未做。
6. TEST 验收后，owner 专用标准用户会话才创建生产 CNG key；管理员独立登记固定 public fingerprints/SID/scope。人工逐项审核全部 O1–O6/七决策，展示最终精确冻结记录后才由本人签名/注册。不得一键全部 APPROVED；正式签核不属于本轮执行范围。
7. 先验撤销、服务退出、旧 receipt/response 重放、断电重启和备份恢复。没有可靠的独立状态检查点时恢复后继续 NO-GO，不能恢复旧 ACTIVE 解除撤销；丢失 key 时新版本/新审核，不复活旧批准。

本机模型不防 OS 管理员/SYSTEM、同审核账户恶意代码、供应链替换或全盘回滚；增强这些边界需独立设备/硬件或外部日志锚。权限、key、服务和时间配置属于 owner 的系统操作，本轮明确停止，不请求 Agent 代做。

## G. 下一阶段与独立 GO/NO-GO

| 验收对象 | 本轮结论 | 仍需条件 |
| --- | --- | --- |
| synthetic 离线持久化 preflight | **GO，仅离线测试** | HMAC 和当前 registry double 不证明 CNG/IPC/OS部署；Windows TEST 身份实测仍未执行 |
| 真实 O1–O6 审核/签核 | **NO-GO，全部 NOT_REVIEWED** | 独立信任根、可信时间、production host/client、owner 实际逐项签核 |
| 商业 Content Draft | **NO-GO，writer=0** | 真实审核之后还需同冻结输入消费、输出全覆盖验证及独立商业验收 |

下一阶段先由 owner 完成系统准备/可信时间证据，再实现及验收复用现有 ports 的 production host/client；缺根时维持拒绝。之后分别安排真实审核和商业 Draft 消费，不能继承 synthetic 或有限离线授权。普通 P/S、EXPLAIN/comparison 和 WordPress create-only/draft-only 原边界保留。

本轮付费 LLM、真实外部网站、WordPress、真实审批、正式 Draft、生产 key、Windows 安全配置变更、commit/push/reset/clean 均为零。历史报告不改写；本轮证据放在新目录中。
