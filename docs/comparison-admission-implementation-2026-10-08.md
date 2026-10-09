# SEO MVP 比较操作准入与主动放弃

日期：2026-10-08。本轮只实现能力关闭与执行拒绝，不实现 Comparison Table V2。

## A. 当前 Planning 是否允许没有比较表格

允许。`CHANGE_OPERATION_COMPATIBILITY` 按每个 R 的 `action_codes` 授权；最终材料的 `allowed_operation_types` 再按候选、引用和结构最低要求收窄。原 parser 只要求**响应中包含的 R** 有一个 primary、最多一个 secondary，并不要求所有 R 都出现，也不要求比较操作。新计划可为空；SUCCESS 本身不是批准。

`ChangePlanReport` 保留连续 C 编号、每 R 最多两项、规范身份去重、操作上限及 `requires_human_review=true`。没有发现必须含比较操作的领域约束，因此不新增替代 action 或占位操作。

## B. 新比较操作准入与拒绝边界

没有可信主体、属性和事实关系准入入口，当前比较能力一律不可用，不接受 provider 自报证明。

- Planning availability 不再把 `ADD_COMPARISON_TABLE` action 转成直接比较或比较新资源能力。另有非比较 action 授权时，普通章节、重排、链接和无表的新资源保持原有资格。
- 仅有比较 action 的 R 在**新生成材料**中列入 `unavailable_opportunities`，原因是 `COMPARISON_UNAVAILABLE`，不出现在可生成的 `opportunities` 中。原 Content Opportunity 报告和 catalog 不改写。其他可执行 R 可以继续；全部 R 仅支持比较时，preflight 返回 INVALID_INPUT，writer 调用为零，不伪造空计划成功。
- 最终 HTTP 材料仍与确定性投影逐项比较，不能通过伪造 allowlist 或删除不可用声明绕过 preflight。其他原因造成的空 allowed set 仍 fail-closed。
- `validate_and_finalize_specification` 在共同引用/action 约束后拒绝直接比较、比较 action、新资源比较 purpose 及任何 nested table。provider 提交有效普通操作和比较操作时，整份新输出 INVALID_OUTPUT，无部分成功、无比较能力 retry。
- Draft 的稳定输入校验拒绝整份含比较的 Plan，发生在任何 writer 调用前。公开 prompt builder、prompt 构造、直接 Draft finalizer 和直接 DeepSeek Draft adapter 也检查资格，防止旁路。普通 C1 不能用“先执行 C1”的方式掩盖同一 Plan 中无资格的 C2。
- 公共拒绝使用 allowlisted `COMPARISON_UNAVAILABLE`，不含轴、事实值、正文或 provider 原文。Planning 输出失败的 run diagnostic 映射到既有 `OPERATION_NOT_ALLOWED`，保留安全原因且避免扩展旧 SQLite v4 CHECK 约束。失败 artifact 的 error 保留具体比较拒绝类别。

主动放弃发生在新的 Planning 输入/能力选择阶段；执行阶段不删除、不替换、不重排既有 Change。旧含比较 Plan 必须保留，通过重新规划取得新的有效 Plan，再重新审查。`unavailable_opportunities` 是生成材料中的临时诊断，不是新增 artifact 字段或批准记录。

## C. 本轮实际修改文件

生产代码共四个文件：

| 文件 | 原因 |
|---|---|
| `src/foreign_trade_geo_agent/core/change_plan.py` | 确定性 availability、比较专属 R 的显式不可用投影、公共能力拒绝及新 specification 准入 |
| `src/foreign_trade_geo_agent/core/content_draft.py` | 整份 Plan 输入拒绝、prompt 构造及直接 finalizer 防线 |
| `src/foreign_trade_geo_agent/adapters/deepseek_content_draft.py` | 直接 adapter 在 HTTP 前复查输入和 operation 资格 |
| `src/foreign_trade_geo_agent/workflows/change_plan.py` | 新拒绝类别映射到旧运行诊断 enum，避免数据库迁移 |

新增 `tests/test_comparison_admission.py`（15 项行为测试）、`tests/comparison_fixtures.py`（显式 V1 历史模型及保留的底层 cell 校验 fixture）。更新 `tests/test_change_plan_core.py`、`tests/test_change_plan_material_availability.py`、`tests/test_change_plan_workflow.py`、`tests/test_content_draft_core.py`、`tests/test_content_draft_numeric_diagnostic.py`、`tests/test_content_draft_table_coordinates.py`、`tests/test_content_draft_block_budget.py`、`tests/test_content_draft_numeric_contract.py`、`tests/test_deepseek_draft_numeric_prompt.py`。

