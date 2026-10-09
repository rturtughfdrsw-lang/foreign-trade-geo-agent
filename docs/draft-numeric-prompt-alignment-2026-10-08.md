# Draft 数字生成指令契约对齐（2026-10-08）

本轮只修订 DeepSeek Draft 的 system Prompt 和 NUMERIC_NOT_GROUNDED retry 指导，并新增离线请求契约测试。以下 diff 以本轮开始时的 dirty 文件快照为基线，不包含既有改动。

变更文件：

- `src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py`：数字与表格生成约束。
- `src/foreign_trade_geo_agent/core/content_draft.py`：仅数字 retry 指导字符串；validator、数字规则、类别白名单均未修改。
- `tests/test_deepseek_draft_numeric_prompt.py`：六个离线测试。
- 本报告。

## A. Prompt 修改前后的精确差异

system Prompt 从 4992 增至 6111 字符，UTF-8 字节数同为 6111，低于 8000 字符 / 16384 字节预算。没有增加长示例，也没有调整 provider 配置。

```diff
--- src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py (turn baseline)
+++ src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py
@@ -52,3 +52,4 @@
 FIRST-PARTY RULE: any claim about our/our company/our factory/our pump/our product/model/certification/warranty/maximum/material code/port size, or claim_type OBSERVED_PRODUCT_FACT, must cite at least one P page. S evidence alone never establishes a customer-specific fact.
-NUMERIC RULE: any product or first-party numeric value (flow, pressure, temperature, dimension, material code, port size, certification number, percentage, price, warranty duration) must appear verbatim in the cited P evidence. Never invent or convert numbers. A numeric expression found only in S evidence must never become an OBSERVED_PRODUCT_FACT. Adding a P reference does not make an S-only number a first-party fact; use it only as GENERAL_TECHNICAL_CONTEXT with source_refs or omit it. When a content point has empty observed_in_page_refs, never turn it into an OBSERVED_PRODUCT_FACT; use only its observed_in_source_refs or omit it. For every content point, use only its allowed_claim_types and required_page_refs and required_source_refs; never add a reference outside those point-specific lists.
+NUMERIC RULE: any product or first-party numeric value (flow, pressure, temperature, dimension, material code, port size, certification number, percentage, price, warranty duration) must appear verbatim in the cited P evidence. Never invent or convert numbers. Never emit a numeric expression the validator treats as bare (including standalone integers and decimals), even if it appears in P evidence or its unit is in a table label. Copy only complete non-bare expressions, preserving number-unit spacing; never invent or append units, symbols, or percentages to bypass validation. Each comparison-table cell's numbers must come from that cell's own cited P evidence. The presence of page_refs or source_refs alone does not establish numeric grounding; never substitute numbers from another cell, another Change, or an uncited page. A numeric expression found only in S evidence must never become an OBSERVED_PRODUCT_FACT. Adding a P reference does not make an S-only number a first-party fact; use it only in non-first-party ordinary claims as GENERAL_TECHNICAL_CONTEXT with source_refs or omit it. When a content point has empty observed_in_page_refs, never turn it into an OBSERVED_PRODUCT_FACT; use only its observed_in_source_refs or omit it. For every content point, use only its allowed_claim_types and required_page_refs and required_source_refs; never add a reference outside those point-specific lists.
+When a number cannot be used safely under the evidence and expression contract, prefer accurate, conservative non-numeric wording supported by current evidence; never invent replacement facts. Preserve required table cells, cell_ref coordinates, schema, and row/column coverage; never evade numeric validation by omitting a required cell, deleting a coordinate, or changing the schema. If evidence cannot support a specific comparison, do not assert unverified advantages, rankings, or performance conclusions.
 EXTERNAL RULE: S evidence supports only general technical context, industry explanation, and buyer considerations. Paraphrase briefly; never copy long source prose.
--- src/foreign_trade_geo_agent/core/content_draft.py (turn baseline)
+++ src/foreign_trade_geo_agent/core/content_draft.py
@@ -144,6 +144,8 @@
         ContentDraftValidationCategory.NUMERIC_NOT_GROUNDED: (
-            "Regenerate the complete response. Remove every numeric expression "
-            "that is not copied verbatim from the claim's cited P evidence. "
-            "Never emit a bare number; omit the claim when no grounded numeric "
-            "expression is available."
+            "Regenerate the complete response under the system NUMERIC RULE. "
+            "Never emit a bare number. Replace unsafe numeric claims or cell "
+            "text with accurate, conservative non-numeric wording supported "
+            "by current evidence; do not invent replacement facts. Preserve "
+            "required table cells, cell_ref coordinates, schema, and row/column "
+            "coverage."
         ),
```

