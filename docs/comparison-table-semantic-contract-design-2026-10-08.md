# ADD_COMPARISON_TABLE 语义契约与兼容性设计

日期：2026-10-08。参考：`draft-schema-numeric-contract-review-2026-10-08.md`。

**状态：根因及现有接口已离线核实；最低领域要求已明确；V2 方案尚未实现，语义证据准入机制尚未验证。没有新生产执行边界，也没有真实验收通过。**

本轮按用户的停止条件停在设计：当前输入没有可信的主体/属性角色绑定，不能从词法出现、表格位置或 provider 自述可靠证明比较关系。把这样的角色猜测改成新 validator，或只禁止一行表格，都不能满足通用语义要求。全面禁用比较操作又不能满足合法多主体计划通过的要求。不能将这两个捷径作为最小修复交付。

本报告记录后续实现必须满足的合同和验证门槛。下文所有新类型、规则名、V2 格式及拒绝结果均是设计，不是现有 API。

## A. 原领域模型的问题与历史用法

已审查当前 dirty 工作区中的以下链路，并对比初始 Change Planning 提交 `33096a2`：

| 边界 | 当前契约与缺口 |
|---|---|
| `core/change_plan.py` 的 `ComparisonTableSpecification` / `ComparisonTableSpec` | 仅有 `column_headers`、`row_dimensions`。前者是列标签，后者是行标签，没有轴角色或主体身份约定。列 2–5、行 1–6、标签最多 80 字符；最终模型检查长度和唯一性。 |
| `_validate_table` / `validate_and_finalize_specification` | 检查形状、禁止语法、absence claims，以及每个标签在本 operation 引用 P/S 中连续出现；不验证主体、属性、关系或可填充事实。直接比较和新资源内嵌 brief 共用这一缺口。 |
| `workflows/change_plan.py` / DeepSeek adapter | provider 自由选择两个轴；parser 只接受指定字段，Python 原样物化。当前候选/availability 机制没有比较事实目录；`content_point_candidates` 的 `subject` 是内容主题片段，不是比较主体实体。 |
| `core/content_draft.py` / `workflows/content_draft.py` | Draft 输入校验检查报告、引用、范围和 audit provenance，不重新验证比较语义。`table_coordinate_catalog` 按行优先生成 `C#_CELL_###`。provider 只能填写坐标、text 和 P/S 引用。 |
| `_materialize_table_cells` / `_finalize_table` | 按固定 schema 物化标签并检查行列覆盖；现有稀疏覆盖不是完整笛卡尔积。数字在引用 P 中出现仍不证明该值属于该坐标。无引用的保守文字存在可通过路径。 |
| `CREATE_NEW_RESOURCE` Draft 分支 | `NewResourceSectionSpecification.blocks` 仅接纳段落/列表，finalizer 没有落实内嵌比较 brief；不能视为端到端支持了嵌套表格。 |
| extraction / Site Content | `StructuredContentBlock` 仅有 kind、heading、rows、pairs、items、text。表格提取合并 `th` / `td` 的文本，不保存其角色、scope/headers、实体身份或 cell 关系；邻接关系不足以证明语义。 |

历史测试从 `33096a2` 起把列 `material selection` / `port size`、行 `application` / `maintenance considerations` 当作合法 brief。当前坐标/数字测试还使用 `pump performance` 作为单行标签。这些是**旧契约允许的用法**，不是经过验证的多主体比较证据。本次检索到的相关轴测试没有提供可信主体目录和逐格关系事实；不能据此将 V1 的某轴无声重解释成主体轴。历史可读性必须保留，这些测试的结构、scope、预算、grounding 断言也仍有价值。

历史 C2 把同一参数清单的属性分配到两个轴，不存在定义清晰的比较主体。这里不复制参数值或正文，也不尝试生成替代成品。

只读离线复现的**当前代码结果**：

| 检查 | 观察结果 |
|---|---|
| 历史 C2 `_validate_table` | `None`，没有拒绝 |
| 从历史 C2 重建 specification，经完整 `validate_and_finalize_specification` | operation 非空，error 为 `None` |
| 完整历史 `ContentDraftInput` 的稳定校验 | `None`，没有拒绝 |
| C2 Draft prompt / coordinates | prompt 可构造，生成 5 个固定坐标 |
| 全合成多主体标签组合与属性交叉标签组合，标签均出现在相同 evidence 中 | 两者都被现有 `_validate_table` 接纳；这仅证明词法行为，不能证明前者事实充分 |

