# DeepSeek Draft Prompt 契约修复与离线验证

本轮只修复竞争输出指令和采购分析写作指导。没有真实 DeepSeek、余额、WordPress 请求，没有发布、部署、Git commit/push/merge、PostgreSQL 或生产 Gate/P1 修改。Mock 和审核演练全部为 SYNTHETIC / TEST ONLY，不是模型能力或真人专业签核证据。

最终状态、精确测试计数和冻结哈希见文末机器核验结果；真实调用预检仍须独立满足公开参数、价格、Token 边界和新的明确授权。

## A. 根因审计：核对实际发送的两条消息

读取了历史 `request.json` 的完整 System 和 User 字符串、`native-input.json`、`model-output.txt`、`response-body.bin`、`candidate-validation.json` 及报告/全文。完整历史消息的只读提取副本为 [System](historical-system-prompt.txt) 和 [User Material](historical-user-material.json)。历史原件未修改。

下表旧行号指会话开始时的源码副本 [adapter baseline](baseline-deepseek_content_draft.py.txt) / [core baseline](baseline-content_draft.py.txt)，不是 Git HEAD（进入本轮前已有大量未提交改动）。

| 审计项 | 实际消息和代码证据 | 本轮处理 |
|---|---|---|
| 旧四字段 | adapter L53：`Every claim is exactly {"text","claim_type","page_refs","source_refs"}`，允许类型不含解释类型 | E 不再接入这段；P/S 原文保留 |
| P-only 来源限制 | adapter L57：客户/型号事实 `must cite at least one P page`；L58 数字只按 P 来源描述 | E-backed claim 使用 E；合法 legacy P/S 独立、条件明确 |
| E-only 契约 | adapter L98–108 末尾 `E CANDIDATE RULE supersedes`、`Claims add customer_refs`、`proposal={...}`；实际 User 的 `contract.customer_claim_rule` 也要求 E | 不再用末尾 supersedes 弥补前文；当前模式直接选择完整契约 |
| 已审 E 契约 | adapter L122–137 仍在同一旧 System 后追加；core L1030–1031 投影已审解释时漏掉 proposal | 已审模式独立；已有 proposal 原样投影，没有则仍省略 |
| 自主解释 | User 内 interpretations 为零、43 refs 齐全；System 前部未列 EVIDENCE_BASED_INTERPRETATION | 模式 C 显式列解释类型、五字段与第六字段条件、元数据、问题绑定和待审边界 |
| 模式选择 | 原生已有 `customer_evidence` / `propose_interpretations`；P-only TEST 使用独立 consumer/generator | 复用已有两个字段；不新建业务模式判定器，不改 P-only 路径 |
| 长度/词汇 | adapter L63 `Keep every claim short and lexically grounded`；末尾又说分析不受来源词汇限制 | 旧短文本风格留在 P/S；E 使用实际 300/1200/220 字符预算和自然段指导 |
| 事实覆盖 | adapter L107/L127、User 原规则要求覆盖所有 refs；当前 Validator 确实检查全量 refs | 保留覆盖；区分“正文选择展示”与“事实作为真实分析前提”，不强制每事实一条正文 |
| 章节写作 | 真实 User 的六章 question/explanation_goal/limitations/action/requirements 都在；并非 Plan 丢失 | 先回答采购判断，允许多事实综合、风险/适用性、询价检查项与不同段长 |
| 上限是否当目标 | 原文已经有 `Budgets are ceilings, not quotas`，模型仍输出 48 claims | 不把封顶认定为已证实因果；强化按读者价值组织、不凑词数/claims/tokens |
| 指令优先级 | 四字段“exactly”和追加字段不能同时成立；先 P-only 后 No P/S substitution 争夺来源 | 去掉 E 中竞争规则；前后消息对当前来源与字段一致 |

历史结果仍为：HTTP 200、stop、JSON Parser PASS、Validator REJECT；48 claims，无 customer_refs/proposal，输出 3,387 tokens，未截断。存在明确的 Prompt 缺陷；**它是否导致那次模型失败、修复后模型是否遵循，仍未完成真实因果验证**。

## B. 三种模式及兼容边界

| 原生状态 | System 契约 | 事实/解释准入 |
|---|---|---|
| 无 customer_evidence，propose=false | 原普通 P/S Prompt，逐字节不变 | 原 P/S 来源、逐 point 约束及数字规则 |
| 有 customer_evidence，propose=false | E REVIEWED MODE | E 直接事实精确原文；解释必须匹配已审 text、顺序一致的全部 refs，以及已有 proposal；不能扩大审核范围 |
| 有 customer_evidence，propose=true | E CANDIDATE MODE | E 精确事实 + 新解释 proposal；仅待审候选，不获得正式 Draft/执行资格 |

