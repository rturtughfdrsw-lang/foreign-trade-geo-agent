# Draft-only：C2 schema 与数字领域契约审查

日期：2026-10-08。run：`86d25a34-31de-4808-91c3-b0ed89461960`。

结论：确认 C2 的比较轴语义缺失，以及现有 bare 禁令与完整技术参数表达之间的设计冲突；不能确认历史 provider 具体输出或把该次失败唯一归因于其中之一。当前没有发现适合在不改变领域语义前提下修复的新增局部实现缺陷。本轮仅新增本报告，未修改 Prompt、运行代码、测试、批准计划、诊断字段或 provider 配置。

## A. 完整 C2 schema 与生成来源

只读连接 `.data/task17-final-acceptance/fresh-cli-3c5d419bdf5d4c07bf68d5fa20dcb96d.sqlite3`（SQLite `mode=ro`），按 run_id 读取五个上游 artifacts；通过现有 `decode_artifact` 校验并构造 `ContentDraftInput`、`build_content_draft_prompt(..., 'C2')`。没有写入历史库。

持久化 C2：

```json
{
  "change_id": "C2",
  "opportunity_ref": "R1",
  "source_action_code": "ADD_COMPARISON_TABLE",
  "operation_type": "ADD_COMPARISON_TABLE",
  "target_kind": "MODIFY_EXISTING_PAGE",
  "page_refs": ["P4"],
  "source_refs": ["S1"],
  "audit_refs": [],
  "locator": {
    "locator_kind": "EXACT_OBSERVED_HEADING",
    "page_ref": "P4",
    "observed_heading": "Process and equipment context",
    "observed_heading_kind": "H2"
  },
  "proposed_heading": "Process and equipment context",
  "comparison_table_spec": {
    "column_headers": [
      "Working Table Size",
      "X / Y / Z Travel",
      "Spindle Speed",
      "Spindle Taper",
      "Positioning Accuracy"
    ],
    "row_dimensions": ["Machine Weight"]
  },
  "content_points": [],
  "ordered_headings": [],
  "complete_page_order": false,
  "section_purpose": null,
  "internal_link_spec": null,
  "new_resource_spec": null,
  "requires_human_review": true
}
```

`locator.observed_context` 是已保存的页面上下文片段，不是额外的表格轴；报告未复制该正文。schema、行列名称及方向完全按原 artifact 保留。artifact 的 `status=success`、`requires_human_review=true` 本身不证明人类批准；本轮按用户指定的批准基线处理。旧 artifact 的 `writer_attempt_count=None`，不能据此恢复生成尝试次数。

| cell_ref | 坐标（零基） | 原 row_dimension | 原 column_header | 列的语义角色 |
|---|---|---|---|---|
| C2_CELL_001 | (0,0) | Machine Weight | Working Table Size | 工作台几何尺寸属性 |
| C2_CELL_002 | (0,1) | Machine Weight | X / Y / Z Travel | 三轴运动行程属性 |
| C2_CELL_003 | (0,2) | Machine Weight | Spindle Speed | 主轴转速属性 |
| C2_CELL_004 | (0,3) | Machine Weight | Spindle Taper | 主轴接口/锥度类别属性 |
| C2_CELL_005 | (0,4) | Machine Weight | Positioning Accuracy | 定位精度属性 |

`Machine Weight` 也是机器属性，属于质量；`Working Table Size` 属于长度/几何尺寸。两者同属“属性”这个角色，但量纲和含义不同，不能直接当作两个可比较对象。重量不是机型、配置、方案或应用实体；schema 也没有说明要表达“重量与尺寸之间的关系”。不能把这一行改读成某个机型、某个重量级别或隐含关系。

全部六个标签在 P4 中出现，在当前 S1 `content` 中均未出现。P4 保存了一个 `Sample Technical Specifications` 结构化表格：六行、每行两格，分别是属性及其数值/标识；它不是六个被比较对象的目录。不能因为抽到了六个合法标签，就把它们分配到两个比较轴。该表的 sample 标题也不能额外证明实际产品承诺或多个机型身份。

来源链：

1. Site-content packet 保存 P4 技术表。P4 extraction success；正文截断，结构化内容未截断。
2. Content Opportunity 的 R1 为 `EXPAND_OBSERVED_CONTENT`，授权 P4/P5、S1，行动包括 `EXPAND_PAGE_SECTION` 与 `ADD_COMPARISON_TABLE`。R1 没有定义具体行列轴。
3. Change Plan provider 选择 `column_headers` / `row_dimensions`；`workflows/change_plan.py` 解析，`core/change_plan.py` 校验并原样物化为 `ComparisonTableSpec`。不是 Draft 阶段发明这些标签。
4. Draft 的 `table_coordinate_catalog` 生成固定坐标；provider 只能填写 `cell_ref`、正文、P/S 引用，不能替换标签。当前一行五列的 coverage 因而要求五个 cell；一般多行 schema 的现有契约只要求每行每列覆盖，并非强制完整笛卡尔积。

