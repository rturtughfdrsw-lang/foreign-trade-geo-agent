# Evidence Sufficiency Gate：项目所有者逐项审核包 v2

日期：2026-10-08（Asia/Shanghai）。包 ID：`ESG-OWNER-REVIEW-20261008-v2`。任务：`T-P3-EQUIPMENT-BRIEF-CANDIDATE-v2`。

**材料可审核；全部签核项 NOT_REVIEWED；合法匹配 Plan 尚未生成；Gate 未实现；没有 GREEN。** “正式审核包”指可保全、逐项确认的材料，不代表已通过审核的生产输入。本轮没有 Draft、收费 API、抓站、WordPress 或 commit/push。

本轮用户消息已要求受控演示页归因范围，并声明自己为项目所有者。这是本次整理的真实指令和权限背景，已用于设计候选；它不是下列逐项审核结果，也不认证工程事实。本包不虚构姓名、资质、批准时间或有效期。

## 四项阻塞推进结果

前报告列出五个缺口；本包将“权限/使用”和“真实性范围”合并为一组，保留全部问题。

| 组 | 已完成的准备工作 | 剩余决定或实现 |
|---|---|---|
| B1 来源用途、权限与真实性 | 冻结原文/来源版本/虚构声明；只提“演示页所述关系”，所有者可审核此归因任务 | 所有者确认有权使用的范围、审核权限记录及每项归因支持；工程事实扩展另需专业资料/审核者 |
| B2 匹配 Opportunity/Plan | 新建无 comparison 的 typed specification 候选；真实 validator 返回 `SOURCE_REFERENCE_REQUIRED`；未 finalize 失败对象 | 所有者决定条件 P-only 方向；后续兼容实现/availability/原校验通过，合法报告产生后重新绑定签核 |
| B3 任务深度与增量 | O1–O6 全保留，明确归因/虚构声明/禁止扩展义务；建议 EXPAND 既有 H1 | 所有者确认展示价值/深度/placement，或因重复拒绝；需新增技术知识则补专业来源 |
| B4 同输入消费、接入与保全 | 给出复用 reader、DraftInput、DraftWorkflow、append-only 新 run 的方案；材料进入非 ignored 文档目录 | 技术实现可信加载、冻结绑定检查、执行保全；所有者指定真实记录/时效策略；本轮未实现 resume/Gate |

没有“为凑正例已合法生成”的 Plan，也没有把 S1–S4 当六项支持。可确认方向不等于可进入生成。

## 任务与匹配候选

英文问题：

> According to the NovaCNC demonstration solutions page, what six groups of inputs form an equipment brief, and what decision or plan does each group inform?

完整回答六组**输入集合及其原文所述用途**，逐项归因于演示 solutions 页，并声明 NovaCNC 是虚构品牌。允许忠实转述/整理，不要求字数、claim 数、数字或来源数。EXPLAIN 在此仅表示解释原文输入→用途关系，不允许增加因果机制、型号选择方法、阈值、技术保证、统计、排名或 SEO 效果。

这是一项独立受限任务，不能代替原统计指南或薄 chemical compatibility 指南。若真正需要完整技术选型指导，本材料应判深度不足，不得将六句列举签为完整指南。

| 字段 | 本包候选 |
|---|---|
| Opportunity | `EXPAND_OBSERVED_CONTENT / EXPAND_PAGE_SECTION`；priority=`LOW` 为待确认提议 |
| Topic | P3 已观察 H1：`Translate a production need into an equipment brief` |
| refs | page_refs=`[P3]`；source_refs=`[]`；audit_refs=`[]`；无装饰引用 |
| Plan | 仅一个 `EXPAND_SECTION`；既有 H1 的 `EXACT_OBSERVED_HEADING` locator；无新 section/resource/comparison |
| ContentPoint | 一个 `EXPLAIN / Manufacturing Solutions \| NovaCNC Machinery`，origin=`P3`；现有候选可见的页标题，不代表完整任务定义 |
| 义务映射 | 候选 `operations[0].content_points[0]` → O1–O6；六项义务不是六个 ContentPoint，不突破最多五 points 的限制 |
| R/C 身份 | specification 中 R1 仅未来局部槽位，当前无正式 R1/C1 artifact，不得与历史 R1/C1 混用 |
| 用途/价值 | 隔离离线审核及未来 Gate 验收；整理现有六句为归因 brief，已有页面并不缺这些知识。所有者可判无增量并拒绝 |
| 站点动作 | EXPAND 是内容目标候选，不授权更新现有 WordPress 内容；create-only/draft-only 边界不变 |

