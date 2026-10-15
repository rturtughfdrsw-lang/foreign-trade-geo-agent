# Flash 失败后的最小 Prompt 改进与离线质量对照准备

已完成离线修改和冻结，**没有发送真实请求**。最终推荐包是 [selected-facts-v1](selected-facts-v1/readiness.json)，不是早期纯 Prompt 控制包。原始真实 JSON、文章、历史冻结材料和报告只读，1897 个既有 docs 文件 SHA256 不变。

本轮有一个必须披露的非 Prompt 变化：根据项目所有者本轮第 4 项要求，结构化文章不再机械引用全部事实；章节问题/来源覆盖仍由原生 Planning/Validator 保持。不能声称这是完全只改 Prompt 的实验，也不能把拒绝数量减少归功于模型。

## A. CL19 修复后全部 7 条拒绝与处理

按原始 `native-input.json` 和原始 `model-output.txt` 重放，改动前全部七条见 [纯 Prompt 控制的原始重放](prompt-only-control-v1/original-replay.json)。这些是七条诊断，部分来自同一错配，不是七个独立事实错误。

| 序号 / rule_id | 原始位置和实际原因 | 归因 | 本轮针对性处理 |
|---|---|---|---|
| 1 `NUMERIC_CONTEXT_NOT_PRESERVED` | CL7 第1章：520 kg / 180 kg 都有来源，但新数量概括句不是所引完整原句 | 确定的模型契约违规；旧 Prompt 已有规则，示例全是非数值，操作指引不够具体。没有证据确认重量或型号错误 | 换成数值直接引文与独立定性解释的通用示例；明确正文和 proposal 元数据都不能自行概括数量。原始 CL7 仍拒绝 |
| 2 `CUSTOMER_EVIDENCE_COVERAGE` | 全文缺 E4.F04、E4.F05、E5.F04；原代码要求 43/43 | 输出遗漏；同时是机械全事实覆盖的业务契约限制，不能只归咎模型 | 根据本轮第4项收敛结构化事实库覆盖；按问题选择必要事实，不凑 43 refs 或48 claims。遗漏匹配周期和小样本局限仍须在内容质量对照中检查 |
| 3 `SECTION_EVIDENCE_OUTSIDE_QUESTION` | 第2章 CL17/18 引 E5，来源属于 F5/F8，本章 F2 | 模型违反冻结映射；主题语义确有重叠，不是事实伪造或 Parser Bug | 指明 source 和 fact 两层 requirement_ids 都必须与本章相交；型号比较材料按合法章节安排 |
| 4 `SECTION_FACT_OUTSIDE_QUESTION` | 第2章 E5.F03 仅属 F5，本章 F2 | 同一模型错配；旧指引未充分解释事实级限制 | 明确“来源合法不代表所有事实合法”，不能只按主轴主题选材 |
| 5 `SECTION_QUESTION_EVIDENCE_INCOMPLETE` | 第2章实际 E1/E3/E5 ≠ 要求 E1/E3，**多出 E5，并非少证据** | 严格集合契约按设计执行；诊断名字容易误读；不是已证实程序误判 | 明确每章实际来源集合必须等于 supporting_evidence；不修改 Validator |
| 6 `SECTION_FACT_OUTSIDE_QUESTION` | 第4章 CL25 的 E3.F04 仅属 F2；本章 F4/F6，虽然 E3 是允许来源 | 模型未守事实级映射；热身/测量环境有自然语义重叠 | Prompt 要求按真实 fact requirement_ids 路由；Mock 把整条热身事实放回 F2 章；不改映射迁就原文 |
| 7 `SECTION_QUESTION_EVIDENCE_INCOMPLETE` | 第6章缺 E2；选配 E2.F09 已在第1章，不能代替本章引用 | 模型遗漏本章来源；同时受每章来源精确集合契约限制 | 指明每章独立覆盖；用与本章 F8 合法相交的选配事实及真实解释前提覆盖 E2 |

**七项均有针对性处理，但没有证据证明真实模型已经解决它们。** 剩余七项中未发现新的程序误判。CL19 标识符程序 Bug 是此前已修复项，本轮没有改数值扫描器。

## B. CL7：数量原文与采购判断分开

直接事实继续精确引用 E5.F01 / F02，分别包含大夹具尺寸与总重、型号排除及候选条件，小夹具尺寸与总重、居中静载和路径/刀具限制。不得把 fixture 总重写成设备自重或额定载荷，也不得删去静载、工况、未评估项来润色。

原 CL7 的数量概括仍是 `NUMERIC_CONTEXT_NOT_PRESERVED`。允许的采购分析示例在测试中独立构造：

> Exclude NCX7 for the larger supplied fixture on nominal width and static load; keep NCX10 conditional. For the smaller fixture, nominal fit alone does not settle path or tool reach. Fixture clearance and dynamic loads remain unassessed. Send the fixture layout for configuration review.

