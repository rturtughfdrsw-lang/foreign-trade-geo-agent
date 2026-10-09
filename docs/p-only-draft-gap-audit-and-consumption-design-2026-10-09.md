# P-only Gate → Draft：差距审计与可信消费设计（2026-10-09）

本轮结论：**停止于可审查设计，不启用新的 Draft 执行链路。**现有公共 Draft 执行契约不能携带冻结摘录任务及可信审核消费；现有审核用途明确禁止 Draft。本轮按用户的停止条件保留业务/签核运行时代码，仅新增差距复现测试及本报告。测试通过表示差距被准确复现，不表示业务闭环 GREEN。

已阅读 AGENTS.md、`evidence-review-host-client-report-2026-10-09.md`，以及 core preflight/target、receipt/loader/client、Draft input/prompt/workflow/finalizer/provider adapter 和相关测试。没有启用的 Superpowers skill，未虚构调用。全程无付费 LLM、WordPress、外站抓取、真实账户/生产密钥、Windows IPC 扩展或 Git 历史操作。

## A. 当前业务链路与阻塞根因

现有链路：带 `FirstPartyPlanningScope` 和 task_id 的 native Opportunity → native Change Plan → `ExcerptReviewTarget` 冻结 → receipt 验签、当前 key/grant/registration 检查 → OFFLINE preflight。它止于审核结果；runtime/CLI/Web 没有把该结果接入 Draft。普通 Draft 继续通过原有 P/S 准入。

实际 synthetic 复现的调用链：

1. `core/content_draft.py:stable_content_draft_input_error` 仅构造 `ChangePlanInput(site_content, opportunity_report)`，没有传 scope/task_id。
2. `core/change_plan.py:validate_change_plan_input` 调用 `finalized_content_opportunity_error` 重新验证 R1。
3. `core/content_opportunity.py:validate_content_opportunity_specification` 因无 scope 且 source_refs 为空返回 **SOURCE_REFERENCE_REQUIRED**。Change Plan 稳定校验将其收敛为 **FIELD_CONTRACT**。
4. `ContentDraftWorkflow.run` 返回 **invalid_input / FIELD_CONTRACT / drafts=() / writer_calls=0**。同一材料带原 scope/task_id 的 Change Plan 输入校验返回 None；不是材料预算、六义务/七 span 容量或 JSON 格式问题。
5. `build_content_draft_prompt` 同样拒绝。DeepSeek adapter 还会独立调用同一稳定输入校验；单在外部 wrapper 检查 Gate 后放行 workflow，不能安全完成接入。

另有独立授权阻塞：`OFFLINE_P_ONLY_EXCERPT` 及冻结 `EXCERPT_OUTPUT_CONSTRAINTS` 明文包含 `Offline review only; no Draft generation, provider calls or CMS permission.`。SYNTHETIC_GREEN 和 OFFLINE_REVIEW_GREEN 都不是 Draft permission。已经签过的离线 receipt 必须继续只用于其原用途，不得改解释、自动升级或重新绑定旧签名。

`EvidenceGateResult` 只是状态摘要，没有 DraftInput digest、完整义务/span、当前有效期或可复验原始签核字节。接受调用者递交的 GREEN/approved 标记作为执行凭据会越过现有可信边界。

## B. Gate 到 Draft 的可信消费契约（设计，未实现）

### 需要审查的公共契约变化

`ContentDraftInput` 当前只有 site_content、opportunity_report、change_plan_report、target_language；`run(value)` 只接受这个输入。要满足“同一冻结任务且每次执行复核授权”，必须给**现有 ContentDraftWorkflow** 增加明确的受审核摘录执行输入/入口，接收冻结任务身份和 receipt 标识，并在可信装配下注入既有 loader/current-state ports。把 scope 塞入隐式属性、全局变量、私有标记，或 patch 稳定校验都不符合要求。增加这个公共执行入口也是契约扩展，即使旧 `run(value)` 的参数与旧 dataclass 完全保持不变。

**输出 JSON schema 并非一定要新增 obligation_id/span 字段。**现有 claims 足以承载短逐字 statement，但不能独立证明义务和来源。可保持 DraftItem/schema，通过可信 validator 在冻结输入及固定输出位置之间生成独立 coverage proof，绑定完整最终输出摘要。provider 自报 proof 不可信；只存文本且丢掉该 proof 后，不能宣称可独立审计全部 span。这个兼容选择需与新执行契约一起审查，不能因为 schema 可保留就跳过授权消费设计。

