# 真实 DeepSeek SEO Draft 内容质量失败：只读根因审计

日期：2026-10-08（Asia/Shanghai）。范围：本次失败的输入、持久化结果、当前工作区生产代码、Prompt 和相关测试。本轮仅新增本报告；不修改生产代码、测试、验收脚本或既有材料，不调用真实 LLM、客户站点或 WordPress，不提交或推送 Git。

结论：**本次商业成稿 NO-GO。已证实的主因是材料只能支持主题观察和极少的概括，Planning 却允许进入解释型扩写；Draft 的普通事实引用验证和任务完成度检查无法挡住这种低信息输出。没有证据证明“最低 9 条 claim”导致填充，因为不存在该最低要求。** 输入和 Prompt 对模型行为的具体因果贡献仍需离线对照样本，不能用一次真实响应定论。

“已证实”表示可从保存材料、代码或本轮本地执行直接核对；“可能”表示有机制和样本一致性，但缺少控制变量证据；“未能证实”表示现有资料不能支持。SEO 信息增量在此指对选材问题增加有依据、可供读者使用的解释或判断信息；没有评估搜索排名、流量或转化效果。

## A. 真实失败重建

### A1. 身份、材料和执行路径

已阅读 [真实验收报告](seo-draft-live-acceptance-2026-10-08.md)、[离线验收报告](seo-draft-offline-acceptance-2026-10-08.md)，并独立核对下列本地证据。以下目录是 ignored 验收材料，不随本报告自动进入版本管理：

`L = .data/seo-draft-acceptance-20261008/live-/d3793d59826448c9834cfcbe87bb2188/`

| 证据 | 本轮核对内容 |
|---|---|
| [L/request.json](../.data/seo-draft-acceptance-20261008/live-/d3793d59826448c9834cfcbe87bb2188/request.json)、prepared-request.json | 完整 system/user 材料；二者及当前生产 builder 重建请求完全相等 |
| [L/history.sqlite3](../.data/seo-draft-acceptance-20261008/live-/d3793d59826448c9834cfcbe87bb2188/history.sqlite3) | 使用 SQLite `mode=ro`，读取实际 P1/S1、Research、Opportunity、Change Plan 和真实 Draft；未构造会迁移数据库的 store |
| L/diagnostics.json | 历史真实请求的状态、模型、usage、输出长度和 result artifact 身份 |
| L/live-review-D1.json、verification.json | 审核视图、既有人工失败结论；本轮独立逐句审查，不将旧结论作为自动语义验证 |
| L/reconstructed-validated-specification.json | 从已验证 artifact 重建的 specification；本轮本地 parser/finalizer 和 workflow 重放 |
| accept_offline.py、accept_deepseek.py | fixture 来源、Mock Planning 选择、单请求限制和真实 Draft 的追加路径；只读脚本，未执行 live harness |

run 为 `58681c3b-2611-490a-93f1-0ec5f2e89f4e`；真实 Draft artifact 为 `0c58bab3-6807-4d18-add8-6b0fb534dcfc`。同库另一份 Draft `d66717b0-3038-4cc0-9354-5aecfebe8c8d` 是准备 mock，不能混用。

| 上游 artifact | 身份 |
|---|---|
| SITE_CONTENT | `3624a6df-aca9-4906-bbf2-c07e8da63baf` |
| INDUSTRY_RESEARCH | `f9df5f03-a0d6-45b7-8f42-de081108e593` |
| CONTENT_OPPORTUNITY | `fec4f838-04ad-4085-af2b-a033ebcc7c90` |
| CHANGE_PLAN | `04c82de7-c294-4b56-96c0-2cd8e85446d5` |

请求真实，上游并非真实客户资料：`tests/test_mvp_composed_flow.py:80–96` 给出本地 HTML；`:161–219` 给出固定搜索、Research 和 Opportunity。`accept_offline.py:55–74` 用 MockTransport 返回 Plan，明确选择 P1 的 Chemical Compatibility candidate、EXPLAIN、`P1.LOC_00`。因此本次 **不能证明真实 Planning LLM 自行做出坏决策，也不能证明生产 crawler 丢失了客户材料**；能证明生产准入接受了这份薄材料及其 Plan。

