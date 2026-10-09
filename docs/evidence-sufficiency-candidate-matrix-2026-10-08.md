# 任务级证据充分性候选矩阵（待授权审核）

日期：2026-10-08（Asia/Shanghai）。**候选材料已整理；可信人工审核未完成；没有可直接用于 GREEN 的充分正例。** 本文只记录真实保存文本及候选支持关系，所有 O1–O6 的人工 verdict 均为 `NOT_REVIEWED`。

## 候选任务与边界

任务 ID：`T-P3-EQUIPMENT-BRIEF-CANDIDATE-v1`。英文输出。提案问题：

> According to the NovaCNC demonstration solutions page, what six groups of inputs form an equipment brief, and what decision or plan does each group inform?

回答范围限定为下列六组输入及各自用途，逐项归因于受控演示页。不得扩成完整选机指南、技术适配保证、市场统计、供应商能力、数字参数、比较排名或 SEO 效果结论。这是**新的待审核离线任务提案**，不是历史 CLI 问题，也不是已批准的历史 C3。审核人若认为这种归因范围不满足需要，须拒绝该候选并补真实来源，不能把范围缩小包装成原任务通过。

主材料：run `8cf30f2d-6f5f-4698-951c-30b427853a94`，SITE_CONTENT artifact `f1e2e071-68e8-44c8-919a-92ab03a4a10b`，payload version `1`，P3 URL `https://geo-test-site.pages.dev/solutions/`。每行字段均为原 artifact 的 `pages[2].structured_content[0].text`。完整字段、完整页面、其他页面及截断标记保存在[冻结 SITE_CONTENT](../.data/evidence-sufficiency-candidate-20261008/snapshots/site_content.json)；不得只看摘录就签核。

## 覆盖矩阵及原文

下标是**原字段 UTF-8 解码后的 Unicode 字符**，零基、半开区间 `[start,end)`；不是 UTF-8 byte、UTF-16 code unit 或清理空白后的下标。源码 span 同样对原文件字节直接 UTF-8 解码，保留 CRLF。所有 quote 精确回切及 SHA-256 在离线核验中检查；这只证明位置和版本，不等于审核人已判定语义支持。

| 必答项 | 有限问题 | P3 字段 span | 受控源码 span | 候选答案关系 | 人工状态 |
|---|---|---|---|---|---|
| O1 | 零件定义需要哪些信息，用于确定什么？ | `[172,297)` | `solutions.astro [880,1005)` | 材料、尺寸、重量、几何、图纸特征、夹紧表面 → 物理工作包络 | NOT_REVIEWED |
| O2 | 需列出哪些加工工序，用于缩小什么？ | `[298,412)` | `[1042,1156)` | 铣/车/钻/攻丝/镗/轮廓切割要求 → 相关机器类别 | NOT_REVIEWED |
| O3 | 质量因素包括什么，影响哪些决策？ | `[413,530)` | `[1194,1311)` | 公差、表面、检验、过程稳定性 → 机器与刀具决策 | NOT_REVIEWED |
| O4 | 生产模式记录什么，用于确定什么？ | `[531,642)` | `[1354,1465)` | 批量、组合、工时、换型、目标节拍 → 产能优先事项 | NOT_REVIEWED |
| O5 | 工厂条件包括什么，影响什么规划？ | `[643,761)` | `[1508,1626)` | 电源、空气、抽排、地面承载、通行、温度、物料搬运 → 安装规划 | NOT_REVIEWED |
| O6 | 出口范围包括什么，塑造什么计划？ | `[762,882)` | `[1663,1783)` | 目的地、运输条款、包装限制、文档、调试预期 → 交付计划 | NOT_REVIEWED |

O1 原文：

> Material, overall dimensions, weight, geometry, drawing features, and clamping surfaces establish the physical work envelope.

O2 原文：

> Milling, turning, drilling, tapping, boring, or profile cutting requirements narrow the relevant machine category.

O3 原文：

> Drawing tolerances, surface finish, inspection method, and process stability influence machine and tooling decisions.

O4 原文：

> Batch size, product mix, working hours, setup frequency, and target cycle time help define capacity priorities.

O5 原文：

> Power supply, air, extraction, floor loading, access, temperature, and material handling affect installation planning.

O6 原文：

> Destination, shipment terms, packing constraints, documentation, and commissioning expectations shape the delivery plan.

候选支持意见仅为整理者对直接原文的对照：六句各包含输入与用途关系，比主题标题更具体。是否足够、是否需要解释更深的原因/操作步骤、是否能形成有价值的增量内容，由授权审核者裁定。不能从六处 span 推导“六项已人工支持”或“整项任务已通过”。

## 来源可信度、使用限制、来源贡献

| 来源 | 已核验事实 | 可以承担的角色 | 不能承担的角色 |
|---|---|---|---|
| 保存 P3 | 真实运行保存的提取文本；六句完整存在；与本地受控源码逐字相同 | 已观察演示页陈述的直接来源；用于这项归因任务的候选解释关系 | 权威工程事实、真实生产型号/供应商保证、人工签核 |
| 本地 `geo-test-site` 源码 | 工作树干净；HEAD `e20d12bc38fccb1258d5b0436b35e9a9f878568c`；四个文件的内容 hash 已冻结 | 内容出处交叉核对、虚构品牌与研究用途限制 | 证明历史部署采用这个 commit；证明作者具备工程资质；自动授予使用权 |
| `DemoDisclosure.astro` | `[163,276)`：“NovaCNC is a fictional brand. This website does not represent an operating manufacturer and cannot accept orders.” | 来源限制，禁止把演示信息当经营事实 | O1–O6 的技术正确性证据；不是旧 Draft input 中已有的 P/S |
| 历史 S2 | 搜索 context，`content_truncated=true`，题目为 `Cnc Machinery Industry Statistics 2026` | 保存原 Plan 的来源身份；本候选六项直接支持贡献为零 | 指南证据、已核验市场数据、第一方保证；其中 `Verified` 文本也不是可信认证 |
| SITE_AUDIT | robots/extraction/title 等 crawl 派生观察；source=`crawl-seo-audit` | 抓取健康和页面观察的辅助事实 | 材料技术真实性、任务充分性、批准或商业成稿质量 |
| Research / Opportunity / Plan 文案 | 保存的模型输出经机器契约验证 | 历史决策及定位证据 | 事实来源、任务覆盖证明或审核授权 |