建议契约及执行次序：

| 步骤 | 必须满足 | 拒绝条件 |
| --- | --- | --- |
| 任务许可 | 新的、明确允许离线逐字 Draft 执行的 purpose 与版本；固定只支持 ATTRIBUTED_EXCERPT、一个 P 页面、一个 EXPAND_SECTION、无 S/audit、DESCRIBE | 旧 OFFLINE receipt；EXPLAIN/COMPARE/SUMMARIZE 或其他操作；商业放置/CMS 用途 |
| 冻结输入 | 一份有界不可变 frozen bytes；严格 decode 后重建校验；project/task/三个版本/purpose/output constraints/obligations/scope/完整 DraftInput 全绑定 | 任一替换，包括语言、locator、正文、span、context/attribution；caller 另给的输入与 receipt 不完全一致 |
| 授权消费 | 用既有 receipt reader 和 registered loader，每次重新验原始 record/proof、可信身份/key/grant、当前注册/撤销/过期及 challenge | 缺根、服务不可用、缓存 GREEN、篡改/错绑、撤销、失效或未知状态 |
| 同一对象执行 | 完成绑定检查后仅消费从该 frozen bytes 解出的私有对象；不重新 crawl/research/plan；不得之后重新读取 caller target 或替换 DraftInput | 使用签核后的新规划结果；scope/content_points 不等价；预算导致截断 |
| 输出校验 | 保留现有格式、预算、事实类型、引用、安全校验；另执行下节的完整逐字覆盖校验，并对最终输出重新验证 | 任一基础校验失败；漏项、重复、重排、错 span/引用、新事实/额外输出 |
| 返回前 | 如存在 await/provider/重试，每次开始前及返回前复验当前授权与绑定；输出摘要必须与 coverage proof 一致 | 执行期间撤销/过期或任务绑定变化；仅首次检查、重试复用旧权限 |

离线逐字输出应优先在现有 workflow 中确定性装配，避免为纯 copy 任务引入 LLM。无需另建 Draft 系统、签核服务、Windows IPC 或生产密钥。TEST 装配仍需固定 TEST domain/anchors、synthetic principal、新用途的全项显式授权；生产入口继续缺根拒绝，不能提供 allow_synthetic/env 开关。

scope dataclass 的 frozen=True 不是对恶意并发内存修改的安全证明；持有单份 bytes、解码为私有对象并复核完整摘要才是防止正常调用链输入替换的消费策略。当前 loader/client 提供新鲜状态读取，**没有执行租约或“验权与 provider 调用共同原子提交”的能力**。执行开始后立刻发生的撤销不能靠一次 preflight 阻止已开始的计算；异步输出必须在返回前再查并丢弃已撤销结果。若业务要求“撤销后一个 CPU 步骤也不能执行”的严格并发语义，需要另行契约决策，不能在本轮声称已解决。

## C. 修改文件及兼容性

仅新增：

- `tests/test_p_only_draft_gap_audit.py`：14 项 synthetic 差距与边界复现测试。
- 本报告：可信消费契约、覆盖算法、验收矩阵及 GO/NO-GO。
- `p-only-draft-gap-verification-2026-10-09.json`：实际验证结果、日志摘要/hash 及历史工作区文件保留证明；不具授权能力。

没有改 core、workflow、adapter、composition、storage、API/schema、CLI/Web 或真实审核包。普通 P/S、EXPLAIN/comparison、商业 Draft 和正式 writer 行为保持原样。既有未提交工作保留；新增 tests 中的低层 DraftItem 是 synthetic gap witness，不是通过受审核执行链生成的正式 Draft。

保留复核：起始 371 个非忽略文件 SHA256 全部一致，既有 `tests/test_history_migration_v1_to_v2.py` 删除状态保留；Git status 从 240 项变为 243 项，仅增加上述三个 untracked 文件，无 staged 变更。逐文件起始 manifest 保存在忽略的 `.data/p-only-draft-audit-20261009/baseline.json`，验证 JSON 记录其摘要及核对结果。

新测试刻意记录现状：某些不完整输出能通过通用 finalizer。它们不是期望永远保留这些缺口的产品要求；后续实现新的摘录契约时，应将相应案例迁入新路径的拒绝测试，通用 finalizer 仍只承担原有通用职责。

## D. TEST 正例和负例