历史 diagnostics 记录：一次 HTTP 200；deepseek-flash，thinking disabled，temperature=0，max_tokens=3000；finish_reason=stop；prompt/completion/total tokens 为 1899/464/2363；输出 1718 chars/bytes。没有截断迹象，也没有 repair 请求。原始 provider envelope 和模型文本字节未保存；可审计的是脱敏诊断及已验证正文，不能声称进行了原始响应字节重放。

### A2. 可核对的原始证据

以下 E 编号仅是本报告的证据段落编号，不是新产品 P/S ID。

**E-P0：P1 页面定位。** title/h1=`Industrial Pump Materials`，h2=`Chemical Compatibility`，description=`Industrial pump selection guidance`。

**E-P1：P1 正文主题枚举。**

> Chemical compatibility, material selection, port size, application, maintenance considerations, and pump performance are observed topics.

**E-P2：P1 正文唯一选材关系句。**

> Buyers compare wetted materials and operating conditions before selecting an industrial pump for a corrosive process.

P1 body_text 另含标题文字。两个 structured_content section 的 text 都重复 E-P1/E-P2，不是两份独立事实。原 HTML 已包含这两句；extraction_status=success、content_truncated=false、structured_content_truncated=false、packet.truncated=false、crawl_budget_exhausted=false。**本样本材料贫乏已证实，抓取丢失未证实。**

**E-S0：S1 标题。** `Chemical compatibility selection guide`。

**E-S1：S1 完整 content。**

> Chemical compatibility and material selection help buyers evaluate industrial pump applications.

S1 content_truncated=false，分类为 EXTERNAL_RESEARCH_CONTEXT / UNVERIFIED_SEARCH_RESULT；标题里的 guide 不代表正文含有指南。Research draft 只有 `Chemical compatibility supports pump material selection [S1].`，没有额外决策证据，也不在 Draft 请求中作为新证据发送。

材料没有提供具体材料与介质的适用关系、工况对判断的影响、可核对的选择条件或选择步骤。这里的不足是相对于“解释兼容性选材指南”的任务；不是“没有数字就不能写”，也不是证明真实世界不存在这些知识。

### A3. Plan 与实际产物

R1 是 HIGH / EXPAND_OBSERVED_CONTENT，topic=`Chemical compatibility selection guide`；C1 是 EXPAND_SECTION，唯一 content point 为 `EXPLAIN Chemical Compatibility`，范围 P1/S1，PAGE_LEVEL，observed/proposed heading 均 null。

Opportunity 的 audit_refs 仅 A1（canonical 检查），不是兼容性内容证据。其 artifact 同时已有 A3：`content.minimum_extracted_word_count=36 / warning`。这说明至少已有文本短的诊断，却没有形成任务证据充分性判断；36 词本身也不能证明充分或不足。

真实 D1 为 PARAGRAPH（CL1–3）→ BULLET_LIST（CL4–8）→ PARAGRAPH（CL9）；前 8 条均引用 P1/S1，并被派生为 MIXED_CONTEXT。6 条沿用 observed topic 句式；两条直接复制不同来源短句；一条泛化 CTA。没有解释兼容性如何判断或如何使用材料/工况信息，未完成 EXPLAIN。

## B. 9 条 claim 的逐条证据矩阵

所有正文均逐句对照完整材料，而非仅对照审核 excerpt 或关键词。P1 支持“本页面出现某主题”与支持“该主题的技术结论”必须分开。复述来源不自动等于错误，但不能充当扩写的实质解释。