旧测试不再通过新 Planning 创建历史表格成功样本。V1 结构、locator、词法 grounding、坐标排序/覆盖、字段预算、引用范围、数字单位及旧 Draft 解码断言仍在适当的读取/底层校验层保留；公开执行另断言拒绝。普通内容的 retry/反馈测试改用仍可执行的无表 supporting resource 或 section，保留原有 retry、预算和安全诊断要求。比较在 numeric validation 前被拒绝，因此新执行不再产生表格 numeric diagnostic；计数、attempt、规则优先级和脱敏断言改用合法普通 claim 验证，表格 per-cell 数字规则仍由底层 V1 validator 验证。

本报告是唯一新增文档。没有修改两份参考报告、数字 grammar、DeepSeek Prompt、codec、artifact payload 版本、SQLite schema、GEO 功能或审核/交付实现。

## D. 历史 V1 artifact 兼容性与审核

保持 V1 dataclass 读取模型和严格 codec：已有标签、cells、引用、字段默认兼容和 SUCCESS 状态均原样读取，不补造语义证明。旧表格的读取成功不授予新的 Draft 执行资格；无表 V1 Plan 经既有输入校验仍可执行。

真实历史库以 SQLite `mode=ro` 核查 run `86d25a34-31de-4808-91c3-b0ed89461960`：五个 V1 artifact 均 decode/encode/decode 等值；schema 仍为 v4；真实 C2 的新 Draft 输入资格为 `COMPARISON_UNAVAILABLE`。核查前后数据库字节摘要相同，未输出参数或正文。该历史 run 没有旧 Content Draft artifact，旧表格 Draft 的往返测试使用合成历史模型。

代码没有独立持久化的 Change Plan 批准状态；`requires_human_review` 是审核要求，不能解释为已经批准。原流程在内容 Draft 后停留于审核边界，WordPress 交付仍须明确批准且 draft-only。本轮不把重新规划视为自动批准，也不改变审核边界。

## E. RED/GREEN 与回归

- 修改前完整离线基线：1356 tests，297.124 秒，OK，exit=0。
- 首批新准入 RED：11 tests，10 failures；普通章节正向路径已通过。失败明确复现旧比较仍可生成/执行、嵌套入口可执行、旧 C2 未拒绝及生成资格未收窄。
- 最小实现后：11/11 GREEN。直接 adapter 的 HTTP 前拒绝另做 RED（旧行为发出 MockTransport 请求并 SUCCESS），补防线后 GREEN。最终新增模块 15/15 GREEN。
- 相关回归初次有 36 failures、3 errors（旧比较成功 fixture/预期冲突）；迁移显式历史 fixture 时另发现两项 fixture 构造错误，已纠正。首轮完整回归 1371 tests，303.510 秒，17 failures，均为额外模块沿用旧比较可执行 fixture。追加修正过程中另有一个普通 section 材料不含 table key 的测试 KeyError，改为正确的缺省读取。最新相关模块回归：310 tests，23.101 秒，OK，exit=0。
- 修改后最终完整离线回归：1371 tests，293.713 秒，OK，exit=0。首轮 17 个失败均已修正，测试总数为原 1356 加本轮新增 15。
- `git diff --check` exit=0。相对本轮开始的文件字节快照，本轮只新增/修改 16 个相关文件（4 个生产文件、11 个测试文件、1 份报告），没有删除文件，其余已有 dirty 文件原样保留。另按源代码逐段核对数字 grammar/函数和 system prompt 未变，storage 文件与本轮开始的字节内容一致。