[完整候选](review-packages/evidence-sufficiency-2026-10-08-v2/planning-candidate.json)和[实际 validation 结果](review-packages/evidence-sufficiency-2026-10-08-v2/planning-validation.json)已保存。现有 pure Opportunity validator 返回 `SOURCE_REFERENCE_REQUIRED`；因合法匹配 Opportunity 前置失败，未调用 Opportunity/Plan finalizer，不是遗漏了已通过 Plan 的结果。

旧 ADD_SECTION 提案还有两个问题：拟 heading 与 P3 H1 相同会触发重复标题 locator 校验；新 heading 候选/grounding 当前来自 S。改提 EXPAND 既有 heading，消除这两个提案问题，不声称已消除 P-only 阻塞。

## 六项原文与支持签核

来源 run `8cf30f2d-6f5f-4698-951c-30b427853a94`；SITE_CONTENT artifact `f1e2e071-68e8-44c8-919a-92ab03a4a10b`；payload version `1`。保存的 P3 URL 为 `https://geo-test-site.pages.dev/solutions/`，本轮未访问。

共同原字段：`pages[2].structured_content[0].text`。下标是直接 UTF-8 解码后原字段的 Unicode 字符零基半开区间 `[start,end)`，不是 byte、UTF-16 或规范化后下标。P3 body_text 已截断，structured_content 未截断，六句在该字段完整存在。请一并阅读完整页面上下文，不能仅凭摘句签核。

| 项 | 输入→原文用途 | 原字段 span | 人工状态 |
|---|---|---|---|
| O1 | 材料、尺寸、重量、几何、图纸特征、夹紧表面 → 物理工作包络 | `[172,297)` | NOT_REVIEWED |
| O2 | 铣、车、钻、攻丝、镗、轮廓切割要求 → 相关机器类别 | `[298,412)` | NOT_REVIEWED |
| O3 | 公差、表面、检验、过程稳定性 → 机器与刀具决策 | `[413,530)` | NOT_REVIEWED |
| O4 | 批量、组合、工时、换型、目标节拍 → 产能优先事项 | `[531,642)` | NOT_REVIEWED |
| O5 | 电源、空气、抽排、地面承载、通行、温度、物料搬运 → 安装规划 | `[643,761)` | NOT_REVIEWED |
| O6 | 目的地、运输条款、包装限制、文档、调试预期 → 交付计划 | `[762,882)` | NOT_REVIEWED |

逐字原句，仅核对演示页陈述，不认证技术正确性：

1. O1: “Material, overall dimensions, weight, geometry, drawing features, and clamping surfaces establish the physical work envelope.”
2. O2: “Milling, turning, drilling, tapping, boring, or profile cutting requirements narrow the relevant machine category.”
3. O3: “Drawing tolerances, surface finish, inspection method, and process stability influence machine and tooling decisions.”
4. O4: “Batch size, product mix, working hours, setup frequency, and target cycle time help define capacity priorities.”
5. O5: “Power supply, air, extraction, floor loading, access, temperature, and material handling affect installation planning.”
6. O6: “Destination, shipment terms, packing constraints, documentation, and commissioning expectations shape the delivery plan.”

每 O 请实际判断：原文是否直接支持归因转述，输入集合/用途/条件有没有遗漏或增强，是否需新增义务。填 `SUPPORTED / PARTIAL / TOPIC_ONLY / UNSUPPORTED / NOT_REVIEWED` 和理由。span 命中不能自动派生 SUPPORTED；修改义务须新版本重审。

另需确认 `task.json.required_output_constraints` 四项：逐项归因、虚构声明、O1–O6 完整且不增加机制、不增加数字/适配/保证/统计。虚构声明是输出边界，来自独立源码声明，不伪装成原 Draft P/S：未来应作为可信 brief 的允许范围传给 writer 并检查；若要求成为普通事实 claim，须合法进入实际 bounded evidence，不能私塞到 P3。

## 来源贡献、版本与审核材料