| claim / 实际类型与引用 | 原文及具体表达 | P1 的语义支持 | S1 的语义支持 | 主题复述、重复及有依据增量 | 越界判定 |
|---|---|---|---|---|---|
| CL1 / OBSERVED_PRODUCT_FACT / P1,S1 | “Chemical compatibility is an observed topic for industrial pump materials.” 表达页面材料中观察到兼容性主题 | E-P0/E-P1 支持页面主题观察；不支持任何材料兼容性结论 | E-S0/E-S1 讨论兼容性，但不说明 P1 页面观察结果；仅相关背景 | 是主题复述；与 CL2 构成主题共现的重叠铺陈。没有解释增量 | 没有虚构技术事实；将 S1 作为页面观察的证明不充分 |
| CL2 / OBSERVED_PRODUCT_FACT / P1,S1 | “Material selection is an observed topic alongside chemical compatibility.” 表达两主题在材料中共现 | E-P1 明确同时列出二者 | E-S1 同时谈二者，支持一般主题联系；不能证明该页面的 observed 结论 | 是主题复述；与 CL1 重叠但非同一命题，不能称为完全重复；无实质解释增量 | P1 支持观察；S1 的背景关联不等于观察支持 |
| CL3 / OBSERVED_PRODUCT_FACT / P1,S1 | “Buyers compare wetted materials and operating conditions before selecting an industrial pump for a corrosive process.” 表达买家在选泵前比较接液材料和工况 | E-P2 逐字支持完整句子 | E-S1 没有 wetted materials、operating conditions、corrosive process 或先后关系；不支持这些具体命题 | 非 observed topic；与 CL4 有宽泛选材背景重叠，但有独立细节。作为 P1 扩写逐字复制已有内容，新增解释为零 | 事实未越过 P1；额外 S1 归因不成立。类型名不应被解读成已验证的产品参数 |
| CL4 / GENERAL_TECHNICAL_CONTEXT / P1,S1 | “Chemical compatibility and material selection help buyers evaluate industrial pump applications.” 表达两者有助于评估应用 | E-P1/E-P2 提供相邻主题和选材背景，但没有完整断言该帮助关系；不能以词重合认定完整支持 | E-S1 逐字支持。它仍是未验证外部 context | 非 observed topic；相对 P1 增加一个弱概括性关系，价值有限；与 CL1–3 都在同一泛化层级，没有回答如何评估 | 未越过 S1；P1 不构成该关系的独立完整佐证。不是因为文案空泛就判其事实虚假 |
| CL5 / OBSERVED_PRODUCT_FACT / P1,S1 | “Port size is an observed topic in industrial pump material selection.” 表达页面选材材料出现接口尺寸主题 | E-P0/E-P1 支持页面中出现此主题；没有任何接口规格或选型关系 | E-S0/E-S1 不含接口尺寸或相关观察 | 是主题拆分复述；和 CL6–8 同一模板但主题不同，属于功能性冗余。无兼容性解释增量 | 无捏造规格；S1 不支持；偏离唯一 Chemical Compatibility content point |
| CL6 / OBSERVED_PRODUCT_FACT / P1,S1 | “Application is an observed topic in industrial pump material selection.” 表达页面出现应用主题 | E-P1 支持 application 主题出现 | E-S1 的 applications 指买家评估泵应用，不是“页面出现主题”的观察；不能等同 | 是主题复述；与 CL4 共用 application 主题但命题不同，且与 CL5/7/8 同模板。无判断信息 | 无新技术事实；S1 不能证明页面观察；偏离唯一 content point |
| CL7 / OBSERVED_PRODUCT_FACT / P1,S1 | “Maintenance considerations are an observed topic in industrial pump material selection.” 表达页面出现维护考虑主题 | E-P1 支持主题出现，不支持维护要求或建议 | E-S0/E-S1 不含维护信息 | 是主题复述；与 CL5/6/8 为功能性冗余，无解释增量 | 未虚构维护要求；S1 不支持；偏离唯一 content point |
| CL8 / OBSERVED_PRODUCT_FACT / P1,S1 | “Pump performance is an observed topic in industrial pump material selection.” 表达页面出现泵性能主题 | E-P1 支持主题出现，不支持任何性能结论 | E-S0/E-S1 不含性能信息 | 是主题复述；与 CL5–7 同模板，无解释增量 | 未虚构性能值或优势；S1 不支持；偏离唯一 content point |
| CL9 / CALL_TO_ACTION / 无引用 | “Review the chemical compatibility and material selection topics before choosing an industrial pump.” 建议选泵前查看两个主题 | 作为无具体技术事实的编辑性建议，不要求 P1 支持；E-P1/E-P2 是主题背景 | 同理不要求 S1 支持 | 非 observed topic；重复开篇主题和选泵语境，未说明查看什么、如何判断。无可操作的技术增量 | 引用为空符合契约；没有数字、承诺或新产品事实；不能用它代替任务完成 |

共同结论：没有发现伪造数值、认证或优势；不存在完全相同的正文句子，但有明显模板和功能性重复。CL3 完全受 P1 支持，CL4 完全受 S1 支持，其他主要是 P1 主题观察。**没有任何一条实现兼容性选择方法的解释。** CL4 有弱的外部 context 增量，不能夸大为指南已经成立，也不能不加区别地称全部事实无依据。