## B. 新比较表格最低语义契约（设计）

### 分类与操作承载

| 内容 | 领域判断 | 现有操作的适用性 |
|---|---|---|
| 至少两个不同主体，对同一组属性有可比且可追溯的事实 | 多主体比较表 | `ADD_COMPARISON_TABLE` 的目标语义。新资源比较必须遵循同一规则。 |
| 一个已识别主体的属性/值清单 | 单主体技术参数表 | 不属于比较操作。已有 `EXPAND_SECTION`、技术文档 `ADD_SECTION` / `CREATE_NEW_RESOURCE` 能承载证据支持的文字说明；当前 Draft 不能承诺输出专用技术参数表。 |
| 仅有标签、没有主体身份；没有逐格事实；条件不可比；不明关系的属性交叉 | 不适合生成比较表 | 省略比较操作。只有原 R action 和证据另行授权时，才能在新的 Plan 中选择已有说明操作。 |

本轮不新增 operation type。若以后产品要求独立技术参数表，应先设计该能力；不能以 `ADD_COMPARISON_TABLE` 名义塞入单主体表，也不能由 Draft 把已经批准的比较计划改成说明文字。

### 轴、身份和关系

建议 V2 固定 **row = subject、column = attribute**。这是新版本的明确约定，不是对 V1 的追溯解释。

1. 至少两个不同的、有来源绑定的主体身份（产品、配置、方案或其他明确实体）；不同显示标签不证明不同实体，多个页面不证明多个主体。别名必须归属于同一身份，不能靠改名凑数量。
2. 至少一个明确属性，所有主体使用相同属性定义。领域最低要求是一项属性；首次实现可保留当前 2–5 列预算，明确一属性比较暂不受支持，而不把它称为语义无效。行预算仍为最多 6，新增比较主体最少 2。
3. 每个 cell 表达且只表达 `value(subject_id, attribute_id, context_id)`。属性定义包括适用范围，context 定义可比条件。不同单位不自动等价，不做换算；不同测试条件不能只因名称相同合并。最低版本只接纳已确认可比的关系，不做自由关系分析。
4. 每个选中的主体 × 属性坐标有至少一个合法事实绑定。最低版本要求完整网格；缺少事实时拒绝整张比较 brief，不填入泛化占位符、不把事实缺失转成 absence claim。缺失数据表、条件化比较和 N/A 有独立领域需求，暂不接纳。
5. 每个事实绑定准确的 P/S、材料位置及原文值，且在 enclosing R 和 operation 范围内。第一方产品事实仍必须来自允许的 P；S 不能代替第一方 P。外部主体/一般方案事实仅能使用符合现有证据用途的 S，不能升级成自家产品承诺。
6. 事实语义证明与数字格式检查是两项独立检查。已有 numeric grammar 保持原样；本轮不以比较设计放宽裸数字、共享单位、范围或型号表达。

### 可信证据准入是实施前置条件

不能让 Planning provider 自由输出 `role=SUBJECT`、`approved=true`、自造实体 ID 或三元组，就把它们当作证明。换用所谓 evidence candidate 也无效：**候选来自同一组裸标签时，选择引用只证明标签存在。**

建议引入冻结的 `ComparisonEvidenceCatalog`，包含以下有界领域内容：

- `SubjectBinding`：稳定实体身份、准确显示名称及来源位置。
- `AttributeBinding`：属性身份、显示名称、值语义及适用 context。
- `ComparisonFactBinding`：subject、attribute、context、原文 value、P/S 及结构位置。
- `ComparisonCandidate`：确认的 subject/attribute 顺序、完整 fact 网格，以及对应材料快照身份。

目录必须在 Planning writer 之外形成并验证。可靠入口可以是保留显式语义关系的结构化来源，或明确人工审核的映射；两者都需验证原文位置、范围、身份一致性和材料版本。原网页也是不可信内容，显式结构仅提供归属证明，不证明现实世界真实性。若采用人工审核，其授权记录必须由可信运行边界提供并绑定目录快照，不能接受 provider 或网页内的批准字段。