这段不替换原始响应，不代表真实模型输出或语义批准。原有直接事实保持逐字不变，解释仍带真实前提 refs 和独立 proposal。型号 `NCX7` / `NCX10` 有引用时可以用于分析，不能由此推导数量句、跨型号借值或任意材料编号豁免。

原生局部检查确认：上述定性解释无数值错误；把 `The 520 kg fixture should be excluded.` 放入正文、reasoning、assumptions、limitation 或 procurement_action，仍被拒绝。完整文章仍需章节检查和人工语义审核。真实模型能否稳定这样写，尚待下一次实验。

新 Prompt 示例是虚拟 E999 的通用静载事实，不含 NovaCNC、型号、客户参数或预写的本篇答案；E999 不属于实际允许 refs，不能照抄进入文章。

## C. 正常写作与最小契约收敛

取消的是**所有来源都具有结构化 facts 时的机械全事实引用**。共享 `reference_selection_valid` 在 Candidate、Finalizer、DraftItem 三处复用：引用集合必须非空且全部真实存在，单条直接事实与已审解释仍按既有精确绑定验证。旧式或混合 quote-only 输入保持原先全覆盖。没有改变 Schema、来源版本、snapshot/native binding、审核新鲜度、生产 Gate、WordPress 或候选审批边界。

文章按 reader_problem、search intent 和每章 reader_question 选择必要事实。事实可以直接呈现，也可以成为真正相关的解释前提，不能给一句话挂无关 refs 凑覆盖。模型收到的证据仍是同样的7份资料、43条事实；选择权不是删改证据包。

本案 cutting-cycle 问题需要两型号匹配的周期观察 E4.F04/F05 及适用限制；型号比较也需要 E5.F04 的匹配试验/小样本边界。这些资料应因采购问题需要而使用，而不是因为43/43指标。27条 claims / 36个引用的合法 Mock 证明不必填满48或用完43，但不构成真实模型质量证明，也不是新的数量目标。

仍有保守、可能限制自然写作的规则：新数量摘要须为完整原句、直接事实逐字引用、每章来源集合精确相等、限定的非事实 transition、至少一条解释逐字保留 brief 的 limitation/action。尤其章节语义重叠和来源精确集合可能增加编辑成本。本轮保持这些既有规则，按本轮第5项不修改章节 Validator。新 Prompt 没有增加字数、句式、每章固定分析条数或事实覆盖配额，也没有强迫每段重复“判断/限制/行动”模板。

## D. 新旧 Prompt 的实际差异

见 [system diff](selected-facts-v1/system-prompt.diff) 和 [本轮独立源码补丁](deepseek_content_draft.py.session.patch)。

1. 将原先抽象的数值安全指令换成“精确直接事实 + 独立定性解释”的明确操作方式，通用示例带真实形状的数量/条件；解释不重新概括数量，模型标识符仍可作为候选名称。
2. 明确按真实 section_briefs 的 source/fact requirement_ids 安排材料，各章独立满足 supporting_evidence；不靠主题相近猜路由。
3. 明确必要事实选择、无全量引用配额、预算是上限；同步 user material 的 customer_coverage_rule，避免系统指令与原生契约冲突。
4. 强调参数如何改变选择、可排除/条件候选、待核查条件、试验和RFQ设计；比较必须区分材料、图纸、方法和周期边界，避免事实清单加泛化提醒。

没有增加新供应商、行业专用允许列表、工具调用或自动审核。普通 P/S Prompt 不变。旧式 E 引用及已审解释复制规则保持，原生测试覆盖。

## E. 冻结请求与有意义的对照

最终推荐：[冻结 request](selected-facts-v1/request.FROZEN-NOT-AUTHORIZED.json)、[readiness](selected-facts-v1/readiness.json)、[budget](selected-facts-v1/budget.json)、[真实六章来源/事实地图](selected-facts-v1/section-map.json)。

`request SHA256 = fca21d168a21f6c760a3351087ee2068817edcb63382e0094cfb9898b8d772e7`

保持 `deepseek-flash`、temperature=0、thinking.disabled、json_object、max_tokens=16384；同一任务、Plan、Writing Brief、7份客户资料和43 facts（包括真实 source/fact requirement_ids）。wire 仅改变 system content 和 user material 内 customer_coverage_rule 文本。六章标题、brief、事实、来源、版本、条件、解释输入数量（零）均未变。材料断言和测试实际检查了这个差异边界。

System 7968 chars / 7968 bytes（原7775）；user material 22861 bytes（原22847）；request 32751 bytes（原32544），均在原生输入限制内。最多一次请求，零重试/修复/fallback，建议60秒、262144 response bytes、预算USD0.05。**本轮实际支出授权USD0，实际请求0。** 精确输入tokens未知；字符估算7707–15415不是已证明上界。按历史峰值输入USD0.3/百万、输出USD1.2/百万，65536输入+16384输出的场景估算USD0.0393216；不是当前已验证价格、硬限额或账单承诺。本轮未查模型服务、余额或现价。