上游 validator **不仅检查结构**：`ComparisonTableSpec.__post_init__` 检查数量、唯一性、长度；`_validate_table` / `_validate_phrase` 还检查禁止语法、absence claims 和标签在本 operation 引用 P/S 中的规范化连续子串 grounding。但是它们没有检查比较对象身份、轴角色、量纲关系、cell 的关系定义或可填充性。本轮对原 schema 调用 `_validate_table` 返回 `None`，与这一实现一致。

## B. BARE_NUMBER_FORBIDDEN 的原始目的与边界

Git 历史中 `1e0a79e`（`feat: add grounded content draft generation`）已经存在 `_is_bare_number` 及“bare 先拒绝”的实现。原始 numeric 文档字符串要求 number+unit expression 来自证据；原始 Prompt 要求第一方数字在引用 P 中原样出现，并禁止发明、换算。现有 `test_bare_number_fails_closed` 明确要求即使 P 与 claim 都包含相同 bare 值，也拒绝。

据此可以确认：这是一项有意的 fail-closed 格式限制，并非本轮新引入的失配。其防止脱离单位/上下文的数字成为产品参数的动机是合理推断；未找到更详细的历史设计说明，不能替作者声称它是完整技术参数语法。

实际执行顺序：

1. `_normalized_text` 对草稿及 P 各文本投影执行 NFKC、casefold、空白合并；不同 P/字段投影以换行连接。
2. `_NUMERIC_SPAN_RE` 提取数字 span；`_NUMERIC_TAIL_RE` 接收符号、字母及有限斜线形式，保留原有邻接空格。
3. 每个表达式先执行 `_is_bare_number`：不含 `[a-zµ%°"'/-]` 中任一字符便是 bare。整数/小数可拒绝；斜线、连字符、普通英文字母也可能使表达式 non-bare。因此 non-bare 不等于物理单位有效。
4. bare 立即拒绝，**不进入** P evidence matching。非 bare 才用 `_numeric_expression_is_present` 检查规范化文本中的完整 token；拒绝嵌在更大数字、字母、下划线或十进制片段内的匹配。
5. cell 有 P 引用就进入第一方 numeric 检查；只看该 cell 引用的 P。S 不参与，schema 标签也不会给 cell 数字补单位。首个失败拒绝整个 draft；诊断 observer 再统计该失败字段的表达式分类。

格式是否合法、证据中是否出现、证据是否支持该属性/实体，是三个独立问题。现在第一个是简单字符禁令，第二个是表达式存在匹配，第三个未被数字校验证明。`grounded_count` 应解读为“non-bare 且表达式匹配计数”，不能解读为语义 entailment。

已确认的合法工程表达边界：

| 全合成表达（证据也原样包含该表达） | 当前提取 | 结果 |
|---|---|---|
| `42 × 24 mm` | `42`、`24 mm` | 一个 bare，拒绝完整尺寸 |
| `42 x 24 mm` | `42 x`、`24 mm` | 无 bare，通过；`x` 被当作字母 tail |
| `100 / 80 / 60 mm` | `100`、`80`、`60 mm` | 两个 bare，拒绝共享单位的三轴值 |
| `0–9000 rpm` | `0`、`9000 rpm` | 一个 bare，拒绝 en dash 范围 |
| `0-9000 rpm` | `0-9000 rpm` | 无 bare，通过 |

这证明完整工程参数可能被系统性拒绝，同时相同语义的不同书写形式受到不同待遇；**不是建议改字符或补单位来过关**。这里讨论的“合法”是工程表达合法，不是声称它们满足当前已定义的 bare 禁令。接纳共享单位、乘号或范围形式，会改变数字表达式领域定义，不能作为本轮偷偷放宽 validator 的实现修补。

## C. 上下游契约冲突

存在两个可确认的设计缺口：

- 上游允许分别词法 grounded 的属性标签组成任意轴；下游固定执行这个轴、要求 coverage，却没有比较主体或关系语义。这使不合理 schema 可以被验证为 SUCCESS，Draft 又无权纠正。
- 上游 evidence 可以合法保存完整多轴/范围参数；下游逐个数字应用 bare 禁令，不能理解最后一个分量携带的共享单位。完整复制原证据仍可被拒绝。

