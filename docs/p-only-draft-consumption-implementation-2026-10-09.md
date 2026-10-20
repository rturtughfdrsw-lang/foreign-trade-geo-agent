# P-only TEST Draft 消费闭环实现（2026-10-09）

实现范围：独立 TEST 授权 → 冻结输入绑定 → **既有 ContentDraftWorkflow** 中消费 → 通用 finalizer → 确定性覆盖校验 → 返回前重新验权。没有启用生产 Draft、CLI/Web 新入口、真实签核、付费 LLM、外站或 WordPress。

## A. 实际代码改动

本轮修改六个已有文件，新增三个代码/测试文件；全部是现有链路上的局部扩展。

| 文件 | 实际行为 |
| --- | --- |
| `core/p_only_draft.py`（新增） | V1 request/result/proof、消费和生成 ports、六义务/七 span profile、原始 specification 和最终 Draft 覆盖校验、完整输出摘要及 proof 重算 |
| `adapters/p_only_draft.py`（新增） | 既有 frozen codec + persisted review loader 的消费 adapter；私有解码输入、重新验权；无网络的确定性逐字生成器 |
| `workflows/content_draft.py` | 同一 workflow 新增 `run_p_only(request)` 和默认关闭的注入点；复用 `_finalize`、`DraftItem`、`ContentDraftReport`，失败无正文/proof/Draft 返回 |
| `core/content_draft.py` | 稳定输入验证增加可选 keyword-only scope/task 参数；普通 `run` 和 prompt 仍使用原默认校验 |
| `core/evidence_sufficiency.py` | 独立 TEST Draft 用途、约束和七项决策；target validation 显式选择新 profile，默认仍是离线审核 |
| `adapters/evidence_review.py` | 既有验签/有效期/字段/义务校验按已知用途选择完整决策集合；旧离线决策不能替代 Draft 消费决策 |
| `adapters/evidence_review_host.py` | 独立 `seal_test_draft`，只允许 TEST anchors；复用原身份、确认、签名、注册流程；普通 `seal` 保留离线用途 |
| `evidence_review_composition.py` | `isolated_test_p_only_draft` 仅接受 TEST client；`production_p_only_draft()` 不接受注入参数，缺消费根，始终拒绝 |
| `tests/test_p_only_draft_consumption.py`（新增） | 临时 PSS、公钥验证、TEST session/state、临时 SQLite 及本地生成器的完整业务正负例 |

报告和验证结果为新增文档，不具签核能力。没有修改真实审核包、原 14 项差距测试、DeepSeek adapter、runtime/CLI/Web、WordPress 或历史 artifact codec。

## B. 公共契约与兼容性

- 新入口：`ContentDraftWorkflow.run_p_only(POnlyDraftRequestV1(frozen_target: bytes, review_id: str, schema_version=1))`。请求只携带冻结 bytes 和 receipt ID，没有 caller-controlled approved/GREEN 字段。JSON、摘要、receipt ID 本身均不授予执行权。
- 新用途：`TEST_P_ONLY_VERBATIM_DRAFT_V1`，必须独立审批全部 O1–O6 和全部七项决策，包括 `TEST_DRAFT_CONSUMPTION`。旧 `OFFLINE_P_ONLY_EXCERPT`、历史 EXPLAIN 或离线 GREEN 均不能升级。TEST credential 在 TEST PSS domain 下签署、绑定 synthetic principal 和当前 registration。
- V1 只接受 `ATTRIBUTED_EXCERPT`、一个 P 页面、一个 `EXPAND_SECTION`、无 S/audit、全部 `DESCRIBE`，O1=(0,1)、O2–O6 分别对应其余五 span。保留原 Planning、安全/预算/数字/事实类型校验。摘要、解释、改写、comparison 无消费路径。
- `ContentDraftInput` 的四字段、旧 `run(value)`、writer port、prompt/JSON schema、DraftItem、report、历史 artifact schema/SQLite migrations 均不变。旧调用者不需要改参数；新 scope 参数只提供结构验证，不等于执行授权。普通 Draft 不调用新 profile。
- 返回 `POnlyDraftResultV1`，包裹既有 report、完整 `body`、独立 coverage proof 和 text-free failure reason。正文的冻结 context/attribution 由外层固定 renderer 保留，不能把单独取出的 DraftItem 当成完整受审核交付。

