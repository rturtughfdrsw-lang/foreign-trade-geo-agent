# Draft-only 数字 grounding 审查（2026-10-08）

对象：run `86d25a34-31de-4808-91c3-b0ed89461960`。本轮没有调用真实 DeepSeek、真实 CLI/LiveComposition 或 WordPress；没有改变 provider 配置、重试预算、Git 历史。原有 dirty working tree 保留。

## A. 数字校验契约的准确语义

代码位置：`core/content_draft.py` 中 `extract_numeric_expressions`、`_is_bare_number`、`_validate_numeric_grounding`、`_numeric_expression_is_present`。

1. 草稿文本先执行 NFKC、casefold、空白合并；证据也执行相同规范化。所谓 verbatim 实际为规范化后的文本匹配，不是字节相等，不允许数字/单位换算。
2. 数字起点是前面没有 word 字符的数字；span 可包含数字及 `.,%°"'-/`。tail 可包含温度符号、百分号、引号或字母及字母斜线组合。它不是单位白名单：紧跟数字的普通英文词也可能成为 tail。尾随句点/逗号可能进入 span，拼写数字和嵌在字母标识中的数字不一定被识别。
3. `_is_bare_number(expression)` 的精确定义是 expression **不含** `[a-zµ%°"'/-]` 中任意字符。因此整数、十进制和千分位数字可以是 bare；`1/2`、`1-2` 即使没有物理单位也不是 bare。不能把“非 bare”解读为“单位已经验证”。
4. 每个提取表达式按顺序校验：先拒绝 bare；只有非 bare 才做证据匹配。bare 即使原样存在于 P 也拒绝。第一个失败导致整个 draft 失败；不存在“两个数字有一个 grounded 就可通过”。
5. 数字匹配只使用该 claim/cell 自己引用的 P 正文投影，不使用整个站点、不使用 operation 所有 P、不使用 S。内部链接 anchor 使用指定目标 P。
6. P 投影包含 title、description、h1/h2、body_text、structured block 的 heading/text/rows/pairs/items；跨字段用换行隔开。它不能证明数字与产品属性的语义关系，也不会重建“标签里有单位、值里只有整数”的表格数值。表格 schema 的行列标签及 `cell_ref` 不属于 cell.text 的 numeric 输入。
7. 本轮修复后，匹配前后边界拒绝字母、数字、下划线，继续拒绝更大十进制/千分位数字中的片段。相同 `10bar` 可以匹配相同证据；`10 bar` 不匹配仅含 `10bar` 的证据。

三类调用的 gating 不完全相同：

| 调用位置 | 执行数字 grounding 的条件 | 证据范围 |
|---|---|---|
| `_validate_claim_evidence` | factual claim 且 OBSERVED_PRODUCT_FACT、第一方文本标记或已观察第一方实体之一成立 | claim.page_refs |
| `_finalize_table` | 第一方文本标记、已观察第一方实体或非空 cell.page_refs 之一成立 | cell.page_refs |
| `_finalize_internal_link` | anchor 含第一方文本标记或已观察第一方实体 | 目标页面 P |

SECTION、resource section、link insertion claims 最终复用普通 claim 路径。EDITORIAL_TRANSITION/CTA 有数字会按 CLAIM_TYPE_CONTRACT 拒绝，并不进入此数字错误类别。

claim 有 claim_type，可表达 external context；cell 没有 claim_type，所以目前以 P 引用作为第一方 cell 信号。这是从代码结构得出的设计解释，没有历史设计文档证明作者动机。一般 context claim 即使带 P，也可能不执行数字 grounding；P 引用 cell 则一定执行。

**既有边界：**无 P、无第一方标记/实体的 cell 跳过数字 grounding，甚至没有 S 也可通过该分支。普通非第一方 context claim 也没有数字与 S 正文的 exact grounding。本轮只如实复现，没有把这些成功结果认定为“数字获得证明”，也没有扩大这一边界。若产品要求所有数字必须被 P/S 证实，需要另行确定 provider-independent 契约；不能仅靠引用存在来认定 grounded。

## B. 本次裸整数失败的具体执行路径

真实验收的尝试顺序和 terminal diagnostic 来自用户提供，provider 原始输出没有保留，不能恢复实际 cell 字符串。

只读检查该 run 的 SQLite artifacts 确认：C2 是 ADD_COMPARISON_TABLE，仅允许 P4/S1，schema 为一行五列。P4 extraction success；body content_truncated=true，structured_content_truncated=false。使用当前提取器统计 P4 投影得到九个数字表达式，其中四个 bare；这些计数不证明 provider 选择了其中某个数，也不输出证据正文。

执行路径：JSON → `_parse_specification` → `_materialize_table_cells` → `finalize_draft_item` → `_finalize_table` → scope/reference 检查 → 非空 page_refs 触发第一方 cell 路径 → 拼接 cell 所引 P 文本 → `_validate_numeric_grounding` → `_is_bare_number` → NUMERIC_NOT_GROUNDED。