propose=true 而没有 E 输入继续视为无效；新构造函数也明确拒绝该组合。是否 structured 使用已有 `source.facts`：任一来源有 facts 时 P/S 是 planning context；全部无 facts 的旧 E 输入仍可在独立 claim 中使用合法 P/S。E 和 P/S 不混引，E 事实不能用 P/S 代替。

## C. 本轮具体差异

- `src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py`：提取共享基础和预算，保留原 `_SYSTEM_PROMPT` 的 P/S 内容，增加 `_e_system_prompt()`、模式专属说明及少量真实 schema 示例；`build_system_prompt()` 选择当前契约。
- `src/foreign_trade_geo_agent/core/content_draft.py::ContentDraftPrompt.material_json()`：补上已审 proposal 投影，明确 E 覆盖、P/S planning scope、允许的非事实 claim；不改验证、持久化模型或序列化。
- `tests/test_draft_prompt_contract.py`：真实输入最终消息、原 P/S 字节兼容、已审/候选/legacy E、示例原生解析/校验、来源与数字错误及历史失败重放。
- `tests/test_draft_prompt_contract_acceptance.py`：完整离线链路、低资料、不同段长、独立冻结哈希与未授权阻断。
- `scripts/accept_draft_prompt_contract.py`：复用原生验收器，保留新的独立 Mock 输出、旧响应拒绝诊断和新冻结包。
- 本目录与计划 `docs/superpowers/plans/2026-10-12-draft-prompt-contract.md`：审计、RED/GREEN、回归、历史完整性与冻结资料。

[源码边界核验](source-boundary-verification.json) 用 AST 比较会话前后原有函数，变化仅为以上两个 Prompt 方法；新增 `_e_system_prompt`。原 P/S System 6,114 chars 完全一致。所有既有无关未提交成果按基线 SHA256 保留，详见 [完整性结果](historical-integrity.json)。

## D. 原生 schema 一致性

按 `workflows/content_draft.py::_parse_claim/_parse_specification`、`core/draft_customer_evidence.py::InterpretationProposal/DraftInterpretation`、`core/content_draft.py::_validate_claim_evidence/article_quality_findings/finalize_draft_item` 交叉核实：

- 顶层只能 `draft`；本 E 路径是 `change_ref,draft_type,sections`，section 为 `outline_heading,blocks`；heading 与批准 outline 顺序一致。
- E claim 五个基本字段：`text,claim_type,page_refs,source_refs,customer_refs`；引用是数组，不是正文自动推断的引用。直接事实一条完整精确 quote、一个有效 ref；E 的 P/S 数组为空。
- 新解释为 `EVIDENCE_BASED_INTERPRETATION`，增加且只增加 `proposal`，包含 `procurement_question,reasoning,assumptions,limitation,procurement_action`；前三项各 ≤300 chars，后两项各 ≤150；question 等于 section.reader_question，limitation/action 逐字出现在正文中，正文空白规范化。
- 新解释 refs 为 1–20 个去重前提；直接事实/CTA 等 ≤300 chars，E 解释 ≤1,200，bullet item 即使解释也 ≤220。48 claims、24 blocks、4 claims/paragraph、每章最多4 paragraphs、6 bullet items 均保留。
- 数量必须保留原表达、单位、主体、条件。新解释及元数据中的数量只能出现在引用前提的完整原句中；不允许数字推导或跨型号借值。建议数量留在精确事实，分析使用有边界的定性推理。
- 已审解释存在 proposal 时必须原样输出；原解释没有 proposal 时省略，不能自行补造。TEST-only 复验不生成真人签名或生产许可。
- 普通 CTA 和衔接不含事实、数量、能力或商业保证。structured E 的衔接句原生只允许两句，已明确保留；自然过渡可在解释内部书写，不能借 editorial 标签隐藏断言。

System 末尾的四个示例覆盖单事实、多事实新解释、衔接和 CTA。测试直接读取**实际嵌入 Prompt 的 JSON**，走原生 Parser 和 claim Validator；没有另造示例 Parser。`E999.F01/F02` 明确为示意值，未进入真实 43 refs 目录。完整文章 Mock 同样走原生 Parser，而非转换后 JSON。

## E. 从事实枚举转向采购决策

新指导以文章目标、search intent、reader_problem、各章 reader_question 为主线：判断排除/条件候选、名义匹配后的未知条件、买家输入、供应商试验/记录和不能得出的结论。相关事实组合成有边界的解释，而非连续贴参数。

允许比较、适用性讨论、风险分析和有用途的询价项；不强迫每段使用 Fact→Meaning→Limitation→Action。减少重复的泛化谨慎句，同时保留每项结论不可缺少的限定和原生 section limitation/action。CTA 选择图纸版本、材料状态、夹具、循环、验收及配置/交付输入，不堆满所有字段，不暗示已经验证应用能力。