相关模块命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_comparison_admission tests.test_change_plan_core tests.test_change_plan_material_availability tests.test_change_plan_workflow tests.test_content_draft_core tests.test_content_draft_workflow tests.test_content_draft_table_coordinates tests.test_content_draft_numeric_diagnostic tests.test_content_draft_block_budget tests.test_content_draft_numeric_contract tests.test_deepseek_draft_numeric_prompt tests.test_deepseek_change_plan_adapter tests.test_deepseek_content_draft_adapter tests.test_history_serialization -q
```


首轮完整回归的 17 个失败名称（均已在最新相关回归中通过）：

- `test_table_contract_and_rejection_use_the_same_cell_limit (test_content_draft_block_budget.DraftBlockBudgetTests.test_table_contract_and_rejection_use_the_same_cell_limit)`
- `test_attached_unit_expression_keeps_observed_spacing (test_content_draft_numeric_contract.TableNumericContractTests.test_attached_unit_expression_keeps_observed_spacing)`
- `test_claim_and_cell_have_different_first_party_gates (test_content_draft_numeric_contract.TableNumericContractTests.test_claim_and_cell_have_different_first_party_gates)`
- `test_first_attempt_diagnostic_preserves_supplied_attempt_context (test_content_draft_numeric_contract.TableNumericContractTests.test_first_attempt_diagnostic_preserves_supplied_attempt_context)`
- `test_identical_attached_units_are_grounded_but_spacing_conversion_is_not (test_content_draft_numeric_contract.TableNumericContractTests.test_identical_attached_units_are_grounded_but_spacing_conversion_is_not)`
- `test_new_diagnostic_fields_reject_unsafe_or_inconsistent_values (test_content_draft_numeric_contract.TableNumericContractTests.test_new_diagnostic_fields_reject_unsafe_or_inconsistent_values)`
- `test_provider_matrix_preserves_fail_closed_numeric_contract (test_content_draft_numeric_contract.TableNumericContractTests.test_provider_matrix_preserves_fail_closed_numeric_contract)`
- `test_safe_diagnostic_counts_each_rejection_without_literal_text (test_content_draft_numeric_contract.TableNumericContractTests.test_safe_diagnostic_counts_each_rejection_without_literal_text)`
- `test_safe_diagnostic_separates_bare_rule_from_evidence_mismatch (test_content_draft_numeric_contract.TableNumericContractTests.test_safe_diagnostic_separates_bare_rule_from_evidence_mismatch)`
- `test_sorting_keeps_numeric_text_and_refs_at_approved_coordinate (test_content_draft_numeric_contract.TableNumericContractTests.test_sorting_keeps_numeric_text_and_refs_at_approved_coordinate)`
- `test_unit_prefix_and_embedded_identifier_are_not_exact_numeric_evidence (test_content_draft_numeric_contract.TableNumericContractTests.test_unit_prefix_and_embedded_identifier_are_not_exact_numeric_evidence)`
- `test_controlled_qualitative_retry_preserves_cell_ref_text_and_refs (test_deepseek_draft_numeric_prompt.DraftNumericPromptRequestTests.test_controlled_qualitative_retry_preserves_cell_ref_text_and_refs)`
- `test_initial_and_retry_requests_stay_within_prompt_envelope_budgets (test_deepseek_draft_numeric_prompt.DraftNumericPromptRequestTests.test_initial_and_retry_requests_stay_within_prompt_envelope_budgets)`
- `test_initial_request_carries_bare_and_cell_local_numeric_rules (test_deepseek_draft_numeric_prompt.DraftNumericPromptRequestTests.test_initial_request_carries_bare_and_cell_local_numeric_rules)`
- `test_initial_request_forbids_evasion_and_unverified_comparisons (test_deepseek_draft_numeric_prompt.DraftNumericPromptRequestTests.test_initial_request_forbids_evasion_and_unverified_comparisons)`
- `test_retry_keeps_system_rules_and_replaces_ambiguous_omission_guidance (test_deepseek_draft_numeric_prompt.DraftNumericPromptRequestTests.test_retry_keeps_system_rules_and_replaces_ambiguous_omission_guidance)`
- `test_retry_preserves_material_scope_catalog_and_coverage_instructions (test_deepseek_draft_numeric_prompt.DraftNumericPromptRequestTests.test_retry_preserves_material_scope_catalog_and_coverage_instructions)`

完整回归命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
```

## F. 普通 SEO Draft 的比较表格阻塞

合法无比较 Plan 可执行；即使上游 R 同时建议比较，新 Plan 选择原已授权的章节操作也可生成普通 Draft。独立比较专属 R 的不可用不会要求给普通 R 添加表格。只获比较授权的材料不自动获得普通内容 action。

含旧 C2 的整份 Plan 仍明确拒绝，不能靠删除 C2 或继续尝试其 cells 变成成功；需新计划和新审查。普通 Draft 的既有数字、安全和 grounding 约束继续生效，关闭比较能力不承诺任何 provider 请求必然成功。

## G. 下一次 Draft 验收 GO/NO-GO

在离线完整回归通过后，使用**新生成、不含任何比较操作/brief、引用和授权合法、经重新审查的计划**进行普通 SEO Draft 验收为条件 GO。具体真实 DeepSeek 调用仍需单独授权；本轮不执行。

沿用历史 C2、任何直接/嵌套比较表格、完整 Comparison Table V2 或据此宣布真实 CLI 6/6 成功均为 NO-GO。未来开放比较能力需可信语义准入和独立设计/测试，不能仅放宽 allowlist 或 Prompt。

没有调用真实 DeepSeek、WordPress、真实 CLI 6/6、真实 LiveComposition 或 opt-in integration scripts。未 commit、push、merge，保留本轮开始已有 dirty working tree。