既有 verification 把 CL3/5/6/7/8 列为 unsupported_S1。本审计补充更严格的归因区分：CL1/2 的 S1 有主题背景关联，但不能支持页面 observation；CL4 的 P1 也不能仅因词汇相似被当作完整帮助关系的佐证。每条引用须支持一个明确子命题；多来源可以共同覆盖复合句，但“相关主题”不能冒充其贡献。

## C. 根因排序与证据

### C1. 原因分类

| 排序 / 类别 | 判定 | 证据、作用与边界 |
|---|---|---|
| 1 / A：上游证据材料不足 | **已证实：本次任务材料不足；未证实：抓取故障** | A2 的完整正文只能支持主题存在、一个选材关系和一句泛化 context。fixture HTML 与 artifact 一致，未截断。对 EXPLAIN guide 不够；不是一般化的客户抓取结论 |
| 2 / B：Planning 与证据能力不匹配 | **已证实：准入缺口；未证实：真实 Planner 的决策行为** | `change_plan.py:1201–1280` 按 candidate/locator 等可用数量开放操作；`:2648–2669` 可从标题生成候选；`:3045–3056` 验 subject phrase 出现，不能验“能解释”。Mock 选择 EXPLAIN heading 后真实生产 finalizer 接受。Plan 无明确待回答问题、证据可支持的答案范围或增量目标 |
| 3 / E：普通引用验证不确认语义贡献 | **已证实** | `content_draft.py:1373–1472` 检查 ID/scope、类型、第一方、数字及禁用表达；甚至不接收 source content 进行普通 S 句义核对。`:1278–1293` 仅依 refs 是否非空派生 MIXED_CONTEXT。B 中 S1 归因缺口及 C2 的关系反转探针直接确认 |
| 4 / F：没有检查意图完成度和实质重复 | **已证实** | `content_draft.py:1765–1776` 接受合规 blocks，不检 EXPLAIN 完成；`:1525–1557` 只按标准化文本和 refs 判重复；`workflows/content_draft.py:393–412` 只在现有 validation category 失败时 repair。本次合法但空泛直接 success，不进入 repair |
| 5 / C：输入结构、措辞及 Prompt 的诱导 | **结构和指令不一致已证实；模型因果贡献可能** | P1 明含 observed topics 并在 body/两个 section 重复；Prompt 强调 short、lexically grounded，但也明确禁止 meta-analysis。6 句延续输入模板。`_content_point_payload` 将主题出现转为 required refs/allowed types；模型为 8 句全附 P/S 与此形式一致。没有对照试验，不能断言某指令必然造成坏文案或仅改 Prompt 即可修复 |
| 6 / D：结构契约强迫数量填充 | **“最低数量导致 9 条”未能证实，且与实际约束不符；缺少 abstain 路径已证实** | C3：SECTION 最少 1 block、其中至少 1 非空 claim/item，没有 9 条、3 段或最短字数要求。1 条 CL3 通过。空 blocks 被拒绝，而 CTA-only 被接受；证据不足时现有 schema 没有明确不足结果，成功准入又不检查任务完成 |
| 7 / F：测试/验收材料覆盖商业质量不足 | **已证实：这些样本测契约；未证实：整个仓库没有任何质量评估** | `test_content_draft_core.py:98–119` 将 observed topics 作为正向契约样本；`:160–180` 验 MIXED_CONTEXT 派生；`:490–511` 只验同 refs 文本标准化重复；`test_change_plan_material_availability.py:52–59` 明确保留单候选内容操作。准备 mock Draft 本身含 observed topic。这些通过本来就不能证明成稿可用 |

这里有两个不同问题：**为何产出了薄内容**（A/B 确认的任务与输入不匹配，C 的诱导可能）；**为何它仍 success**（E/F/D 已确认的准入与验证边界）。不能把“机器放行原因”全部当作“模型产生这些字句的因果证明”。

### C2. 本轮纯本地探针

采用 Python `-B`，SQLite 只读 decode，复用生产 builder、parser、finalizer；各变体仅存在内存，未修改真实 artifact，未调用 writer HTTP。真实重建 specification 另用 LocalWriter 跑生产 ContentDraftWorkflow，结果与真实 artifact 的 ContentDraftReport 完全相等（本地 writer 1 次，HTTP 0 次）。