**保留的限制**：现有 Validator 要求所有 E refs 覆盖，不能真正从证据目录中随意丢弃事实；本轮只改变展示和综合方式。若要放宽引用覆盖或两句 editorial allowlist，属于以后独立核心契约任务，本轮没有实施。

## F. 安全边界

旧四字段 P/S 输出仍能按历史格式解析，但 E Candidate Validator 继续拒绝；没有自动补 customer_refs、从正文匹配 E、改 claim_type 或添加 proposal。原始错误输出及历史冻结材料都保持字节不变。

篡改 quote、无效 ref、E→P/S 替代、额外批准字段、缺失 proposal、未证实数字继续失败。未经审核的新解释在 Finalizer 仍报 `INTERPRETATION_PENDING_REVIEW`。审核意见绑定正文、premises、来源/版本、Plan 和元数据；变化不能沿用批准。低资料在 Evidence Sufficiency 前置阻断，writer=0。既有比较不可用、P-only TEST、证据不足、超预算和历史 artifact 读取通过全量回归核对。

## G. 实际测试、失败与修复

1. 首轮 RED：8 项运行，4 个预期失败，暴露输出模式、分析指导、示例及已审模式缺失，见 [tests-red.txt](tests-red.txt)。
2. 初版 E System 超过 8,000 chars，最终消息与 adapter 测试正确拒绝；压缩指令到现有预算内，没有扩预算或删安全约束。初始失败保存在 `tests-green-initial.txt`。
3. 初始 GREEN：8/8；定向 Draft/Evidence 回归 **182/182，32.702 秒，OK**，见 [定向日志](tests-targeted.txt)。
4. 新完整离线模块初跑 **13/13，7.738 秒，OK**，见 [集成日志](tests-acceptance.txt)。后续增加的复核回归由最终全量结果覆盖。
5. 独立只读代码复核发现并修复：E ref 最小数量必须只用于事实/解释；E-backed 与 legacy P/S 的条件需明确；reviewed proposal 不能统一必填；已审 User Material 应包含原生合法 editorial。均有失败在先的回归记录，见 `review-*-red.txt` 和最终 `review-green.txt`（14/14）。
6. legacy 测试初稿误用七份资料删 facts 的大型输入，触发既有 legacy envelope 预算；改用真实历史单份 E fixture 后才验证目标来源规则。新测试中禁止泛化 `cited P evidence` 的过宽字符串断言改为禁止旧完整无条件指令，同时新增合法 legacy P/S 来源/数字断言；没有删除既有项目断言。
7. [首次完整回归](tests-full-first.txt)：**1,887项，446.589秒，失败2项**，均是旧实验检查 `E INPUT RULE` 标识。保留旧断言，在独立 reviewed 模式标题中保留该兼容标识，未恢复 `supersedes` 或竞争契约。修复后 Prompt与旧实验模块 **25/25，5.116秒，OK**，见 [兼容验证](tests-legacy-marker-fix.txt)。因此有必要再运行一次全量，而非忽略失败；两次完整结果均保留。精确最终数量、耗时和退出状态见文末。保留既有 Starlette/httpx 弃用提示，不以提示当测试失败。

最终离线 Mock：7 documents /43 facts /6 sections，输入已审解释0，输出6条精确直接事实、14条解释候选及1 CTA，共21 claims/15 blocks，段长不同。全部43 refs保留为直接引用或前提。原生 Parser→Candidate Validator→待审保存→显式 TEST-only Review→原生 Revalidation→SQLite reopen→Markdown→Web 完成。未审 Finalizer 拒绝由定向与全量测试覆盖。没有把脚本写好的分析当成 DeepSeek 已学会新契约。

## H. 真实失败对照

| 检查项 | 修复前 | 本轮离线结果 |
|---|---|---|
| 最终输出契约 | 四字段/P-only 前文 + E 末尾例外 | 当前 E 模式完整、类型条件明确 |
| E refs | 有目录与指导但模型全未使用 | 五字段显式要求，示例/Mock原生验证 |
| 新解释 proposal | 模型0条 | 合法 Mock14条待审；不自批 |
| 旧 P/S 四字段 | 混进 E | 普通P/S逐字保留，E独立 |
| 写作倾向 | 参数/限制改写为主 | 指令与Mock展示问题导向分析；真实质量未知 |
| 原历史响应 | REJECT | **仍REJECT**，零修补 |
| 合法新响应 | 未验证 | 原生待审/TEST复验/留存链路PASS |

拒绝原输出证明安全边界未被削弱；Mock 通过证明契约可实现。两者都不能证明真实 Flash 的遵循率或商业文章质量。

## I. 新独立冻结包