现有契约并非形式上完全不可满足：无数字的保守文字可以填满 schema 并通过。但“可通过结构校验”不等于“形成有价值且可信的比较表”。使用这种文字不能解决比较主体缺失。当前 Prompt 已对齐 bare 禁令，也没有改变上述领域问题。

## D. 离线复现、安全诊断与根因分类

cell 实验直接运行现有离线 parser/finalizer；grammar 实验调用现有 extractor 与 numeric validator；provider JSON 为人工构造。没有历史 provider 原文。受控复现的安全摘要及本报告不含真实 P4 参数正文或数字指纹。受控抄录使用内存中的 P4 数值，以下仅记录形状和拒绝类别；早期只读检查的一次输出问题见 E 节。

| 受控实验 | 证据来源 | 观察结果 |
|---|---|---|
| C2_CELL_001 填入完整 P4 工作台尺寸原表达 | 历史上游 P4；provider 输出人工构造 | BARE_NUMBER_FORBIDDEN；grounded=1、bare=1、mismatch=0 |
| cell=`316`，P4 合成文本也含该值 | 全合成 | bare 拒绝；grounded=0、bare=1、mismatch=0 |
| cell=`99 kg`，P4 合成文本仅含 `42 kg` | 全合成 | NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE；bare=0、mismatch=1 |
| 将 `Machine Weight 42 kg` 填入 Working Table Size cell，P4 合成文本含相同重量事实 | 全合成 | 校验通过；数字来自错误属性仍没有语义拒绝 |
| 原 C2 schema 保持不变，填写五个不同的非数字属性说明 | 全合成 | 校验通过；不产生语义 diagnostic |
| cell=`42 × 24 mm`，P4 合成文本含相同完整尺寸 | 全合成 | grounded=1、bare=1、mismatch=0 |

原 P4 各属性值的提取形状：工作台尺寸 2 个表达式/1 bare；三轴行程 3/2；转速 2/1；锥度 0/0；精度 1/0；重量 1/0。这些是当前 extractor 的结果，不是历史 provider 选择的值。锥度的字母数字标识未被提取为 numeric expression，也不能据此声称它获得了数值证明。

受控抄录证明：有一个明确机制能够生成与最新失败相同的计数，而且相应表达确实来自该 upstream P4。它**不能**证明真实 provider 就抄了这个表达，不能证明真实 bare 数字在 P4 中出现或没有出现，也不能证明历史失败由 schema 的语义问题直接触发。

现有 safe diagnostic 的能力足够定位两类数值失败：

- `rule_id=BARE_NUMBER_FORBIDDEN`：匹配尚未执行；`evidence_match_failed=false` 不是“已经匹配成功”。
- `rule_id=NUMERIC_EXPRESSION_NOT_IN_CITED_PAGE`：非 bare 已进入 P 匹配并失败。
- `TABLE_SCHEMA_MISMATCH`：坐标/覆盖等结构错误，不是语义不合理；语义错误的合成 cell 可以成功，没有 numeric diagnostic。

目前不新增字段。静态 artifact 审查及离线实验已能完成本轮判断；新增“同值出现”布尔字段仍不能证明实体/属性 grounding。没有输出普通哈希、数字指纹或原文，没有向 artifact、SQLite 或公共 progress 增加诊断载荷。

| 分类 | 判断 | 证据与限度 |
|---|---|---|
| A. 上游产生语义不合理的比较表格 | 确认 schema 缺少比较主体/关系语义 | 同一参数表的六个属性被拆成两个轴；无法确定交叉 cell 意义。不是历史 numeric 失败的充分证明 |
| B. 合理 schema 下 provider 无法稳定遵守 | 未成立 | 当前 schema 合理性前提未满足；两次失败只能证明该次生成未满足当前契约，不能量化一般可靠性 |
| C. 数字格式契约过严 | 确认设计边界冲突 | 同证据中的完整共享单位/范围表达被拒绝；直接抄录 P4 可复现相同计数 |
| D. 识别或证据匹配确定性实现缺陷 | 本轮未证明需要局部修复的新增缺陷 | 观察到的拆分/字符差异是真实的语法局限；改变它们需要先明确领域 grammar，不是偏离既定规则的实现修补。先前已修复的邻接空格/token 边界缺陷不能解释当前 bare 先拒绝 |
| E. 证据不足 | 历史具体失败归因仍不足 | 无原始输出；无法唯一关联 bare 值、来源或语义意图 |

## E. 实际变更与验证