| 探针 | 本轮结果 | 能证明什么 |
|---|---|---|
| 原 9 条 reconstructed specification | finalizer 接受；workflow success；report 与 live artifact 等值 | 当前生产链可重复放行该失败正文；不是 codec 导致变形 |
| 只保留 CL3，P1-only | 接受 | 1 block / 1 claim 足够，S1 不要求每条都引用；没有硬凑 9 条要求 |
| 只保留 CL9 CTA，无事实、无 refs | 接受 | 存在形式成功但完全未履行 EXPLAIN 的路径 |
| blocks=[] | `BLOCK_BUDGET` | 空正文不代表证据不足的合法结果 |
| 将 CL3 改成 “Buyers select an industrial pump before comparing wetted materials and operating conditions.”，仍 P1/S1 | 接受 | 相同词汇、相反先后关系仍通过；这不是语义蕴含验证 |
| CL3 改为 GENERAL_TECHNICAL_CONTEXT、只 S1 | 接受 | 没有 CL3 细节的 S1 也能被挂作其普通 context 引用 |
| 两次同 CL3 文本，一次 P1/S1、一次 P1-only | 接受 | 去重 identity 含 refs；与 Prompt 的“全文 text 唯一”也有确定的差异 |
| 两次同 CL3 文本及同 refs | `DUPLICATE_CLAIM` | 原有去重规则有效，但保证的性质较窄 |

关系反转仅是离线反例，不是本次真实模型输出；不能记为真实 hallucination。8 个 finalizer 探针的断言均符合预期，exit=0。

### C3. 最低要求核对

| 项目 | 当前实际约束 | 本次因果判断 |
|---|---|---|
| SECTION blocks | 1–8；PARAGRAPH blocks 0–4 | 非空要求存在，但没有要求段落/列表/CTA 三段结构 |
| PARAGRAPH claims | 每个已有 paragraph 1–4；全稿最多 16 claims/items | 最低 1，无“至少 9”“每个 content point 至少若干条” |
| BULLET_LIST items | 每个已有列表 1–6 | 没有必须创建列表，也没有必须列完页面主题 |
| 文本长度 | claim 非空、最长 300 chars；bullet 最长 220 chars；另有 raw/envelope/token 上限 | 没有最低字数/段落长度；本次正常 stop 且远低于 token cap，不是输出截断 |
| 普通事实引用 | 至少有一种 P/S support；OBSERVED/第一方另要求 P；每句 refs 在 Change scope 内 | 不要求每句同时 P/S；CTA/transition 必须 refs 为空 |
| Plan 引用/content point | EXPAND 至少一个 P、一个 S、一个 content point；subject grounded | 限制的是 Plan 的证据类别/候选存在，不能转化为句级双来源证明或足够解释 |
| point-specific refs | 请求把“subject 在哪些 P/S 中出现”同时投影为 `observed_in_*` 和 `required_*`，Prompt 说 use only 对应 lists | 名称可能暗示全部必填，但生产句级校验只有 Change scope，且 claim 无 content_point_ref；既没有明确逐条语义支持，也未强制每句引用全部 lists |

证据不足时，“必须返回非空 draft”与“成功不要求事实/增量”允许输出安全的 filler。**这不等于数量上限或最低 1 条迫使模型生成本次 9 条；其确切条数成因未证实。** 不应先降低安全预算或增加最低条数。

### C4. heading=null 的来源

两个 null 要分开：

- **locator_heading=null**：Mock Planning 明确选择 `P1.LOC_00`。`change_plan.py:2546–2596` 生成 PAGE_LEVEL 和可用的 exact-heading 候选；`:2946–2949` 对 PAGE_LEVEL 直接派生 null。P1 的 Chemical Compatibility H2 在输入中确实存在，不是标题抓取丢失。
- **Draft heading=null**：`content_draft.py:1761–1776` 仅 ADD_SECTION 使用 proposed_heading；EXPAND_SECTION 不生成新 heading。provider SECTION_DRAFT 字段只允许 change_ref/draft_type/blocks，根本不让模型输出 heading。即使另选 exact locator，也不能据此期待 EXPAND 的 Draft heading 自动非空。

它们是**合法的待审核结构，不是本次模型遗漏/JSON/序列化故障**。PAGE_LEVEL 的确留下放置歧义，review 的 `requires_title_override` 在 `content_draft_review.py:328` 由显示标题为空派生，涉及审核/交付标题，不能当作缺少正文 H2 的自动证明。恢复正确定位不能修复正文信息不足；需人工确定位置和适用标题，不能自行补标题后宣布内容通过。

## D. 现有系统的设计缺陷