## B. 首次 Prompt 与 retry 的契约一致性

使用实际 ContentDraftWorkflow → DeepSeekContentDraftWriter → httpx.MockTransport 请求边界验证：先返回一个 P 中原样存在的 bare 整数，触发现有 NUMERIC_NOT_GROUNDED retry；再返回保守的非数字 cell 文本。

两次请求的 system message 完全一致，均携带新增约束。retry user material 仅改变 `contract.retry_feedback`，其余证据、Change、catalog、预算材料完全一致。retry 显式遵守 system NUMERIC RULE，并要求重生成完整响应、禁止 bare、保守替换 claim/cell 文本及保留表格覆盖。旧 `omit the claim` 已移除。

S-only 数字的 GENERAL_TECHNICAL_CONTEXT 指导限定为非第一方普通 claim，不再暗示 comparison cell 可依靠 S 引用解除 P 数字约束。首轮明确：引用存在本身不是 grounding、每个 cell 的数字只能来自自身引用的 P、不能借用其他 cell/Change/未引用页面的数字。

workflow、retry 次数、类别白名单、调用预算、provider model/temperature/token 配置均保持原状。

## C. 表格覆盖不变量

保持现有 exact cell 字段 `{cell_ref,text,page_refs,source_refs}`，从 approved catalog 选择唯一 cell_ref，不输出 row_dimension/column 字段。每个 supplied column 和 row dimension 至少覆盖一次；没有新增完整笛卡尔网格要求。

新增 Prompt 明确禁止为绕过数字校验省略必需 cell、删除坐标或修改 schema。受控一行五列回复在 retry 中反序提交，经原有解析与排序后五列齐全，text/page_refs/source_refs 仍绑定各自 cell_ref。既有缺列、缺行、重复/未知/跨 Change cell_ref 拒绝测试均通过。

core 与本轮开始快照比较确认：除数字 retry 指导字符串外，文件文本完全一致。没有放宽 validator，也没有改变 grounding 判定或 Draft domain。

## D. 新增离线测试结果

六个新增测试验证实际发送的首轮/retry 请求、数字约束、禁止编造单位或替代事实、禁止无证据比较、schema 与覆盖、cell_ref 绑定以及 Prompt/envelope 预算。MockTransport 仅替代 HTTP 外部边界，Prompt 构建、workflow、解析、finalizer 使用实际代码。

RED：首次运行六个测试，缺失约束与旧 omission 指导产生 17 个预期断言失败（包含 subtests），无测试加载错误。随后补充“standalone integers and decimals”说明的断言，单独观察一个预期 RED，再补充该短句。

GREEN：新增六个测试全部通过；相关七模块共 95/95 通过，3.441 秒，exit=0。

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_deepseek_draft_numeric_prompt tests.test_deepseek_content_draft_adapter tests.test_content_draft_numeric_contract tests.test_content_draft_numeric_diagnostic tests.test_content_draft_table_coordinates tests.test_content_draft_core tests.test_content_draft_workflow -q
```

这些测试证明指令随请求发送、受控回复保持原有契约；不能证明真实 DeepSeek 会遵从或真实生成成功。

## E. 完整离线回归

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

实际执行上述完整发现命令并将输出重定向到临时日志：1356/1356 PASS，216.809 秒，exit=0，日志无 FAIL/ERROR 测试头。`git diff --check` exit=0。

完整日志含既有 Starlette/httpx 弃用警告、asyncio slow-task 提示和预期的参数/端口拒绝 fixture 输出；Git 含 LF/CRLF 提示。一次日志摘要打印因 GBK 控制台无法编码替换字符而失败，改用安全转义后成功读取，未涉及测试或业务代码失败。

未调用真实 API、WordPress、真实 CLI 6/6、真实 LiveComposition 或 opt-in integration scripts。保留既有 dirty working tree；没有 commit、push、merge 或 Git 历史操作。

## F. 下一次受控真实 Draft-only 验证条件

具备本轮范围内的离线准备条件：指令缺口已对齐、请求约束与表格不变量有离线覆盖、完整回归通过。下一次真实验证仍需用户对具体 Draft-only API 调用明确授权；本报告不构成授权。

建议使用同一 evidence snapshot，保持 provider 配置、retry 白名单和预算，限定 Draft-only，并查看现有安全数字诊断。真实裸整数的具体来源仍未知，Prompt 修改不能证明真实 provider 故障已经解决。只有新的真实验收通过，才能确认该次生成成功；无法在当前证据与表达契约下安全使用的数值，仍须保守表达，不能编造单位、证据、替代事实或优势结论。