本轮唯一新增文件：本报告。无运行代码、测试、Prompt、诊断模型、存储 schema 或计划修改；因此没有实施 RED/GREEN 修复，也没有为增加数量新增测试。

实际运行：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_change_plan_core tests.test_change_plan_workflow tests.test_deepseek_draft_numeric_prompt tests.test_deepseek_content_draft_adapter tests.test_content_draft_numeric_contract tests.test_content_draft_numeric_diagnostic tests.test_content_draft_table_coordinates tests.test_content_draft_core tests.test_content_draft_workflow -q
```

结果：235 tests，7.662 秒，OK，exit=0。复用了上游结构/词法 grounding、数字格式/匹配、diagnostic、坐标及请求契约测试。两个 PowerShell 内联 Python 离线 probe 分别执行受控 cell/assertions 和全合成 grammar assertions，均 exit=0。

一次早期只读探针误引用不存在的 `_page_evidence_text`，ImportError、exit=1；随后改用实际函数 `_evidence_text`，重跑成功。该失败不是业务测试失败。一次上游表格检查把首行当表头显示了一个已保存的参数值，后续改为仅输出标签及表达式计数；没有将其保存为诊断资产或本报告正文。

`git diff --check` exit=0。历史 1356/1356 与 97/97 是用户给定/此前记录，本轮没有重新运行 full discover，不能将其作为本轮完整回归结果。纯报告变更无需完整回归。

没有调用真实 DeepSeek、WordPress、真实 CLI 6/6、真实 LiveComposition 或 integration scripts。保留所有已有 dirty 文件；没有 commit、push、merge 或历史改写。

## F. 推荐最小设计修订（未实施）

优先解决比较语义，再决定工程数字表达范围。

1. **当前基线的最小处置：**保留 C2 artifact，明确标记它不具备进入真实比较表验收的语义条件。重新规划必须产生新的可审查计划；不得换掉这一行、反转轴、删除 cell 或偷偷把它当普通规格表。若证据只支持单份 sample 参数清单，应在新计划中选择已有适当的技术说明操作，或省略比较操作。
2. **比较契约的最小方向：**新契约固定“可识别的比较主体 × 可识别的属性”轴角色，要求每个主体及属性绑定 observed evidence 候选/出处，检查主体是否存在、属性是否对应主体、每个所需 cell 是否可填充。P 页引用本身不能代替主体身份。关系分析表若要支持，需要独立定义关系含义，不从现有标签猜测。没有可比较主体时 fail closed；无需新增 provider 或网络端口。
3. **数字契约的最小方向：**先定义有限的 typed expression grammar（单值、范围、多分量尺寸/行程、明确共享单位），引用完整的 observed 表达式及其属性/主体/证据位置。必须同时验证格式与正确证据绑定，维持单位、分量、顺序与原文表达一致；不做单位换算、不搜索全站同值、不用 S 替代第一方 P。普通无上下文 bare 仍拒绝。材料号/型号属于另一种类型，不能凭字母 tail 或任意符号豁免。
4. **下次实现前的 RED 边界：**无比较主体的属性×属性 schema 应在 Draft 前拒绝；将重量写入尺寸属性即使同值存在也应拒绝；完整 observed 多分量表达在正确主体/属性绑定下应允许，分量/单位/出处不同则拒绝。这些是新设计获认可后才适用的预期，不能现在用它们强迫 V1 规则变 GREEN。

兼容性影响：V1 已保存 artifact 继续可读、可审查，不能无声重解释；新语义校验会使包括 C2 在内的部分既有 SUCCESS 计划不再具备新 Draft 输入资格。建议用显式版本/能力边界区分新生成契约，必要时升级 Change Plan/Draft payload 版本并保留旧 codec。新 row 主体绑定、typed numeric evidence 会影响 core 模型、物化/parser、adapter 请求投影、serialization 和对应测试；应在获批设计后单独实施。重新规划不得复用旧 schema 的 cell_ref 身份来冒充相同计划。Prompt 更长或 retry 更多都不能替代这些变更。

## G. 下一次真实验收：NO-GO

对“沿用当前 C2 schema、继续验证比较表成品成功”的真实 Draft-only 验收为 **NO-GO**。即使偶然通过，当前验证仍可能接受属性错配，不能据此宣布根因解决。已不需要以追加一次相同真实请求来证明格式边界。

GO 的最低条件：明确采用哪种表格产品语义；完成新计划及人工审查；对批准的数字 grammar/证据关系做离线 RED/GREEN 和必要完整回归；保持 draft-only、provider 配置及现有预算；获得下一次具体真实调用授权。当前 C1 通过不证明 C2 合理；C3 未执行仍是未验证状态。