1. **候选可用性与任务证据充分性混为一层。** 现有 availability 能防零候选、越界、预算裁剪后的非法引用，但有一个标题 candidate 不代表能写 EXPLAIN。Opportunity 的 guide 标题也不是指南证据。应保留现有 availability，增加独立、诚实的任务准入决策。
2. **topic provenance 与 claim support 之间缺少连接。** Plan 的最终 ContentPoint 只留 intent/subject（`change_plan.py:1982–1991`），Draft payload 又按 subject 在标题/正文中是否出现重建 P/S 列表（`content_draft.py:968–1008`）。这些是主题定位，不能给 claim 赋予语义证明。claim 也没有指向哪个 content point 或哪段材料。
3. **support_kind 描述引用形状，名字容易被读成验证结论。** MIXED_CONTEXT 是 P/S 都非空，不代表两份证据都支持，也不代表来源可靠、来源独立。S1 始终未验证；即使引用原句完全准确，也不能升级为权威技术结论。
4. **缺少拒绝生成与质量审核的明确结果。** 当前 enum/schema/workflow 支持机器错误与成功正文；成功不检查内容意图、可用信息或事实数量。不能用空 JSON/CTA 模拟“证据不足”，也不能把仅人工审核标记当作已完成质量审核。
5. **去重和任务一致性较窄。** refs 改变即可绕过同文本 identity；语义/功能重复和页面内但 Plan 外的主题漂移没有被识别。增加一个 observed-topic 禁词规则只能挡住这组表面句式，挡不住改写后的等价空话。
6. **审核材料便于追踪，却未保证便于判读。** 当前 P review excerpt 最多 200 chars（`content_draft_review.py:29`），本次甚至在 E-P2 中途省略。对短证据应看到完整原文，对长证据应看到 claim 对应段落；否则人工也容易把 ID 存在误认为支持。
7. **安全回归与商业质量回归缺少明确分工。** mocked tests 和真实 smoke 的 HTTP/schema 成功有价值，不能代替质量金标准。Prompt 的 “already-approved” 用词也应与实际“Plan 已验证但仍 requires_human_review”区分；本次 approval_record=NOT RECORDED，没有发现交付批准被绕过。

以上缺陷不意味着要替换固定 workflow、扩大 Agent 自主性或取消人工审核。现有数字、第一方、scope、安全限制及持久化保全仍是必要边界。

## E. 最小修复方案及取舍

以下是基于根因的推荐边界，不是本轮实现，也不宣称效果已验证。

| 必要性顺序 | 最小措施 | 预期作用与取舍 |
|---|---|---|
| 1：必要 | **先定义面向任务的证据充分性准入，并在本样本明确停止 Draft** | 对 EXPLAIN 指定要回答的买家问题，以及哪段证据支持哪种解释/判断。仅有标题、主题出现或空泛概括时不得进入 guide 扩写。最小起点可由人工确认 evidence brief；没有可靠自动判断时默认待补证，不假造自动充分性分数。短但有用的证据可准入，不能用字数/来源数阈值代替句义 |
| 2：必要 | **证据不足返回明确的未生成/待补证结果，保留上游 artifact** | 不调用 writer 或不返回正文成功；给出缺少的问题答案/证据类型和待审核状态，不虚构当前站点不存在内容。现有 schema 没有该结果，具体 category、run 状态与 codec 兼容方式需下一轮设计；不能随意塞入现有 SUCCESS、GENERATION_FAILED 或空 blocks |
| 3：必要 | **使 Plan 的工作量匹配可支持的答案，停止把主题候选当成解释 brief** | 现材料至多支持简短主题介绍与一个既有关系，不能自动包装为选择指南。若用户确认改成简介，应明确改 Plan/任务目标；不能静默降级已有 Plan 后让它通过。若保持 EXPLAIN，先补证。最小修复不要求广泛重构 Planning |
| 4：必要 | **让引用贡献可审查：按 claim 显示原始证据段落和归因角色** | 保持 P/S ID、scope、第一方/数字规则；候选 span 必须来自实际 cited material、版本可追溯。区分 topic occurrence、支持具体命题的 span、背景 context。多来源各自贡献须可说明；不支持的装饰引用删除，但删引用不能使本正文质量合格。span 存在只证来源位置，语义仍人工审核；不得宣称关键词或 span 命中已验证 entailment |
| 5：必要且小规模 | **建立少量人工标注的离线质量回归样本，先覆盖此失败机制** | 保存脱敏输入、Plan、候选 Draft、逐命题支持/不支持理由和质量判定。不以一条固定“标准文案”匹配输出，也不把引用重合当正确。成本集中于标注和校准；无需先增加大量契约测试 |
| 6：条件性 | **澄清输入/Prompt 的主题观察与 required refs 含义** | `required_*` 不应暗示每句全附；输入应聚焦批准 content point 的相关事实，不让页面主题枚举冒充答案。body/section 重复可评估去冗余，但不是优先重构 extractor。现 Prompt 已禁止 meta-analysis；仅再加一句禁止 observed topics 没有解决主因 |
| 7：目前非必要 | **调整生成数量约束** | 保持安全上限；无需“降低最低 9 条”，该约束不存在。未来可以提供按证据缩短输出的指导，但减少 16 的上限不能保证增量。空输出问题应通过明确不足结果解决，不以放宽非空结构安全校验代替；不要新增最低条数/段落字数要求 |