| 材料 | 贡献 | 不能证明什么 |
|---|---|---|
| P3 | O1–O6 的直接归因来源候选 | 工程事实、型号适配、真实厂家承诺 |
| solutions.astro | 六句逐字出处交叉核对，保留 CRLF span | 历史部署 commit、工程作者资格 |
| DemoDisclosure.astro | `[163,276)` 虚构品牌/非经营制造商限制 | 六项关系的工程真实性；它并非原 packet P/S |
| config.ts / experiment-baseline.md | 受控源码背景、来源版本 | 技术支持、使用授权或质量通过 |
| S1/S2 | 原市场/统计搜索的未验证截断 provenance；六项贡献为零 | 指南支持；S2 中 Verified 文本不是认证 |
| S3 | 他方设备/展会/培训平台 context；六项贡献为零 | “Manufacturing Solutions” 词重合不支持此任务，不得为过 topic 校验挂引用 |
| S4 | 他方经营/社交描述；六项贡献为零 | NovaCNC 关系或经营事实 |
| Audit / Research / Opportunity / Plan | 原运行观察/来源清单/旧决策追溯 | crawl 健康、模型输出、机器 SUCCESS 不认证充分性 |

源码版本 `e20d12bc38fccb1258d5b0436b35e9a9f878568c` 沿用前包已记录值。本轮核验冻结快照与前包字节一致，没有重新审计源码工作树或公网部署。历史部署 commit、工程作者/资质仍为 null。

全部材料移入非 ignored 的 `docs/review-packages/evidence-sufficiency-2026-10-08-v2/`，不依赖 ignored DB 才能阅读：

- [task.json](review-packages/evidence-sufficiency-2026-10-08-v2/task.json)、[coverage.json](review-packages/evidence-sufficiency-2026-10-08-v2/coverage.json)：任务、六项问题/原句、P3 与源码 span、field/quote digest。
- [完整 SITE_CONTENT](review-packages/evidence-sufficiency-2026-10-08-v2/snapshots/site_content.json)、[solutions.astro](review-packages/evidence-sufficiency-2026-10-08-v2/snapshots/solutions.astro)、[虚构声明](review-packages/evidence-sufficiency-2026-10-08-v2/snapshots/DemoDisclosure.astro)。
- [source-provenance.json](review-packages/evidence-sufficiency-2026-10-08-v2/source-provenance.json)：五类原 artifact ID/version/raw/canonical digest、DB digest、源码版本/file digest；[旧 Opportunity](review-packages/evidence-sufficiency-2026-10-08-v2/snapshots/content_opportunity.json)、[旧 Plan](review-packages/evidence-sufficiency-2026-10-08-v2/snapshots/change_plan.json)保留统计错配/comparison，不被改写。
- [P-only 需求/兼容方案](review-packages/evidence-sufficiency-2026-10-08-v2/first-party-policy.md)、[同一冻结输入消费方案](review-packages/evidence-sufficiency-2026-10-08-v2/frozen-input-design.md)、[真实 B2B 独立场景](review-packages/evidence-sufficiency-2026-10-08-v2/commercial-evidence-scenario.md)：均待决、未实现。
- [binding.json](review-packages/evidence-sufficiency-2026-10-08-v2/binding.json)、[manifest.json](review-packages/evidence-sufficiency-2026-10-08-v2/manifest.json)、[审核空模板](review-packages/evidence-sufficiency-2026-10-08-v2/review-record.template.json)。

本包 canonical binding SHA-256：`d3a3164d6c846344a13d37fda1390e8635507989096c474616f5be4a760168f2`。UTF-8、JSON sort_keys、ensure_ascii=false、紧凑分隔符；文件 digest 使用原字节。绑定任务、义务、受阻 specifications、九快照、来源版本、政策和接入/商业场景设计，不把填写后的审核结果塞回输入 hash。主 brief 是冻结对象阅读入口，文件 digest 另列 manifest，避免自引用。

这是**受阻候选/设计的审核绑定**，不是尚不存在的正式 Plan digest。合法 Opportunity/Plan 或实际 writer 可见范围变化后，创建新包、重绑并针对执行对象签核，不能搬用本包批准。hash 不是签名或身份认证。

## 项目所有者逐项决策单

全部待真实确认；可以接受、拒绝或要求补证。O1–O6 的支持另逐项确认，不代填 reviewer/reason/时间。

