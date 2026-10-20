# 资料充分的 CNC Buyer Guide 离线验收：BLOCKED

本轮建立了独立 SYNTHETIC / TEST ONLY NovaCNC 案例：7 份客户文件、43 条独立事实、8 项证据义务，使用新 run/task。完整资料在原生 Intake 和重新规划阶段可以保存、绑定、读取；当前原生 Plan 和 Draft 契约还不能把这些资料转化为符合完整采购指南要求的生成输入。因此 **不冻结付费请求、不进行 Flash 调用**。

这是一个可重跑的离线输入与契约实验。Research、Opportunity、初始 Planning 和诊断 Writer 使用显式固定替身；不能用它证明真实模型会自行规划或写出深度文章。重新规划使用现有 `RetainedIntakePlanWriter`，其能力是保留并验证既有 Plan，不是根据新资料形成新策略。没有手工替换原生 Finalizer 生成的 Plan。

## 资料与来源

| 文件 | 独立事实数 | 业务内容 |
|---|---:|---|
| [E1-retained-spindle-note.txt](customer-materials/E1-retained-spindle-note.txt) | 1 | 原冻结 NCX7 7200 rpm 空载连续主轴声明，原文、原定位和 SHA-256 完全复用 |
| [E2-base-configurations.txt](customer-materials/E2-base-configurations.txt) | 9 | NCX7 / NCX10 行程、台面、工件加夹具载荷、刀库和基础配置与选项边界 |
| [E3-spindle-and-measurements.txt](customer-materials/E3-spindle-and-measurements.txt) | 7 | 两型号电机铭牌功率定义、NCX10 空载速度、预热、试件测量结果与不确定度 |
| [E4-material-and-cutting-trials.txt](customer-materials/E4-material-and-cutting-trials.txt) | 8 | 铝件、刀具、冷却、切削配方、相同条件周期观察、NCX10 钢件试验和未测工况 |
| [E5-conditional-selection.txt](customer-materials/E5-conditional-selection.txt) | 5 | 大小夹具的条件化筛选、速度与匹配试验的比较限制、报价配置复核 |
| [E6-rfq-and-acceptance.txt](customer-materials/E6-rfq-and-acceptance.txt) | 6 | RFQ 输入、FAT 条件和拟议阈值、未定测量判定规则、责任与 SAT |
| [E7-service-and-register.txt](customer-materials/E7-service-and-register.txt) | 7 | 发货触发、运输排除、培训、初始响应、质保提案、备件和资料登记 |

[逐条事实矩阵](fact-matrix.md) 给出主体、属性、值、单位、条件、适用范围、限制、来源和版本；[facts.json](customer-materials/facts.json) 另外保存精确文本偏移和文件 SHA-256。[义务矩阵](evidence-matrix.md) 将八项采购问题映射到确切事实。[documents.json](customer-materials/documents.json) 是经过原生 UTF-8 文档适配器的 Supplement 输入。

原 E2–E5 是未确认资料，只复用一致的业务要素：NCX7、铝试件、fixture A、20 C、NOVA-MEASURE-A、+/-0.02 mm 和“验收方案仍需双方确认”。新版 B-TEST 增加的工具、方法、型号和服务条件都是**新的虚构资料**，不倒写旧版本，也不把旧“未确认”状态解释成历史批准。原 E5 的证书和服务未知不能推出任何真实认证；新案例也没有认证、真实客户案例或实验室权威背书。

资料登记有效区间为 2026-10-11 至 2027-01-09，仅对这个虚构离线案例有意义。日期检查由案例内显式 TEST reviewer 执行，原生 Intake 不自动理解工程文件有效期，也不验证真实工程适用性。审核本身另受原生五分钟新鲜度与当前快照绑定约束。

[一致性检查](customer-materials/consistency-checks.json) 实际核对了文本偏移/哈希、E1 原始身份、行程与台面、大小夹具与载荷的算术关系、试验速度与额定速度、实测偏差与拟议验收阈值的区别，以及所有事实都有义务引用。它不证明结构安全、测量校准、切削可行性、统计显著性或工程认证。

## 两组实际结果

| 验收项 | A：旧低资料对照 | B：新资料充分案例 |
|---|---|---|
| 完整 buyer guide 的证据义务 | 保留 F1–F5 | 五个 EXPLAIN 主题对应 F1–F8 |
| 客户资料 | 原 E1 | 7 文件、43 事实 |
| 原生 Intake 与审核 | BLOCKED；F2/F3/F4/F5 缺失 | 未审核仍 BLOCKED；显式模拟审核后 CANDIDATE_FOR_REVIEW |
| 任务/Plan/证据绑定 | 独立测试任务；不改历史 | task v1 / Plan v2 / evidence v2 / snapshot revision 3 |
| 生产 Draft | 仍拒绝 | 同一诊断输入仍 `INTAKE_EXECUTION_BLOCKED` |
| 完整资料及 Brief 到 Web 请求 | 不应发起 | `INPUT_BUDGET_EXCEEDED`，零请求 |
| 机械链路诊断 | 由既有原生 scope/Web 测试复验拒绝 | 仅缩减引文和 Brief 的显式诊断通过，不算完整指南正例 |