引用可靠性还应保留“支持”与“真实性”的分离：原句可支持改写，但来源可能未验证。未来若试验 LLM 评审，只能作为建议、保存不确定性并用人工金标准校准；不能冒充确定性核心验证。本轮不建议再接一个在线 LLM 来给本结果补盖章。

推荐起始样本数量为 **5 个证据包（含少量 paired Draft）**，不是 5 次真实请求：

| 样本 | 金标准问题 |
|---|---|
| 本次薄 P1/S1 + 当前 EXPLAIN Plan | 应停止；原 9 条不能作为合格正例；清理引用或标题后仍不能通过 |
| 人工整理、已获使用授权的充分解释材料 + 匹配 Plan | 应可生成短、可用、有步骤/判断信息的解释；全文事实逐条有依据，不要求数字或长文 |
| P 仅有主题，S 有具体解释 | 解释只作为外部一般 context，不能升级为第一方产品承诺；允许正确区分来源的正例 |
| 单一完整支持句 + 无关但主题相似的 S | 带装饰 S 引用的坏例和准确归因的好例，检验引用贡献，而非词命中 |
| 充分证据 + 关系反转/功能重复/Plan 外主题的候选变体 | 相同关键词仍判错；语义重复和越题不得靠改写躲过人工质量判定 |

每包标注：任务/读者问题、可回答范围、原始 span、claim 的子命题与引用贡献、来源可信度、任务完成/增量、拒绝理由。质量分歧先由人工裁定，停止把有分歧例子转成机器 pass/fail 阈值。离线候选可以人工编写或复用保存响应；离线 golden replay 只能验证边界和审核材料，不证明改过的 Prompt 在真实模型上有效。

## F. 推荐的下一轮实施边界

下一轮建议仅实施 **“薄证据明确停止 + 可审查的任务证据 brief + 少量质量金标准”**。先完成一个受限 EXPLAIN/EXPAND_SECTION 垂直切片，确认这些信息能装入现有 core contracts/workflow/reporting，再决定是否需要最小兼容扩展。

实施前必须补齐的信息：

- 一份获授权、适合该任务的充分证据包，以及认可的买家问题/答案粒度；当前 fixture 无法给出自动充分性阈值。
- 产品决策：不足时是整个 Draft stage 停止、还是逐 Change 的显式待补证；默认保留现有 all-or-nothing，不为此样本擅自改变部分持久化规则。
- 结果协议：不足状态如何映射现有 run/artifact/CLI/review，是否需新 schema/category，以及历史 V1 如何只读兼容；本审计没有足够依据指定实现。
- 引用贡献的数据表示：在不改旧 claim 含义的情况下，是先做审核 sidecar 还是最小 contract 扩展；需要核对下一轮具体消费方，不能先发明整个证据图。
- 若要判断输入重复或 Prompt 是否改变真实输出，需要后续明确授权、冻结材料和模型的受控对照；本轮没有这份证据。

验证只针对上述行为：薄证据时 writer calls=0、上游保全/无成功正文；充分样本不被误拒；P/S/数字/scope/人工审核不放宽；span 与 artifact 可追溯；历史读取与所选状态映射兼容。沿用 focused unittest 与临时 SQLite，涉及 core/workflow/storage 的跨层变化再跑完整 suite。