**目前这两种准入入口都不存在。** 修改 extraction 保存更多表头元数据只能改善信息保留，不能自动确认某个 header 是主体、同页多个字段是不同实体，或条件可以比较。本报告不声称已经验证了通用自动实体/关系识别算法。

最小部署候选是先支持有明确审核记录的目录，其他材料 fail-closed；但它引入 Planning 前的人工材料确认及 artifact 绑定，需要作为产品接口变更单独落实。本轮不擅自添加该流程。自动识别可作为后续独立能力，不能成为首次实施的隐含假设。

### 拒绝结果（建议）

Planning / Draft 复用核心验证器及结构化 `ComparisonSemanticViolation`，返回公共 allowlisted category `COMPARISON_SEMANTICS_INVALID`；安全诊断仅包含 stage、R/C 引用、field_path、schema_version、rule_id、行列索引、合规 P/S 引用和数量，不包含值、原文、provider 输出或普通事实哈希。

确定的规则优先级：

1. `LEGACY_COMPARISON_NOT_EXECUTABLE`：无 V2 语义能力，允许读取但禁止新 Draft 执行。
2. `COMPARISON_EVIDENCE_UNVERIFIED`：目录无有效准入记录或不匹配材料快照。
3. `COMPARISON_REFERENCE_INVALID`：未知/越权的 candidate、实体、属性、事实引用。
4. `COMPARISON_SUBJECTS_INSUFFICIENT`：少于两个不同规范实体。
5. `COMPARISON_AXIS_ROLE_INVALID`：轴没有按确认的主体/属性目录物化。
6. `COMPARISON_CONTEXT_INCOMPATIBLE`：同列事实没有明确可比 context。
7. `COMPARISON_FACT_COVERAGE_INCOMPLETE` / `COMPARISON_FACT_BINDING_MISMATCH`：缺失坐标事实，或原文、位置、主体/属性关联不匹配。
8. `NESTED_COMPARISON_NOT_SUPPORTED`：首次最小实现未支持新资源表格时，明确拒绝该能力。

既有结构、scope、预算、安全校验仍先执行相应检查。上述顺序是语义层内部的首错规则。缺失可信证据是输入/前置条件问题，不通过 provider retry 修复；Draft 不能修复上游 schema。多个字段失效时诊断不能推测深层原因。

历史 C2 的期望执行拒绝是 `LEGACY_COMPARISON_NOT_EXECUTABLE`，而不是声称自动识别出了“重量”。把原 C2 标签包成 V2 但没有准入目录，应得到 `COMPARISON_EVIDENCE_UNVERIFIED`。不得人工为原错误轴批准伪造关系来使它通过。

## C. Planning 到 Draft 的最小接口升级范围（尚未实施）

1. Core 先接收已验证目录；Planning availability 只有在 R 内至少一个完整比较候选存在时才允许比较能力。无候选时从可用操作中移除比较，不自动增添技术文档 action。
2. writer 仅选择 R 范围内 `comparison_ref`；Python 物化冻结的主体行、属性列和事实绑定。parser 拒绝自由标签和额外事实声明。provider prompt 仅做必要的字段协议同步，不用 Prompt 扩写承担语义推理。
3. `validate_and_finalize_specification` 验证引用、范围、准入、角色、身份、context 和完整 facts；`canonical_change_operation_identity` 纳入语义事实/快照身份，避免同标签不同关系被错误去重。
4. Draft 在 provider 调用之前校验计划语义；公开 prompt builder、coordinate builder 和直接 finalizer 也不能绕过检查。历史 invalid Plan 应返回结构化 INVALID_INPUT，不修复、删除或重排已批准内容。
5. V2 cell_ref 仍可使用现有有界行优先格式，但必须绑定 Plan artifact 与已批准 schema 版本。它只是该计划中的坐标键，不是全局事实身份；不同 Plan 的 `C2_CELL_001` 不可互换。
6. 最小 Draft 表格只能使用 cell 的已批准 fact 原文值及准确出处；可由 Python 物化，或要求 provider 文本与绑定值精确匹配。不接受相同数字来自错误属性，不接受删除 refs、泛化文字或 placeholder。不在首次版本支持自由综合型 cell 文案。数字 grammar 的独立检查继续生效，因此语义通过不保证数字表达通过。
7. 新资源内嵌表格首次先明确不可执行：Planning 移除仅由比较 action 授权的新资源选项并拒绝其 nested brief；其他新资源带表也拒绝；Draft 再拒绝该入口。不能通过将顶层比较操作改名为新资源绕过。要支持它，需扩展 section block/parser/finalizer 并定义表格放置契约，不属于直接比较防线的最小实现。

