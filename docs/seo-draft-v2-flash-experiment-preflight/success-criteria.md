# 成功标准

比较方式：**Controlled comparison**，不是 strict A/B 或 causal proof。固定 frozen-v1 Flash 的参数、主题和客户证据，变化仅为 Selection Contract、Writer context、Explanation requirement。只做离线预检；真实 v2 输出尚不存在。

## Technical（硬门槛）

- Parser PASS：外层严格 JSON、无重复 key、无额外字段；native candidate 通过原 Parser；解释标注满足明确字段/类型。超长、畸形、深层或非法 Unicode 失败关闭。
- Validator PASS：原生所有规则及 V2 检查均通过。不得因实验需要放宽数字、引用、唯一正文、字段、预算或证据规则。
- 正文和原始 envelope 分别保存；candidate hash 绑定规范化 UTF-8 原生 candidate JSON。解释中的 hash 由本地生成，不信任模型自行计算。

## Contract（硬门槛）

- claims <=48，blocks <=24；同时满足原生 block/item/text 限制和每章显式预算。
- selected facts only：客户事实来自选定章节的 selected_facts。禁止完整 fact bank、未选事实、内部选择理由进入请求；禁止输出补充事实。
- section routing PASS：章节顺序/heading/question 固定；selected refs 使用、required_direct_facts、source equality、requirement coverage 及预算 reservation 均满足既有合约。
- explanation contract PASS：每个解释恰好一个标注，claim_id / section_id / 完整前提 refs / selection / Plan / snapshot / candidate / 正文 hash 一致；三个片段拼为读者实际正文。20/12/20 最少词、60–160 总词和 1,200 字符是结构代理。
- 全局直接事实 <=30、解释 >=12、CTA=1 为诊断偏好，不擅自变为新增拒绝规则；逐章明确 reservation 保持硬门槛。
- 技术与合约通过后状态最多为 PENDING_SEMANTIC_REVIEW；semantic_approved、production_authorized 均为 False。

## Quality（人工评审，不由 Validator 代判）

将 frozen-v1 与待生成 v2 以相同标准逐章评审，保存引用正文与理由。建议隐藏版本标签后评审，记录评审者、时间与偏差；历史单样本不能证明因果。

| 检查问题 | 人工观察 | 记录方式 |
|---|---|---|
| 是否减少事实堆积？ | 是否围绕 buyer question 组织必要事实，减少逐条参数罗列；保留支持决策所需前提 | 引用堆积段落/改善段落，按章记录 better / same / worse 与原因 |
| 是否增加采购分析？ | 是否说明某个事实为什么改变候选、排除项、可接受风险、测试设计或合同边界 | 每章摘录一个完整因果/决策解释，检查事实、假设与行动是否连通 |
| 是否仍只是资料改写？ | 是否仅同义改写 quote、重复“this helps buyers / this is important”，或每章套同一空泛模板 | 标记缺少具体 why 的解释；说明缺少哪个机制、适用前提或可检验步骤 |
| CTA 是否具体？ | 是否请求图纸版本、材料状态、夹具布局、目标节拍、验收重点及配置/交付输入，说明核验下一步 | 摘录 CTA，指出请求资料与前文未决问题是否对应，不能只写 contact us |

每章必须能找到 Evidence、Interpretation、Boundary、Verification 四部分，且边界说明何时不能外推，验证说明谁提供什么记录或约定什么试验来解决哪个不确定性。人工可判定某章合约通过但解释浅薄。

**Validator PASS 不等于商业成功。** 本轮不评定真实 v2 质量；合成证据、结构代理和一次受控比较也不能证明客户转化、排名、询盘或工程适用性。只有具备具体正文证据的人工质量评审才可作后续内容决策。