P3 `body_text` 为 600 字符且 `content_truncated=true`；主 span 使用的 structured field 保留了六句，P3 `structured_content_truncated=false`。整个 packet `truncated=true`、`crawl_budget_exhausted=true`、stop=`page_limit`。因此可以核验这六处已保存的关系，不能断言网站没有其他内容、抓取覆盖全站，或截断外的说明已审核。selected run 未找到原始抓取 HTML；保存文本和源码对应是当前可复核范围。

本地全文买家文章 `geo-test-site/src/pages/blog/how-to-choose-a-cnc-machine.md` 已阅读用于寻找候选，但不在该 run 的五页 packet 中，不偷偷补入 P3 或计入 O1–O6 支持。Demo fixture 的 manifest 明写 `source_revision=unknown`，不作为真实来源身份的替代品。

## Plan 身份与错配

历史原任务为 `Improve organic search visibility, technical SEO quality, and content coverage for relevant search queries.`。原 Plan artifact `58b02400-284f-4d16-affd-c9c523241901`（version 1），原 C3 路径 `operations[2].content_points[0]` 是 EXPLAIN / `Manufacturing Solutions | NovaCNC Machinery`，P3/S2；但 proposed heading 是 `Cnc Machinery Industry Statistics 2026 Guide`，R2 同样是统计主题。**上述六句不能完成这个统计指南。** 完整 Plan 还包含已停用的 C2 ADD_COMPARISON_TABLE，不能作为当前新生成的合法整包输入。

本轮只创建 `OFFLINE-P3-PLAN-PROPOSAL-v1`：建议新任务采用 EXPLAIN、P3、标题 `Translate a production need into an equipment brief`，不继承统计目标、不恢复 comparison。它是自然语言离线提案，**没有新匹配 Opportunity/正式 Plan、没有 production validation、没有执行权限**。原 Plan/任务不变。当前内容操作至少需要一个 S ref，提案的直接支持全来自 P3；不得为凑契约把无贡献的 S2 宣称为支持。下一轮须先决定有效 context 的角色及匹配的合法 Plan，或停止该候选，不能在本轮改契约放宽。

已核验的 C1 DESCRIBE 和 P4 工艺描述可作为“非 EXPLAIN 不应全局误伤”的历史参照；它不自动变成解释任务正例。P4 参数是演示数据，也不用于本候选。

## 精确版本绑定

冻结材料根目录：`.data/evidence-sufficiency-candidate-20261008/`，是 ignored 离线材料，审核时需要连同文档保全；仅保留 docs 无法复查所有原文。

| 对象 | 绑定 |
|---|---|
| 数据库文件 SHA-256 | `30730ee633df8793e87a4fe05a932ed8e4576e0493391db0444e939f9127aa40` |
| SITE_CONTENT 原 payload UTF-8 SHA-256 | `3dc38a154f16ebfe89054405633aa31a716ff916e2723018adb8c7ed8e797887` |
| CHANGE_PLAN 原 payload UTF-8 SHA-256 | `cc7fa462e2cb953a56572f0a6a964f37d8bb7c1789de019582d40073c3c4074c` |
| P3 主字段 SHA-256 | `66f6257f3031d5ad6ba23333f935a047cffceee9662b1c2a877256c8a559df67` |
| 源码 `solutions.astro` 原字节 SHA-256 | `6ccc6e116dfd035ced52ada10df5f5b3cee3ccd74ada394414fba785c15398cc` |
| 候选 binding canonical SHA-256 | `ca257cf2375ed536b993fe314fc16e1a303895e0a28e5f269f6adc97c61b8539` |

[binding.json](../.data/evidence-sufficiency-candidate-20261008/binding.json) 全量绑定新任务、提案、P3 与历史 S2/截断状态、语言、原五类 artifact ID/version/payload digest、源码 commit 和四个文件 digest。canonical 投影是 UTF-8 JSON、`ensure_ascii=False`、`sort_keys=True`、`separators=(',',':')`，不做文本规范化。原 payload hash 则对 SQLite TEXT 直接 UTF-8 编码；二者不可混用。

[coverage.json](../.data/evidence-sufficiency-candidate-20261008/coverage.json) 还保存每处 field/quote digest；[manifest.json](../.data/evidence-sufficiency-candidate-20261008/manifest.json) 保存 run 时间、原 task、DB hash、全部快照 hash 和四种状态。run 开始时间为 2026-10-07 13:26:22.811271（Asia/Shanghai），失败状态不影响上游原文可被只读核验，也不等于 Draft 质量通过。

每次新任务、正式 Plan、证据、语言或义务变化都需要新绑定和重新审核。本文 digest 只绑定当前离线提案；将来不能复制到正式 Plan 冒称签核仍有效。签核时间/有效期目前均为空，不能由文件日期推导授权。