排除范围：不恢复 comparison、不扩展 GEO、不给现有内容改写/发布权限、不接真实客户 crawler、不运行 live LLM、不改 WordPress create-only/draft-only、不重做全部 Prompt、不批量增加同构测试。离线通过后仍要独立授权真实模型质量验证；商业质量通过也不能代替具体 WordPress 写入授权。

## G. 当前 GO/NO-GO 与停止条件

| 对象 | 当前结论 |
|---|---|
| 本次样本的机器契约/本地重放 | GO：仅表示当前契约接受已验证产物 |
| 本次正文的商业质量、EXPLAIN 任务完成 | **NO-GO** |
| 以此真实 smoke 证明商业 SEO MVP 已成熟 | **NO-GO**；合成材料、单次响应、无效果指标 |
| 按上述边界继续离线设计/实施 | GO：有足够证据定位准入和审核缺口；具体充分性实现仍受 F 的缺失信息限制 |
| 真实 LLM 重试、客户抓取、WordPress 交付/发布、比较恢复 | **NO-GO：本轮未授权且未执行** |

明确停止条件：

1. 无法为批准的买家问题找到可回答的证据时，停止商业 Draft 生成并待补证；不得以主题存在、字数或加 CTA 顶替。
2. 引用仅相关而不支持明确命题、存在关系反转/来源升级/无依据比较时，停止质量准入；机器 success 不能覆盖该结论。
3. 没有完成批准 content point，或仅有页面主题复述、重复模板和既有句复制时，停止商业交付；减少引用/补标题不改变这一点。
4. 准入实现只能凭关键词判语义、需要放宽现有安全限制才能让例子过、或对金标准存在未裁定分歧时，停止该实现方案并补资料，不编造自动语义能力。
5. 历史材料身份不一致、敏感数据无法安全脱敏、工作区无关文件变化或范围扩到 live action 时，停止并查明；真实动作须另获具体授权。

### G1. 本轮实际验证与保全

本轮执行了：完整请求/当前 builder 相等检查；SQLite `mode=ro` 原 artifact decode；真实 Draft codec 等值往返；8 个内存 finalizer 探针；1 次注入 LocalWriter 的生产 workflow 重放，report 等于真实 artifact；全库 WordPress attempts=0。没有执行 CLI 写入、真实 provider、旧验收 harness 或完整 unittest suite。

另运行以下 **4 项已有 focused tests**，0.009s / OK / exit=0；没有新增测试或实施修复：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_content_draft_core.ContentDraftCoreModelTests.test_finalize_expand_success tests.test_content_draft_core.ContentDraftCoreModelTests.test_mixed_context_requires_both_refs tests.test_content_draft_core.ContentDraftCoreModelTests.test_canonical_duplicate_claim_rejected tests.test_change_plan_material_availability.FinalMaterialAvailabilityTests.test_one_content_candidate_preserves_content_operations -v
```

预期拒绝探针返回 BLOCK_BUDGET / DUPLICATE_CLAIM；无断言或 unittest failure。一次源码打印因 Windows stdout 的 GBK 不能编码 µ 而中断，已用 UTF-8 stdout 重新读取；这不是产品失败。前轮报告中的 51/1372 项通过记录仅为历史，未冒充本轮通过。

复核材料的 SHA-256：

| L 内文件 | SHA-256 |
|---|---|
| request.json | `bb95f0df3d818c48095244c6f759967b3f6811eeceb1ab97fc7bbce23d4195e8` |
| history.sqlite3 | `0b79f8a0cc1ce3610c70c6c95d0ec5d0f6799ef919cba95aa2a913d8eb3a9b7a` |
| reconstructed-validated-specification.json | `380b67a03eeee7cdd064eed4317c50f8bd8046d6749b64209d536f56b90b2f33` |

开始时对 442 个既有 tracked/untracked 路径及该验收目录文件记录 SHA-256/缺失状态；完成时重新比对，既有文件内容和缺失状态不变，新增非 ignored 文件仅本报告。已有 dirty working tree 与删除保留，未 commit/push/merge。保全检查与报告内容检查的执行结果见本轮会话工具输出；未为审计另写 ignored 脚本或修改数据库。

报告检查：A–G 七节、CL1–CL9 九行、UTF-8 和所有 Markdown 文件链接均通过；`git diff --no-index --check -- NUL docs/seo-draft-quality-root-cause-audit-2026-10-08.md` 无 whitespace error，exit=1 表示与 NUL 存在差异，另有既有 Git 配置产生的 LF→CRLF 提示。