原生保留结果：[A 快照与缺口](A-low-evidence/scope-and-evidence-review.json)、[B 原生 run](B-rich-evidence/native-run.json)、[未审核状态](B-rich-evidence/03-unreviewed-candidate.json)、[TEST-only 审核](B-rich-evidence/04-test-only-review.json)、[追加式历史](B-rich-evidence/append-only-intake.json)。174 个历史冻结文件的前后哈希一致，见 `historical-hashes-before.json` / `historical-hashes-after.json`。

## 实际 Opportunity、Plan 与 Brief

实际 [Opportunity](B-rich-evidence/opportunity.json) 为 R1 / NEW_SUPPORTING_CONTENT / HIGH，主题 Model configuration and selection，CREATE_SUPPORTING_RESOURCE，引用 P1 与 S1–S4。P 是本地合成网页，仅含采购主题；S 是本地合成、未经验证的一般问题背景。工程参数只在 E 中。

实际 [Plan](B-rich-evidence/plan.json) 为 C1 / CREATE_NEW_RESOURCE，标题为：

> How to Choose a CNC Machining Center: A Practical Buyer's Guide

原生输出的章节只有：

1. Machine and application fit
2. Procurement and acceptance

五个实际 EXPLAIN 点分别为 Model configuration and selection、Spindle ratings and test conditions、Material and cutting cycle fit、Measured results and procurement acceptance、Delivery training and support。范围 reviewer 只确认目标、主题和八项义务一致，不能证明这两节已具有采购解释深度或下游资料完整性。

完整 [Writing Brief](B-rich-evidence/writing-brief.json) 是人工明确的写作要求，不是模型生成的规划成果。[可读 Plan 与 Brief](plan-and-writing-brief.md) 保留两者区别。Brief 要求按“事实 → 对采购者的意义 → 适用性判断 → 下一步行动”组织，下列是它期望覆盖的问题，**不是被手工替换进 Plan 的章节**：

| 采购问题 | 应用证据 | 可得结论与限制 | 下一步 |
|---|---|---|---|
| 工件加夹具是否能进入候选范围，型号差异是什么？ | E2 / E5 | 较大夹具超出 NCX7 所述台面宽和载荷；NCX10 仍仅是候选 | 提交夹具、路径、刀具伸出与动态载荷要求 |
| 主轴速度和电机功率究竟说明什么？ | E1 / E3 | 空载连续速度与电机铭牌不是切削功率或扭矩曲线 | 请求对应负载工况与扭矩资料 |
| 铝件和钢件试验能否代表实际应用？ | E3 / E4 | 只比较两型号同条件铝件；钢件仅有 NCX10 记录 | 确认材料、工具、冷却、几何和代表性切削循环 |
| 怎样从试件观察转到采购验收？ | E6 | 实测 +/-0.02 mm 与拟议 +/-0.025 mm 不是同一性质；判定规则未约定 | 商定图纸、测量、不确定度、上下料边界、责任和复测 |
| 报价中的交付、培训、支持覆盖什么？ | E7 | 发货不等于到货、初始响应不等于恢复、远程培训不等于现场调试 | 明确目的地、设施、日历、备件和签署条款 |
| 哪些仍无法回答？ | E4 / E5 / E7 的限制 | 扭矩曲线、长期热漂移、能力指数、刀具寿命、表面/孔位、合规、价格和落地成本仍未知 | 请求适用证据；不得补成能力承诺 |

## 实际阻断与最小修复边界

1. **章节生成固定。** `core/change_plan.py` 的 `deterministic_outline_headings_for()` 固定取候选前两项；CREATE_NEW_RESOURCE 不允许模型输出章节。补充 E 不会自动产生型号、工况、测试、限制的章节分配。固定替身选出五个主题不证明通用自动规划能力。
2. **多事实投影失败。** Intake 的 TEST reviewer 引用了 43 个唯一事实 span，但 `DraftCustomerSource` 每个 E 只能有一段最长 300 字符引文；bundle 限制 8 个独立 E ID。逐 span 建 Source 会重复 E ID并超过数量限制，整份文档作 quote 又超长；两条真实原生构造路径均失败，见 [downstream-loss.json](B-rich-evidence/downstream-loss.json)。
3. **写作只能摘录 E。** Draft 请求只发送 quote，不发送 Source.content 全文；Validator 要求 E claim 完整等于对应唯一 quote。7 条合法投影留下 36 条事实，不能用 E 引用生成新的采购解释；实测追加一句适用性问题也会被 `CUSTOMER_QUOTE_MISMATCH` 拒绝。预算另有 16 claims、8 blocks、3000 output tokens。仅堆字数不能解决。
4. **请求预算另有阻断。** 即使使用上述已丢失 36 条事实的投影，完整 Brief 请求仍为 **19,236 bytes > 16,000 bytes**，被现有单次传输边界拒绝，见 [full-brief-web-blocked.json](B-rich-evidence/full-brief-web-blocked.json)。输入 system 7,402 字符、user material 11,049 字符。不是模型上下文不足的实测结果。