对已给出的 `BARE_INTEGER`、total=2、grounded=1、ungrounded=1：可以确定一个表达式因 bare 规则拒绝，另一个通过非 bare + P matching。不能断言被拒数字在 P4 中不存在，因为 bare 路径先返回，未进入证据匹配。S1 的存在不能挽救这个表达式。

cell_ref catalog 固定绑定 change、row、column；解析时整个 text/page_refs/source_refs 一起存入 TableCellSpecification，排序只重排对象。排序后 `draft.cells[0]` 是 materialized index，不一定是 provider JSON 第一个 cell。行列坐标是 approved schema 的零基索引。受控反序 JSON 测试确认文本与引用没有被拆开；标签不会注入数字正文。没有证据证明本次对应关系发生错位。

## C. Prompt-validator 冲突

`adapters/deepseek_content_draft.py` 的初始 NUMERIC RULE 要求 product/first-party 数字来自引用 P，但没有明确禁止“P 中原样存在的 bare 数字”。因此复制合法证据中的纯材料编号、把单位留在列头而只写整数等输出可以满足字面 Prompt，同时违反 validator。这里是可证明的契约缺口；不能证明真实输出就是这些例子。

表格指令规定 cell_ref、引用绑定、覆盖和排序，却没有明确“任何带 P 的 cell 的所有数字必须在自身引用 P 中”。普通 claim 可以采用 GENERAL_TECHNICAL_CONTEXT，但 table cell 没有这个字段。有关 S-only number 的普通 claim 指令不能直接表达表格的 gating。

NUMERIC_NOT_GROUNDED retry_feedback 已有 `Never emit a bare number`；因此第二次并非完全没有 bare 禁令。它使用 `claim` / `omit the claim` 的措辞，未说明如何替换 table cell 并保持覆盖；且 system 和 retry 的规则并未完全对齐。没有 provider 原文和实际请求完整安全投影，不能认定模型没有收到或故意忽视指令。

## D. 可证明的代码缺陷与本轮修复

两个独立缺陷通过修改实现前的 RED 测试证明：

1. **提取引入空格：**`10bar` 被提取为 `10 bar`，`20°C` 被提取为 `20° c`；与原样证据不一致。现在直接保留规范化原文 span+tail 的邻接关系。不同空格形式之间仍拒绝匹配。
2. **token 边界过窄：**旧匹配只排除相邻数字，可把 `10 m` 匹配到 `10 mm`、`10 bar` 匹配到 `10 barrel` 或 `A10 bar` 的片段。现在边界也拒绝字母和下划线。这是收紧 exact matching，保留原有 decimal/digit collision 检查。

这两个缺陷与本次 terminal `BARE_INTEGER` 不是同一机制；不能宣称已经修复该真实 run 的根因。`_is_bare_number` 的定义与裸数字优先拒绝条件完全保留。

安全诊断补充：rule_id、1-based attempt、bare_number_count、evidence_mismatch_count、has_page_refs、has_source_refs、is_bare_number、evidence_match_failed。仍只定位 terminal 的第一个拒绝表达式。

- rule_id 为 BARE_NUMBER_FORBIDDEN 或 NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE。
- bare 与 evidence_mismatch 计数互斥，二者之和等于 ungrounded_count；grounded+ungrounded 等于表达式总数。
- evidence_mismatch_count 只计非 bare 的匹配失败；不为 bare 再做证据匹配。
- evidence_match_failed 说明**第一个拒绝表达式**是否进入证据匹配并失败；bare 的该值为 false，绝不意味着 bare 已在证据中证实。
- 各计数是诊断 observer 对同一失败字段的分类，包括失败表达式后面的数字；领域 validator 本身仍在第一个失败处返回。
- 元数据校验只允许固定规则、布尔值和有界计数/attempt；不包含数字字面值、单位文本、provider 原文或 P/S 正文。仅保留在进程和 CLI 安全投影中，artifact/SQLite/public progress 仍不保存。

本轮修改文件：`core/content_draft.py`、`workflows/content_draft.py`、`cli.py`；新增 `tests/test_content_draft_numeric_contract.py` 及本报告。没有修改 adapter Prompt、storage schema 或其他业务模块。

## E. 离线复现与回归

以下都是人工控制的 fixture，不是真实 P4 或 provider 输出：