材料为既有独立 synthetic logistics fixture，与 NovaCNC 无关。合成 signer/grants/current-state/session 仅限 tests；真实包没有签名、注册或补写审批。

| 案例 | 本轮实际结果 | 含义 |
| --- | --- | --- |
| 六义务、七 span、O1 连续双 span | target 有效、冻结 codec 完整 roundtrip；TEST Gate SYNTHETIC_GREEN | 只证明现有离线审核和输入绑定能力 |
| 六个完整 statement 送低层 finalizer | 得到六 claims；无 context/attribution/obligation/span proof | 不是完整授权 Draft 正例 |
| 同一 frozen DraftInput 送 native workflow | invalid_input / FIELD_CONTRACT，writer=0 | 新业务链尚未实现 |
| 只保留 O1、漏掉其他五项 | 低层 finalizer 接受 | 缺少覆盖验证 |
| 只输出 O1 第一个 fragment | 低层 finalizer 接受 | 不知道完整义务/双 span |
| 六项逆序 | 低层 finalizer 接受 | 不验证冻结义务顺序 |
| 完整六项加新的无数字事实 | 低层 finalizer 接受，共七 claims | 页引用与非数字检查不证明事实有授权 |
| 重复同一句、P99 错引 | DUPLICATE_CLAIM / UNKNOWN_PAGE_REFERENCE | 原有拒绝边界有效，不能替代覆盖证明 |
| 加双空格 | 接受并折叠为单空格 | 现有 finalizer 不保持逐字字节 |
| 替换 target_language | digest 变化，现有审核 Gate 拒绝 | 完整 DraftInput 绑定有效 |
| SUMMARIZE intent、subject 仍为原 quote | target 校验仍可通过，native Draft 继续拒绝 | planning intent 不能直接当纯摘录许可；新路径应拒绝摘要 |
| EXPLAIN / COMPARE | scoped native planning 拒绝，无 operations | 新链不得解除此边界 |
| 缺生产根，即使 TEST GREEN | production_preflight REJECTED | 测试授权不进入生产装配 |
| receipt 重放、review/key/grant 撤销、过期、任务/版本/span/context/purpose 错绑 | 既有 host/client、persisted/preflight 针对性测试全部通过 | 证明现有审核边界；不是新 Draft 执行负例 |

按停止条件，本轮**没有“完整授权后执行并完成全部输出义务”的正例**，也没有宣称新 Draft 路径已通过撤销/过期负例。缺失验收明确保留。

## E. 输出覆盖验证结果与局限

现有 `ExcerptObligation` + `scope.excerpts` + site packet 能表达每项完整 statement、索引、原文字段、structured_index、start/end、quote；scope 同时绑定 page_ref 和冻结 packet。`excerpt_target_error` 验证全体索引恰好按顺序覆盖所有 span，且多 fragment 同义务必须同字段/同 block 连续，连接后逐字等于 statement。O1 的两个 span 因此能在**输入**侧被表达及验证。

但通用 `DraftClaim`/specification 只含 text/claim_type/page_refs/source_refs（最终 claim 另有 Python ID/support_kind），没有任务 obligation/span/context。`finalize_draft_item` 不接受审核 target；无法比较输出与六义务。它主要检查结构/预算/引用范围、数字及部分词汇规则，随后归一化空格；它不证明普通非数字句子的完整原文支撑。相关低层漏洞不能通过删除上游准入来修复。

可审查的确定性 coverage 算法（尚未实现）：

1. 限定固定 renderer profile 与有界输出结构；固定任务的 context/attribution 是单独明确包装槽位，不是允许 writer 自由填充的事实文本。context/attribution 按冻结值严格相等，不能漏掉虚构演示限定。
2. 每项义务占一个固定有序 claim 槽位，要求 raw text 和**最终输出**均逐字等于冻结 statement；精确 page_refs=(scope.page_ref,)、source_refs=() 及固定事实类型；不接受额外 blocks/claims/fields、自由 CTA/transition、空引用或多余引用。
3. 对每项 obligation 的索引重取冻结原字段，验证每个 `[start:end] == quote`、跨 span 连续、按序连接等于 statement；全局每个索引使用恰好一次、每项义务出现恰好一次。O1 的两个 span 必须共同完成一个完整 statement。
4. 可信 verifier 从这些确定性位置产生 obligation→claim→page/field/index/start/end 映射，绑定 frozen_target digest、DraftInput digest、review id、版本与整个最终输出 digest；provider 自报映射不可授权。相同页面其他位置出现相同文字，也不得冒充所审 span；证明来自冻结映射而非全文 substring 搜索。
5. 在原 finalizer 前后都检查：若归一化改变受审文字，或原数字/词汇/预算规则拒绝该 quote，则拒绝整个任务，不可替换、截短、补单位或减义务。纯摘录的通用规则冲突需在审核前暴露，不能凭“逐字”自动豁免。