这些限制在既有通用契约中，不是 NovaCNC 参数解析错误。复制 E 到 P/S、拼接无界大引文、手工换 Plan、压缩掉实质 Brief、把新解释当 EDITORIAL/CTA 都会制造假阳性。本轮没有修改生产 Gate、原生 Validator、P1、PostgreSQL 或生产业务代码。解除阻断需要明确的、仍有界的通用章节与多事实引用契约，以及解释性结论的证据规则；单独放宽长度或改一行截断不能满足验收。本轮没有对 NovaCNC 增加任何原生放行特例。

## 离线 Draft 与 Web

完整 Brief 的 Web 请求先被原生拒绝，确认无请求。随后单独配置明确标记的 **mechanics-only** 诊断：7 条引文、缩减 Brief，15,845 bytes；固定响应返回 10 个 claims，包括 7 个独立 E 原文、1 个 S 背景、过渡和 CTA。这只测试原生处理能力。

一条 MockTransport 请求实际经过原生 Parser → Validator → Finalizer → SQLite 写入及重新打开 → 原生 Markdown Review → Web TestClient HTTP 页面；Web 文章返回 200。重复提交没有第二次请求；移除 scope reviewer 后生成再次阻断；真实交付路由返回 409。E claims 没有 P/S 引用。未做真实浏览器视觉验收，也没有真实 DeepSeek、余额、WordPress 或其他外部 API 调用。

产物：[诊断输入](B-rich-evidence/diagnostic-web-native-input.json)、[固定 writer 响应](B-rich-evidence/scripted-writer-response.json)、[原生 Markdown](B-rich-evidence/diagnostic-article-review.md)、[逐 claim 引用](B-rich-evidence/claim-evidence-bindings.json)、[Web 保存结果](B-rich-evidence/web-result.json)、[Web HTML](B-rich-evidence/web/article.html)。原始 Mock 请求/响应、SQLite 和处理记录在 `B-rich-evidence/generation/` 下。本轮未生成 `web-experiment/` 或付费许可。

## 质量评价与后续 Flash 前置条件

沿用历史维度：事实准确性（包括范围/条件）、解释深度、采购价值、照搬程度、结构与 CTA。历史 Flash 文章为 170 词，已有指标显示 5 条 S1 原句合计 73 词、没有 CALL_TO_ACTION 类型；仅是历史参考。

本轮真实模型质量六项均未测。固定 writer 的 E 原文准确保留只能证明摘录和绑定，不能证明理解；36 条丢失事实和仅两节结构已足以否决完整指南输入质量。不能拿本轮固定响应与历史 Flash 打质量分或宣布提升。

下一次单次 `deepseek-flash` 实验必须先完成：

1. 有界的每文件多事实引用及完整请求投影，保持数字、型号、条件、来源与版本约束。
2. 原生规划产生采购决策结构并分配型号/工况/测试/限制，不能事后换 Plan；模型规划能力若仍用替身，必须继续注明未测。
3. 解决完整 Brief 与请求预算不匹配，保留解释空间；重新跑 A/B，A 继续阻断，B 完整输入离线 READY。
4. READY 后才冻结新任务、Plan、证据、完整 Brief、Prompt、单次请求及精确 SHA-256；记录实际输入长度、Token 估计/预算和当时价格依据。当前 BLOCKED，不给未就绪请求编造成本。
5. 保留历史 170 词文章，按相同六维评价真实新稿。资料、主题/Plan、Brief、背景及请求条件均有变化，这是整体能力对照，不是只改变一个变量的严格模型实验。
6. 获得针对该精确付费请求的**新的明确授权**；TEST 模拟审核不构成真实客户批准或生产权限。

## 复现与验证

从仓库根执行，输出目录必须不存在：

```powershell
.\.venv\Scripts\python.exe -m scripts.accept_rich_buyer_guide --output-dir .data/rich-buyer-new-run
.\.venv\Scripts\python.exe -m unittest tests.test_rich_buyer_guide tests.test_native_scope_paths tests.test_intake_native_planning tests.test_web_generation -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

本轮仅新增 `scripts/novacnc_buyer_fixture.py`、`scripts/accept_rich_buyer_guide.py`、`tests/test_rich_buyer_guide.py` 与本目录，不改动已有用户修改。独立新增测试 8/8 已通过；针对性组合和完整回归的最终结果见 [verification.json](verification.json)。资料契约中的 BLOCKED 是验收结果，不是假装通过的完整采购指南。

脚本迭代中修正过运行入口（使用 `-m scripts...`）、JSON 列表保存、300 字符 SEO goal 边界、Research 的 S 引用和交付探针表单字段。这些是本轮离线脚本错误；最终复现命令已成功。保留的多事实、原生章节和完整 Brief 阻断未被隐藏。

`artifact-sha256.json` 是已关闭离线运行产物的校验清单，**不是付费请求冻结或授权**；本说明和之后追加的测试日志使用独立 verification 记录。