| cell.text / 引用 | fixture 证据 | 观察结果 |
|---|---|---|
| Pressure 10 bar / P4 | P4: 10 bar | 通过 |
| Pressure 99 bar / P4 | P4: 10 bar | 拒绝：evidence mismatch |
| 316 / P4 | P4: 316 | 拒绝：bare |
| Pressure 10 bar and 316 / P4 | 两个值都出现在 P4 | 一个 grounded、一个 bare，拒绝 |
| Pressure 10 bar and 99 bar / P4 | 只有 10 bar 在 P4 | 一个 grounded、一个 mismatch，拒绝 |
| Pressure 10 bar / P4+S1 | P4: 10 bar | 通过；S 不是 numeric grounding 输入 |
| Buyer context 77 bar / P4+S1 | 77 bar 只在 S1 | 拒绝，P 引用不是数字证明 |
| Buyer context 77 bar / 仅 S1 | 无第一方信号 | 跳过数字 grounding；不能推导 S 证明了数字 |
| Buyer context 77 bar / 无引用 | 无第一方信号 | 既有 skip 分支；不能称为 grounded |
| 316 / 仅 S1 | 无第一方信号 | 既有 skip 分支；bare 禁令未在此触发 |
| Our pump pressure 10 bar / 仅 S1 | 第一方文本 | FIRST_PARTY_FACT_WITHOUT_PAGE |
| 任意数字 / P1 或 S99 | 不在 C2 scope | EVIDENCE_OUTSIDE_CHANGE_SCOPE，先于 numeric 检查 |
| 10bar、20°C / P4 | P4 原样紧邻单位 | 修复前 RED，修复后通过 |
| 10 bar / P4 | P4 只有 10bar | 保持拒绝 |
| 10 m、10 bar / P4 | 仅有 10 mm、10 barrel、A10 bar | 修复前误通过，修复后拒绝 |

新增十个 unittest 方法包含上表的 subtests、普通 claim 与 cell 的 gating 差异、排序绑定、诊断的固定枚举/计数/attempt/隐私边界。第一次 RED 是预期缺陷和缺少诊断字段的失败；边界修复也单独观察了三个 RED subtest。迭代中一个额外 attempt 测试构造重复 change plan，被现有输入一致性验证拒绝，已改用有效 specification 验证 attempt 上下文，未修改或绕过领域验证。

实际运行：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_content_draft_numeric_contract tests.test_content_draft_numeric_diagnostic tests.test_content_draft_table_coordinates tests.test_content_draft_core tests.test_content_draft_workflow tests.test_deepseek_content_draft_adapter -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q
```

相关六模块 targeted unittest：89/89 通过，exit=0。完整离线回归：1350/1350 通过，305.011 秒，exit=0。`git diff --check` 也通过。完整运行输出包含 Starlette/httpx 弃用警告、asyncio slow-task 提示以及预期的参数拒绝/端口占用 fixture 信息，没有测试失败。没有运行 opt-in 真实 integration scripts。

## F. 最小 Prompt 修订建议（本轮未应用）

建议仅给现有 NUMERIC RULE 与表格/repair 指令添加短句，不重写大段 Prompt，不放宽 validator：

> Wherever first-party numeric grounding applies, never emit a bare numeric expression, even when it appears in P evidence or its unit is in a table label. Copy the complete non-bare expression, preserving number-unit spacing, from the cited P evidence; never invent a unit.

> For every table cell with page_refs, every numeric expression must be supported by that cell's cited P evidence. source_refs cannot ground these numbers. If no compliant numeric expression is available, use grounded qualitative text while retaining cell_ref and required row/column coverage.

对应 retry 的 `omit the claim` 改为兼容操作的说明：ordinary claim 可省略；table cell 应改为 grounded qualitative text 并保留 coverage。建议把 S-only 指令明确限定为非第一方普通 context claim，避免暗示为 cell 添加 S 即可解除 P numeric 检查。

现有离线矩阵已经验证核心结果：bare 有 P 也拒绝；P+S 的 S-only 数字也拒绝；无数字的表格文字可保持覆盖。若下一轮实际修改 Prompt，还应增加 MockTransport 请求投影测试，证明初次与 repair 请求都携带新增约束；该测试不能证明真实模型遵从，仅证明指令确实发送。

不建议允许“列头有单位则 bare 合法”、允许“有 P 就算 grounded”，或把 S 文本加入第一方 P 匹配。若要支持材料编号/认证号等裸数字，应单独设计 typed numeric evidence contract，并由用户决定领域边界。

## G. 下一轮真实 Draft-only 建议

不建议原样重复当前 Prompt，也不能承诺本轮代码修复会消除真实 BARE_INTEGER。建议先应用并离线验证上述短 Prompt 修订，再在用户明确授权后进行一次限定 Draft-only；保持同一 evidence snapshot、provider 配置和 retry 预算，以新增安全规则诊断判断拒绝机制。

仍缺失：实际被拒表达式的安全类别（如材料编号、序号、单位来自标签等）、它与 P4 的对应关系、第一/第二次输出的差异。安全元数据足以分辨 bare/mismatch，却不能恢复具体文字或证明语义 entailment；不能据此猜测根因。P4 正文截断只能解释某些 evidence mismatch 的可能性，无法解释 bare 规则本身。