最终交付目录为 [final-v2](final-v2/readiness.json)。本轮开发预检 `frozen-v1` 保留为原样的早期离线包，**不作为最终请求使用**；没有修改任何旧真实冻结包。final-v2 单独冻结当前输入和代码。

包含原始七份 SYNTHETIC UTF-8 文件、43 facts/来源映射、当前 task/Plan/brief、原生 Intake snapshot和TEST审核、System/User、实际 schema及原生源码行号/函数摘要、冲突审计、完整请求/参数、预算/成本假设、原始响应留存与过期处理、逐文件 SHA256及独立bundle SHA256。新资料源字节、facts和Plan与上次真实输入相同；新的审核时间/快照独立留存。

请求：`deepseek-flash`，temperature0，thinking disabled，JSON object，max_tokens16,384；计划单次、零自动重试/fallback、有界60秒timeout、256KiB响应留存。输出长度是上限。费用提案上限USD0.05；按**未再次核实的历史高峰费率和假设输入65,536 tokens**估计USD0.0393216，不是硬账户限额或已验证Token上界。

本轮只读访问官方公开价格/参数页面均超时；未确认当前alias、上下文/输出上限、参数支持或价格。字符估算不是Tokenizer，实际usage为空。因此真实预检为 **BLOCKED_PUBLIC_CONFIGURATION_AND_TOKEN_BOUND_CONFIRMATION**。没有查余额或发模型请求。

冻结准备有效期24小时；本轮未发许可，许可expires_at为空。未来许可提案只限本bundle、一次请求、10分钟；到期或任何输入/代码/hash变更即停止，重新核查/冻结并取得新的明确授权。旧已消费授权不可复用。完整原响应、模型文本、model/finish_reason/usage/缓存统计、时间与SHA应在原生解析前安全留存；超限只留有界前缀并标记不完整；敏感响应拒存，凭据/headers永不写入产物。

## J. 有依据的结论

- `PROMPT_CONTRACT_CONFLICT_FIXED`
- `OFFLINE_E_CANDIDATE_READY`
- `REAL_FLASH_INSTRUCTION_FOLLOWING_UNTESTED`
- `REAL_WRITING_QUALITY_UNTESTED`
- `PRODUCTION_NO_GO`

需要后续独立实验和专业人工评审才能评价真实遵循率与写作质量。本轮完成后停止，不签发调用许可。

复核决策记录：全ref覆盖与两句editorial是原生边界，保留而非“优化”绕过；已审User遗漏editorial虽然复核标为Minor，本轮重定为契约一致性问题并修复。未判断真实模型质量、Mock每项前提的专业语义充分性及当前公开配置，是因为缺少真实实验、专业人工审核或成功公开核实；这些均保留为未测/阻断。无延后实现的小修饰项。

## 最终机器核验结果

| 项目 | 实际结果 |
|---|---|
| 最终完整回归 | **1887/1887，437.343秒，OK，exit 0** |
| 首次完整回归 | 1887项，446.589秒，失败2项；exit 1；已保留并修复 |
| 新增测试 | 16项（14个Prompt/native边界 +2个完整链路/冻结） |
| 最后兼容定向 | 25/25，5.116秒，OK |
| 完整Mock | 7资料/43facts/6章，14待审解释，21claims/15blocks；原生TEST复验与SQLite/Markdown/Web PASS |
| 未审核Finalizer | INTERPRETATION_PENDING_REVIEW；正式Draft 0 |
| 最终System / User / request | 7775 / 22847 chars / 32544 bytes |
| 最终冻结核验 | 82个产物，174个代码hash；request可逐字节重建 |
| 历史完整性 | 1793个基线文件；1449个历史docs全部不变；既有变更仅两个Prompt文件发生本轮增量 |
| 真实调用预检 | BLOCKED_PUBLIC_CONFIGURATION_AND_TOKEN_BOUND_CONFIRMATION |
| 准备有效期 | 2026-10-13 10:23:55 +0800（Asia/Shanghai；不是调用许可） |
| 真实模型 / WordPress / LIVE许可 | 0 /0 /未签发 |

**最终request SHA256**：`8fd2b8834c9aa50f4ebaeba6229b4a9b01b59d033effa8637cce5ed223428431`

**独立bundle SHA256**（artifact-sha256.json的摘要）：`04bd097396c9a32cc764881d8e943e42d81fe941836182ee90ebbb0f3e86488b`

原生内部freeze另有摘要，见final-v2/readiness.json的native_frozen_bundle_sha256；不要与交付bundle混用。

完整结果：[verification.json](verification.json)、[全量日志](tests-full.txt)、[最终包核验](final-package-verification.json)、[冻结manifest](final-v2/artifact-sha256.json)、[预检与预算](final-v2/real-request-preflight.json)。