上述变更至少涉及 `core/change_plan.py`、`core/content_draft.py`、两个 workflow、Planning adapter 字段协议、artifact codecs 与写入版本选择；此外还需要真实可用的目录准入接口。当前只改 `_validate_table` 的参数或数目规则不足以完成这些边界。

## D. 历史 artifact 和 SQLite 兼容性策略（设计）

当前 artifact payload 都为 V1；SQLite `user_version=4` 是数据库结构版本，两者独立。`storage/serialization.py` 的根类型 allowlist 目前只接纳 payload V1；其严格 dataclass codec 对未知/缺失字段 fail-closed，少数历史 provenance 字段有显式默认兼容。

建议 `CHANGE_PLAN` 与包含新事实绑定的 `CONTENT_DRAFT` 各自升级 payload V2，使用版本感知的严格 codec 和明确的 Legacy/V2 映射：

- V1 保持原字段、原标签、原值、原引用及原阅读模型。没有语义记录时标记为 legacy，不补造主体、属性、facts 或批准状态。
- V1 无比较操作的计划，仍可按现有稳定安全边界执行；V1 任何比较 brief（包括嵌套）可读、可审查，但不进入新的 Draft 路径。读取成功和执行合格是不同接口。
- V2 的新比较计划必须携带目录快照、角色及 facts 的完整绑定；缺失语义字段不能由 dataclass 默认值补齐。持久化后篡改绑定仍需在新执行前重新验证。
- V1 Draft 的旧 table cells 仍是 row_dimension、column、text、page_refs、source_refs；不添加不存在的 cell_ref。读取旧成品不证明新语义验收成功。
- 新规划、新准入记录和新批准产生 append-only artifacts，保留旧 C2。不能升级原 payload 来冒充旧计划已获新批准；新的审核必须绑定新的计划身份。Draft 不得重写已批准 Plan。
- `artifacts.payload_version` 已能容纳 V2；仅改变 JSON payload 不需要 SQLite DDL 迁移。若准入记录新增存储设施，则必须单独设计，不能隐含在这次 codec 升级中。
- end-to-end writer 当前使用统一 `_PAYLOAD_VERSION`；web application / live application 中存在只接纳 V1 的分支。必须同步版本选择和读取兼容，或明确 fail-closed 为暂不支持 V2。不能只增加 codec 后宣称所有消费者兼容；本轮不修改完整 CLI / LiveComposition。

真实历史库核查：以 SQLite `mode=ro` 读取 run `86d25a34-31de-4808-91c3-b0ed89461960` 的五个 artifact，全部成功 decode；库的 schema version 为 4，全部 payload version 为 1。该 run 没有 Content Draft artifact，所以没有可声称通过的真实旧 Draft 成品读取验收。Site Content、Content Opportunity、Change Plan 的 decode/encode/decode 等值检查通过；旧 Draft 比较 cells 的往返兼容另用全合成成功报告验证。未调用会迁移历史库的写入 store，schema version 保持 4。

## E. 本轮实际修改及验证

唯一新增文件：本报告。没有修改运行代码、测试、Prompt、schema、批准记录或历史库；没有实现 RED/GREEN，也没有新增声称修复成功的测试。

