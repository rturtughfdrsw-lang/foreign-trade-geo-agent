# NovaCNC P3 独立摘录任务：受阻准备材料 v1

本包 `ESG-P3-EXCERPT-PREPARATION-20261008-v1` 保存独立任务 `T-P3-SIX-RELATIONS-ATTRIBUTED-EXCERPT-v1`（版本 1）和最新限定用途决定。**没有合法新 Opportunity/Plan，不能签为可执行冻结候选。** 原 v2 EXPLAIN 任务、包、状态和 artifact 保持不变。

最新决定仅允许本项目受控演示中的独立纯摘录/摘要 P-only 离线测试。D01 保留原限定授权；D02 仅用途，D03 仅离线价值，D04 仅方向；D05–D07 未审；D08 排除真实技术认证、商业验收仍未审。全 D 项原整体状态不升级，范围详见 [owner-decision.json](owner-decision.json)。原始 ChatGPT 消息无法独立核验，未填写身份认证、签名、原确认时间或审核事件。

## 唯一工程阻塞

现有契约要求每条原文摘录不超过 120 字符、一个 scope 最多 5 条、最终 ContentPoints 与 scope 原句按序等值。本任务六句长度为 125、114、117、111、118、120，共 705 字符。O1 单句构造直接失败；六个短原文片段因数量失败；将 O1 拆成两段形成七条也失败。不能以自由缩写、删掉输入、仅用页标题、借无贡献 S 或多任务合并冒充本六项任务通过。

[planning-validation.json](planning-validation.json) 保存真实拒绝结果。没有合法 scope，因此本任务 Opportunity/Plan workflow、availability、locator、finalizer 与稳定重验均未到达；不能称“全部原生校验通过”。按本轮要求停止生成，不创建 SUCCESS report、artifact ID 或正式可执行冻结包。绑定只固定受阻准备材料，formal Opportunity/Plan digest 均为 null。

## 一次阅读的六项支持审核表

共同来源：`https://geo-test-site.pages.dev/solutions/`；原 SITE_CONTENT artifact `f1e2e071-68e8-44c8-919a-92ab03a4a10b`，payload v1，原 run `8cf30f2d-6f5f-4698-951c-30b427853a94`。本轮未访问该 URL。

精确字段 `pages[2].structured_content[0].text`，Unicode 字符零基半开区间。原字段 SHA-256 `66f6257f3031d5ad6ba23333f935a047cffceee9662b1c2a877256c8a559df67`。body 截断，所用 structured 字段未截断。引言原文：

> A useful machinery discussion begins with the work to be done. NovaCNC groups the main technical and delivery inputs so buyers can compare equipment on a consistent basis.

以下六句是相邻完整原句。后文转入 “A part may require more than one process, but its primary geometry usually provides the starting point.” 及 process matrix；该后文不属于六项任务，不得据此增加选型映射或 comparison 操作。完整页面、原源码及每项前后文见 [coverage.json](coverage.json) 与 [完整快照](snapshots/site_content.json)；源码用于定位与虚构声明，不作为新增 S 引用。

### O1 · Part definition · NOT_REVIEWED

要求：六项零件输入 → physical work envelope。P3 字段 span `[172,297)`；`solutions.astro` 原文件 span `[880,1005)`。

> Material, overall dimensions, weight, geometry, drawing features, and clamping surfaces establish the physical work envelope.

允许：完整原句逐字呈现并归因演示页；当前契约不允许自由转述。审核重点：保留 material、overall dimensions、weight、geometry、drawing features、clamping surfaces；不将 work envelope 偷换为夹具或选型结论。

### O2 · Process plan · NOT_REVIEWED

要求：六种备选工序要求 → relevant machine category。P3 字段 span `[298,412)`；`solutions.astro` 原文件 span `[1042,1156)`。

> Milling, turning, drilling, tapping, boring, or profile cutting requirements narrow the relevant machine category.