每次执行先把 request 标量/bytes 复制为私有快照，严格解码并检查 canonical roundtrip。生成器只收到复制的文本材料，不收到授权对象或可替换 DraftInput。执行前和返回前均通过原 persisted loader 重新读取原始 receipt、验证签名、当前身份/key/grant、当前 registration 的 challenge/time/revision/撤销/有效期，以及任务/Plan/证据版本、冻结 digest、完整 DraftInput digest 和全部 obligation IDs。执行过程中替换请求会拒绝；调用者在 freeze 后改动原 Python target 不会替换实际消费的快照。

## C. TEST 正例

使用独立 fictional logistics fixture，不使用真实 O1–O6 的签核。PSS keys 为测试内临时 BCrypt keys；TEST sessions/state 和临时 SQLite 仅存在于测试环境，测试结束关闭 keys/删除临时数据库。

已执行的正例验证：

1. 完整独立签核，经实际 TEST host → client → SQLite receipt → RegisteredEvidenceReviewLoader → 新 workflow 入口 → 既有 finalizer → proof 完成，`SUCCESS` 且 `requires_human_review=True`。
2. 六 claims 按冻结顺序逐字输出；七 span 全覆盖；O1 两 span 连续、同字段且完整连接为单个 statement。
3. 额外长 O1（超过单 span 的 120 字符 cap）通过两连续 span 完整消费，没有截断或按 fragment 输出两条义务。
4. 正文保留冻结演示限定及来源；proof 绑定 project/task/三版本、review/reviewer、两个输入 digest、全输出 digest、每项 claim 的 page/URL/field/index/start/end/quote。
5. 显式 TEST 装配正例完成；重复执行再次查询当前状态；普通 writer 计数始终为 0。

## D. TEST 负例与拒绝时机

| 负例 | 实际边界 |
| --- | --- |
| 旧离线 GREEN、旧用途、EXPLAIN 用途、缺决策/义务、NOT_REVIEWED verdict | 不获得新消费权；签核或执行入口拒绝 |
| 生产入口或 PRODUCTION anchors、TEST signature 跨 domain | 生产入口缺根拒绝；TEST factory/TEST seal 拒绝生产 anchors；生产 client 不接受 TEST signature |
| frozen JSON 改写、unsigned/改写 record、错误 proof、非 canonical bytes、错误 schema/类型/超限 | 生成前拒绝 |
| 任务/project/Plan/证据版本、语言、context、attribution、constraints、span、原证据变化 | 生成前拒绝；生成器 calls=0 |
| key/grant/review 撤销、缺 permission、身份/注册/record 过期、根不可用、signed stale-response replay | 生成前重新核验并拒绝 |
| 生成期间 key/grant/review 撤销、过期、transport 不可用、request 替换 | 返回前重新核验并丢弃候选正文 |
| 漏五项/漏一项、O1 半句或双 span 逆序、全部义务逆序、重复、加非数字新事实、空/错 P/S 引用、错误 claim type | raw specification 覆盖校验拒绝 |
| 原文双空格变体、解释文本、改 context/attribution、额外 CTA 字段 | raw specification 严格比较拒绝 |
| 通用 finalizer 后文本被替换 | 最终 Draft 覆盖校验拒绝 |
| 遗漏义务后重算一个“匹配”digest、错 span proof、错最终 digest | proof verifier 先重新检查覆盖，再比较 proof/digest，拒绝 |
| Planning 归一化与原文不相等、原文包含被禁止的宣传措辞 | 原生 Planning 已提前拒绝，不能获得 TEST 签核；未豁免原规则 |
| 通用 finalizer 返回数字错误、generator 抛异常 | 原错误保留/错误净化；无 Draft、正文或 proof 交付 |

所有失败结果的 `drafts=()`、`body=None`、`coverage_proof=None`。负例运行只使用本地候选对象，没有 provider/WordPress 调用。

## E. 确定性输出覆盖

输入侧重建 FirstPartyPlanningScope，逐 span 验证原字段 `[start:end] == quote`；检查 O1 同字段同 block 连续连接，所有索引按顺序恰好使用一次。保留原 scoped Planning 重验和完整 DraftInput 验证。