| ID | 待确认事项 | 决定权限/依据 | 状态 |
|---|---|---|---|
| D01_SOURCE_USE | 允许确切快照用于受控演示归因、离线审核/未来隔离验收；确认有权授予此用途，说明是否允许对外展示 | 所有者在自身有权范围决定；不推定第三方许可，S1–S4 仅 provenance、不入正文 | NOT_REVIEWED |
| D02_TASK_AND_DEPTH | 接受英文题目、O1–O6、全部输出约束与排除范围，不验收为真实选型指南 | 所有者决定产品目标；归因转述可亲自对照，不自动认证技术 | NOT_REVIEWED |
| D03_VALUE_AND_PLACEMENT | 接受归因 brief 的演示展示价值、拟 EXPAND 既有 H1；或判重复取消/补证 | 所有者决定用途/价值；不声称因此新增知识或证实 SEO 收益 | NOT_REVIEWED |
| D04_CANDIDATE_AND_P_ONLY_DIRECTION | 接受当前受阻的无 comparison 候选及仅 EXPAND 的条件 P-only 方向，供后续设计 | 所有者决定产品边界；工程实现、原校验/availability/focused tests 另完成，不能签字绕过 | NOT_REVIEWED |
| D05_FROZEN_CONSUMPTION | 采用确切冻结 artifacts→同一 DraftInput；禁止重跑 Planning/选 latest 替换 | 所有者决定流程，技术人员实现可信加载/绑定/保全 | NOT_REVIEWED |
| D06_REVIEW_AUTHORITY | 指定自己或授权人审核归因支持/任务范围，并指定独立可信人类消息/记录位置；技术场景另指定适用专业审核者 | 当前人类声明提供所有者背景；真实确认来自人类通道。JSON 自填/网页 approved 不认证身份 | NOT_REVIEWED |
| D07_VALIDITY_AND_REVIEW_STORAGE | 指定真实审核保存位置、有效期策略/日期与重审规则，记录人/时间/真实消息定位 | 所有者确认；不预填有效天数。任务/义务/语言/Plan/材料/截断/用途/授权变更或到期均重新审查 | NOT_REVIEWED |
| D08_COMMERCIAL_SCENARIO | 接受真实 B2B 场景为独立验收，补专业证据后另冻结，不用演示正例代替 | 所有者决定验收目标，专业来源支持实际工程内容 | NOT_REVIEWED |

可按 `D01=接受/拒绝/需补充；理由…`、`O1=SUPPORTED/...；理由…` 分批答复，引用包 ID/绑定。未答项仍 NOT_REVIEWED；确认 task 不自动确认六项支持，确认用途不确认 Plan 可执行。只有真实人类回复才能转录为新的审核记录，空模板不改为“已批准”。改任务/义务须新版本再审。

归因 evidence verdict 仅在用途/权限、完整任务/义务、每 O 支持及有效性实际确认后才可能 sufficient。即使这些满足，正式 Plan/执行绑定缺失时仍不可执行；不因此宣布 Gate GREEN 或工程技术认证。待审与已确认不足分开记录。

## 专业资料与技术实现边界

必须有专业来源支持的扩展：真实型号适配、机床/刀具机制、工况/阈值、质量/产能保证、安装安全/合规、出口法规、兼容性、真实统计及厂家能力。所有者身份可确定目标/用途，不能使缺失事实获认证，详见独立商业场景。

仍需实现：可信且显式 P-only context；Planning P-origin topic/availability/finalizer/stable/report validation 的条件兼容；合法 Plan/重新冻结；真实审核 record 加载、preflight/诊断/append-only 保全；冻结输入执行入口；生成后逐论断/任务质量审核。本轮生产代码、正式 tests、Prompt、codec 均未修改。

原薄 chemical compatibility 包/原任务/真实 Draft 与 mock 区分沿用[前轮报告](evidence-sufficiency-positive-candidate-report-2026-10-08.md)。未重跑 RED，未复制成“可信已审不足”新标签，未用演示包覆盖它。前轮测试结果只保留为历史，不计本轮验证。

## 本轮实际验证

只运行新增隔离准备/完整性脚本及现有 pure validator 探针。没有为受阻候选构造 SUCCESS report、调用 finalizer/writer/Gate。最终 [verification.json](review-packages/evidence-sufficiency-2026-10-08-v2/verification.json)记录九快照字节继承、十三 spans、binding/manifest/空审核记录/文档链接；[preservation.json](review-packages/evidence-sufficiency-2026-10-08-v2/preservation.json)保留原工作树/DB/前包保全的实际结果，独立脚本只核对该记录完整性，不冒充每次都重新核验外部工作树。命令和范围见[verification-notes.md](review-packages/evidence-sufficiency-2026-10-08-v2/verification-notes.md)。正式 unittest、full discovery、既有 RED 本轮均未运行，避免重复。

交付后仍为：**所有者审核待完成；专业事实未认证；合法匹配 Plan 不存在；Gate 未实现；真实 Draft 未验收。** 没有真实确认不得 GREEN。未来收费 API、抓取和 WordPress 各自另需具体授权，本包不包含这些动作授权。