实际运行：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_change_plan_core tests.test_change_plan_workflow tests.test_change_plan_material_availability tests.test_content_draft_core tests.test_content_draft_workflow tests.test_content_draft_table_coordinates tests.test_history_serialization tests.test_history_migration_to_v3 tests.test_sqlite_history_store -q
```

结果：**272 tests，15.187 秒，OK，exit=0**。这验证现有契约，不是 V2 或语义修复测试。没有执行 full discover；纯设计文件变更没有运行完整回归的必要，不能引用先前 full suite 数量作为本轮结果。

另外运行两个内联 Python 离线 probe，均 exit=0：历史只读 decode、V1 roundtrip、完整 C2 Planning finalizer、Draft 输入和坐标核查；全合成旧 Draft table cell roundtrip。没有打印真实参数值、正文或 provider 原文。一次文件检索将 PowerShell 通配路径直接交给 rg，产生路径错误；已改用 `rg ... docs -g 'draft-numeric-*.md'` 重查，exit=0。没有业务测试失败。

`git diff --check` exit=0，没有 whitespace error；Git 输出既有工作区的 LF/CRLF 提示。新报告是 untracked 文件，另以 `git diff --no-index --check -- NUL docs/comparison-table-semantic-contract-design-2026-10-08.md` 检查，没有 whitespace 输出（exit=1 表示文件与空文件不同）。所有既有 dirty 文件保留；没有 commit、push、merge、真实 API、真实 Draft-only、WordPress、完整真实 CLI 或 LiveComposition 调用。

## F. 后续必须实现并先 RED 的验收矩阵

先落实并验证目录准入，之后才能开始生产语义规则实现。每一项新增确定性规则应先写失败测试、观察 RED，再做最小实现和 GREEN。旧行为测试需分为 V1 读取/结构测试与 V2 执行测试，不能删除有效 scope、grounding 或预算断言。

| 新规则测试 | 期望 | 本轮状态 |
|---|---|---|
| 历史 C2 V1 可读，Draft workflow 在任何 writer 调用之前拒绝；同样验证直接 builder/finalizer | legacy 拒绝，writer calls=0 | 当前读取已验证，拒绝未实现；当前实测仍通过 |
| 全合成两个不同产品、两个属性、完整四格的审核目录；再用另一行业的方案比较目录 | Planning 物化合法 V2，Draft facts 接口通过 | 未实现，不能把标签 probe 算作通过 |
| 两个合理名称但没有准入目录；provider 自报 role/approval；属性 × 属性组合 | 拒绝，不通过名字推断角色 | 未实现 |
| 同一实体的两个别名、一主体参数表 | 不满足比较主体数量；不得自动重写操作 | 未实现 |
| 正确数值但错误主体/属性、错误位置/context、同值来自不同页面 | 拒绝绑定错配 | 未实现 |
| 删除 refs、伪造主体/属性/fact、未授权 R/P/S、跨计划 cell_ref | 拒绝，无引用降级和占位符绕过 | 未实现 |
| 一个坐标缺事实、稀疏覆盖、额外坐标、重排批准轴 | 拒绝；完整合法网格通过 | 未实现 |
| 修改已冻结材料/准入记录、V2 字段缺失、未知新版本 | fail-closed；不能默认填充或无声降级 | 未实现 |
| V1 Plan / Draft / 旧 SQLite 读取 | 原样可读，读不授权执行 | V1/SQLite 相关 272 项及 probe 已验证；混合 V1/V2 未实现 |
| nested 新资源比较从 Planning 与 Draft 进入 | 明确 unsupported，不能静默丢表或绕过 | 缺口已核实；拒绝未实现 |

实现后需要相关 core、workflow、adapter、serialization、version consumer 测试及必要完整回归，再运行 `git diff --check`。合成合法目录只能证明规则正确性；至少一个真实、合理、重新规划并人工审查的多主体样本才能作为之后具体授权的真实验收。不能重新使用旧 C2 作为成功样本。

## G. 是否进入数字 grammar 修订

可以开展独立数字 grammar **设计**，但不应先放宽生产 numeric validator 或开展真实 Draft-only。当前语义准入、逐格绑定和执行拒绝仍未落地；在此之前扩大数字接受范围会扩大错误属性/主体事实的可通过范围。下一步开发优先解决比较证据准入和执行边界，再在正确绑定事实下做 grammar 的离线 RED/GREEN。

## H. 完整 CLI 6/6 readiness

**NO-GO。** 本轮没有运行完整真实 CLI 6/6，也没有新增真实通过项。历史 C2 无效，新执行防线、可信目录准入、嵌套入口拒绝及 V2 消费者兼容尚未实现，数字 grammar 也未修订；不能凭现有 272 项测试宣布商业 MVP 完整链路就绪。

最终状态应严格表述为：**根因/最低语义边界已明确；兼容性和升级范围有方案；可靠证据准入尚需实现与验证；代码修复未实施；真实验收未通过。**