早期 [prompt-only-control-v1](prompt-only-control-v1/readiness.json) 仅 system 改变，request SHA256 `94111b9c9c391800b0fda4a4a71876679e1765fe32379cf615543174cc669666`，保留旧全事实约束，作为归因参考。它不满足本轮按需选材目标，**不是最终推荐请求**；不应把它与最终包混用或为了比较额外发送。

下一次对照方法已写入 [comparison-protocol.md](comparison-protocol.md)。由于覆盖契约变了，历史原文必须同时按旧/新规则报告：[validator-delta.json](validator-delta.json) 证明原文仅移除 `CUSTOMER_EVIDENCE_COVERAGE`，claim 检查、绑定和其余六条错误逐字段不变，全文继续 `DETERMINISTICALLY_REJECTED`。这不是模型改善。新文是否有更好的 E 合规、真实解释、采购价值和更低人工修改成本，须由新真实响应和人工检查回答。

**离线已具备有意义的对照材料，尚未具备执行授权。** 未来执行前须复核当前原生状态、代码/哈希、资料与Plan、官方模型参数/价格/预算，并获得只绑定最终请求的新一次性授权。未刷新历史审核时间、未签发许可，保留现有阻断，不把本报告当真人审阅或商业准入。

## F. 如果 Flash 仍不足

值得比较其他模型，但先固定同一个最终 Prompt、任务、证据与选材契约。单次实验只能判断这个样本；若引用/路由稳定而采购分析仍浅，或正确分析仍需要大量人工重写，其他模型的收益应按可核查决策、适用范围错误和修改成本评估，不按词数/价格/“有proposal”推断。

本轮不选择或调用替代模型。跨模型对照需另行授权，记录服务声明的实际model、usage、延迟和费用；不能假定同一 alias 永远对应相同后端版本。既有六章和证据的局限也不会因换模型自动消失。

## 修改文件与验证

生产代码仅4处文件：`adapters/deepseek_content_draft.py`（Prompt/通用示例）、`core/draft_customer_evidence.py`（非空合法事实选择）、`core/draft_candidate_review.py`（调用同一选择检查）、`core/content_draft.py`（投影覆盖指令、Finalizer/DraftItem调用）。Parser、数值规则和章节质量函数没有变。原有用户未提交改动保留，见 [verification.json](verification.json)。

新增 `scripts/prepare_flash_prompt_refinement.py`（只离线冻结/对照，无transport或reviewer）、`tests/test_flash_prompt_refinement.py`（7项针对性测试）及本报告目录。已有 `tests/test_flash_draft_replay.py` 更新为六条拒绝的明确预期，保留原文SHA、CL7拒绝、CL19通过、整篇拒绝和授权为false；`tests/test_draft_prompt_contract.py` 同步选择指令预期。不是删除有效安全断言来通过错误文章。

实际执行：

| 验证 | 实测结果 |
|---|---|
| 数值示例 RED | 3项，1预期FAIL（旧示例不含数值），2已有行为通过，见 tests-red.txt |
| 事实选择 RED | 修正一次测试调用签名后，原生Candidate全量覆盖拒绝和DraftItem全量覆盖拒绝均复现，见 tests-selection-red-confirmed.txt |
| 中间预算检查 | Prompt一度8006 chars触发原生预算拒绝：55项中2FAIL/2ERROR；压缩措辞后7968，不扩大预算，见 tests-selection-green.txt |
| 最终选择/历史/Prompt/旧E测试 | **55项，OK，3.786s**，见 [tests-selection-verified.txt](tests-selection-verified.txt) |
| 原生Core/Workflow/Adapter/数字/证据文章/自主候选/留存验收 | **97项，OK，20.506s**，见 [tests-native-targeted.txt](tests-native-targeted.txt) |
| 最终冻结 | request与原生builder逐字节相同；仅两处允许的Prompt文本改变；包不得覆盖；Mock待人审；历史原文仍拒绝 |
| 历史完整性 | 1897既有docs文件不变；原模型SHA仍为 `04c311ca5fc7a85833f3662dd11d21a97aae00cc95a40afe2604dd5e4ba202e0` |

首次准备纯Prompt包时，手写序列化未按原生顺序排序，wire-byte断言拒绝；已改用相同排序并加入包级测试。失败目录为空且不作有效包。所有中间失败保留，不冒充通过。测试保留既有Starlette/httpx弃用提示。

最终两组共152项定向测试通过；未运行新的全量回归，也不引用上轮全量通过冒充本轮结果。共享改动只涉及选择契约，已针对三个消费者、旧式/混合输入、必要问题、数字、来源、恢复及审核边界验证。没有真实API、自动重试、WordPress写入、部署、生产Gate变更、Git写操作或模型语义批准。工作在离线阶段停止。