允许：完整原句逐字呈现并归因演示页；当前契约不允许自由转述。审核重点：保留 or 的备选关系；requirements narrow 不等于指定某一机型；不由下方 process matrix 增加类别映射。

### O3 · Quality needs · NOT_REVIEWED

要求：四项质量输入 → machine and tooling decisions。P3 字段 span `[413,530)`；`solutions.astro` 原文件 span `[1194,1311)`。

> Drawing tolerances, surface finish, inspection method, and process stability influence machine and tooling decisions.

允许：完整原句逐字呈现并归因演示页；当前契约不允许自由转述。审核重点：保留四个因素及 machine and tooling 两个对象；influence 不等于保证公差、表面或稳定性。

### O4 · Production pattern · NOT_REVIEWED

要求：五项生产输入 → capacity priorities。P3 字段 span `[531,642)`；`solutions.astro` 原文件 span `[1354,1465)`。

> Batch size, product mix, working hours, setup frequency, and target cycle time help define capacity priorities.

允许：完整原句逐字呈现并归因演示页；当前契约不允许自由转述。审核重点：保留五项及 help define 的限定；target cycle time 是输入，不能改成实际节拍、产能或达标承诺。

### O5 · Factory conditions · NOT_REVIEWED

要求：七项工厂输入 → installation planning。P3 字段 span `[643,761)`；`solutions.astro` 原文件 span `[1508,1626)`。

> Power supply, air, extraction, floor loading, access, temperature, and material handling affect installation planning.

允许：完整原句逐字呈现并归因演示页；当前契约不允许自由转述。审核重点：保留七项；air/extraction/access 的具体工程含义未展开；affect 不能扩写成安全标准或安装阈值。

### O6 · Export scope · NOT_REVIEWED

要求：五项出口输入 → delivery plan。P3 字段 span `[762,882)`；`solutions.astro` 原文件 span `[1663,1783)`。

> Destination, shipment terms, packing constraints, documentation, and commissioning expectations shape the delivery plan.

允许：完整原句逐字呈现并归因演示页；当前契约不允许自由转述。审核重点：保留五项；commissioning expectations 不是服务承诺；shape 不等于满足出口法规或运输保证。

六项分别判断输入集合、关联动词、用途和必要限定是否完整；不得因 span 命中自动填 SUPPORTED。六项均未审，没有 reviewer/reason/时间代填。若改变任务、义务、语言、Plan、材料、政策或实际 Draft 可见范围，旧支持审核不继承。

## 下一步及阶段边界

需要先解决明确的摘录容量缺口，再产生真实原生合法的 Opportunity/Plan 并建立新的执行对象冻结绑定。本轮未发现 validator 缺陷：当前拒绝符合已验证契约，所以不修改生产代码或正式测试。后续可独立批准有限容量契约扩展，或另批准减少义务的新任务；本包不擅自替换六项任务。

本材料可以预审原文关系与用途，**尚不能完成可执行 Plan 签核**。仅支持签核仍不能启动该正例的 Gate 最小实现：还需要合法 Plan/实际 Draft 输入重绑，以及 D02 完整范围、D05 同输入消费、D06 审核权限、D07 保存与时效的真实决定。D03 SEO/placement 和 D08 商业方案仍未批准，若最小实现依赖它们需另确认。

工程契约合法、人工证据支持、Gate 验收和真实商业文章质量是独立阶段。本轮：工程候选受阻；人工支持 NOT_REVIEWED；Gate 未实现未验收；没有商业文章质量结论。真实模型和 WordPress 动作仍需分别授权。

验证：230 项现有针对性 unittest 全通过（8.191 秒、exit 0），覆盖 P-only 合法原生流程、EXPLAIN 拒绝、无证据/伪引用/跨任务绑定、既有 P/S、availability/locator 与 comparison 禁用、历史 v2/artifact 兼容。该成绩不表示本六项任务成功。未运行完整套件。只读材料校验命令：`.\.venv\Scripts\python.exe docs/review-packages/evidence-sufficiency-2026-10-08-excerpt-v1/verify_materials.py`。