输出侧先要求全部原始字段、固定 paragraph 布局、六个有序 claims、逐字 statement、精确 P 引用、空 S 引用、固定事实类型、context/attribution 与冻结对象相等，且没有额外字段/blocks/claims。随后调用原 finalizer，并再次检查最终 claim 文本/ID/support kind/来源/locator/metadata、人审标记及完整正文；归一化不得悄悄替换受审原文。

可信 verifier 生成 O1–O6 → claim → 精确冻结 source span 映射，并绑定完整最终 report + body 的 SHA256。`verify_coverage_proof` 重算覆盖和映射后才比较 digest/proof。因此合法 JSON、引用存在、provider 自报摘要或单独 digest 一致均不足以通过。

这证明特定冻结原文的机械覆盖及授权范围，没有证明网站陈述的现实真实性、工程结论或 SEO/商业适用性。proof 本身也不是签核凭据；复验应使用从消费 adapter 重新准备且验权的 frozen execution/review。独立语义审核仍是摘要、解释和改写的生产阻塞。

## F. 实际验证与工作区保留

新增模块最后一次单独运行：**27 tests / 2.643s / OK / exit 0**。
针对性组合：**265 tests / 17.356s / OK / exit 0**，涵盖旧差距、host/client、persisted review、preflight、Planning、普通 Draft、comparison、DeepSeek adapter、历史 artifact/migration、runtime/CLI 及 WordPress delivery。

完整回归：**1506 tests / 231.015s / OK / unittest exit 0 / helper exit 0**（wall 232.109s），比上轮 1479 项新增 27 项。精确命令、日志 SHA256 和源文件 SHA256 见 `p-only-draft-consumption-verification-2026-10-09.json`。运行命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_p_only_draft_consumption -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

期间一个新增测试运行为 26 tests / FAILED(errors=2)：两个测试误设双空格/宣传原文已能获得签核，实际原生 Planning 提前拒绝。按代码根因改为验证提前拒绝，未放松 Planning/finalizer 规则，随后上述 27 项全部通过。最初 19 项正负例及旧边界 58 项也分别通过。没有运行 live/integration verification。

默认 `git diff --check` 实际 exit 0，无 stdout 差错，stderr 仅为既有 LF/CRLF 提示。另一次临时关闭 autocrlf 的只读检查把既有 CRLF 作为尾空白输出；没有据此格式化或改写已有文件。一次 rg 传入 Windows 通配路径产生路径错误，改用目录和 `-g '*.json'` 后完成真实 NOT_REVIEWED 复核；均不是 unittest 失败。

开始记录 374 个已有非忽略文件 SHA256；只有本轮六个指定已有文件发生局部修改，其余 **368 个逐字节不变**。起始已删除的 `tests/test_history_migration_v1_to_v2.py` 状态保留。未 commit/push/reset/clean，未操作 Windows 系统安全配置。基线和测试原始日志在 `.data/p-only-draft-consumption-20261009/`；文档验证 JSON 仅记录结果和摘要，不包含 keys、凭据或原始签核 proof。

## G. 剩余生产阻塞及 GO / NO-GO

| 范围 | 结论 |
| --- | --- |
| 独立 TEST 授权 → 冻结绑定 → P-only Draft → 完整覆盖 | **GO**，实际执行成功并通过负例 |
| 生产 P-only Draft | **NO-GO**，生产入口无身份/签核根，writer=0，TEST credential 无生产装配能力 |
| 真实 O1–O6 | **NOT_REVIEWED**，reviewer/time=null；真实包未改变，不借用 synthetic verdict |
| 商业 Draft、摘要/改写/解释、comparison、CMS delivery | **NO-GO（本路径）**；仍须原业务契约、真实授权及人工审核 |

V1 是精确六义务/七 span 的 TEST profile，没有生产用途、UI、签核来源部署、执行租约或新 artifact 持久化 schema。真实生产装配仍需以后明确实现并验收；新测试接口不是生产安全部署验收。当前版本通过“生成后再查并丢弃”处理执行期间撤销，不能保证撤销与本地计算每一步原子化。Plan/证据版本按当前可信 registration 与签核对象绑定复核；这不是重新 crawl/research 或扫描外部系统最新内容。