这能证明指定冻结摘录的机械覆盖、来源坐标绑定和没有新增文本事实；不能证明原始网站本身真实、工程正确、授权主体有现实业务权利、SEO 效果或商业适用性。任一摘要、改写、拼接推理或比较都超出精确覆盖证明；即使字符串相似或引用有效也不能称语义正确。最小新路径应拒绝此类任务，由另行人工语义审核路径处理。

## F. 针对性测试及完整回归

实际执行：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_p_only_draft_gap_audit -v
.\.venv\Scripts\python.exe -m unittest tests.test_p_only_draft_gap_audit tests.test_evidence_review_host_client tests.test_persisted_evidence_review tests.test_evidence_sufficiency_preflight tests.test_first_party_excerpt_capacity tests.test_first_party_planning tests.test_content_draft_core tests.test_content_draft_workflow tests.test_comparison_admission tests.test_history_serialization tests.test_runtime tests.test_cli -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

新测试单独运行：14 tests / 0.044s / OK / exit 0。
针对性组合：208 tests / 12.785s / OK / exit 0。
首次完整回归日志：1479 tests / 226.739s / OK；随后汇总脚本以 UTF-8 读取混合 Windows 输出失败（UnicodeDecodeError，helper exit 1），未记录 unittest 子进程退出码，因此不宣称该次 exit 0。已从原始日志 ASCII 总结行确认 unittest 为 OK，未隐藏汇总失败。修正为先保存退出码、明确 Python 输出编码并容错读日志后，重新完整回归：**1479 tests / 226.106s / OK / unittest exit 0 / helper exit 0**（wall 227.141s）。日志位于 `.data/p-only-draft-audit-20261009/`，未执行 live/integration verify 脚本。末尾 demo launcher 端口占用信息是既有负例的预期控制台输出，unittest 总结和退出码均已实际确认。

一次只读探索脚本退出 1：尝试把已有七点 P-only operation 直接 dataclasses.replace 成 EXPLAIN，构造器立即抛出 `Change operation fields do not match its discriminator.`。这是原有准入边界提前拒绝，不是 unittest 失败；之后通过合法 provider specification 在 scoped planning 中测试 EXPLAIN/COMPARE，未删除断言或修改验证。上述日志汇总错误也已单独记录；没有已观测 unittest 失败。

## G. 下一阶段与 GO / NO-GO

| 对象 | 判断 | 下一步 |
| --- | --- | --- |
| TEST 现有离线 Gate/签核、差距审计 | GO | 本轮仅在此范围内运行；不代表真实授权 |
| TEST Gate → 完整摘录 Draft 执行闭环 | NO-GO，尚未实现 | 先审查新公共执行契约与明确 Draft 用途；之后在现有 workflow 最小扩展及隔离 TEST 装配，实现上节 proof 和全部执行级正负例 |
| 真实 O1–O6 审核 | 当前 NO-GO | 生产可信身份根未建立，实际义务/决策仍 NOT_REVIEWED；业务 owner 未来需逐项实际审核。旧离线签核不能授权 Draft |
| 正式商业 Draft | NO-GO，writer=0 | 本设计只覆盖离线纯逐字摘录。商业内容必须另满足既有 P/S、事实/数字与人工 review 规则及明确用途授权 |

下一阶段聚焦 SEO 业务消费和覆盖校验；本报告不要求本轮扩展任何 Windows 安全基础设施。不自动审批真实义务、不借用 TEST grant、不弱化普通准入、不调用 provider/CMS。真实冻结 task `T-P3-SIX-RELATIONS-ATTRIBUTED-EXCERPT-v2`，版本 (2,2,1)，frozen SHA256 `146cd906b1fce15a21a6f26f50224e09182a1d0b7ed934df1e7ccba826972c1d`，DraftInput SHA256 `a24428cbc575527b09d59897422fdabe6038c13b206878ddc4cce0a93256b7e2`；本輪本地读回六义务/七决策全部 NOT_REVIEWED，reviewer/time=null，production REJECTED，native Draft invalid_input/FIELD_CONTRACT，writer=0。
