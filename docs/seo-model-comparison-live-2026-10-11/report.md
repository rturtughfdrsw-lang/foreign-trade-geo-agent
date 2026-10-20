# Flash / V4 Pro 单次真实文章对照

结论：**本轮真实 Pro POST 恰好 1 次，技术链路通过；V4 Pro 未明显优于历史 Flash，不建议据此升级 MVP 默认模型。两份文章均 NEEDS_REVISION，均没有可信人类签核。** 实验已结束，没有追加请求、改 Prompt 或修复生成。

本报告的内容评分是依据冻结 rubric 的非盲 AI 编辑评价；评价者知道样本身份，没有人类盲评，不是客户商业交付批准。原生校验、内容质量及人工签核分别报告。

## 授权与请求核对

用户以项目所有者身份在本 chat 明确授权这份请求，截止北京时间 **2026-10-11 14:30:00+08:00**。可信时钟读数为 14:03:53，进程 UTC 时钟约晚 1 秒。单次请求开始于 **14:04:05.595775**，完整响应收到于 **14:04:10.696250**，原生校验完成于 **14:04:10.709270**，均在截止前。

- 请求 SHA-256：`991361f0eb58bfeb7fd557374faca7aae0093fd19a8e215586ca4c37593d8abc`，11,413 bytes。
- 冻结预检 manifest SHA-256：`c9b777110bb522d6ca47934acc8d6ddc8ac496b7b14f6055664a5b1431769957`。
- 与历史 Flash 原始请求相比，仅 `model: deepseek-flash → deepseek-v4-pro` 不同。Prompt、Plan、P/S/E、temperature=0、thinking disabled、max_tokens=3000、JSON 输出方式均未改变。
- 旧 Web / retained receiver 固定 Flash，不能直接用于 Pro。本轮只在此新目录补齐并验证隔离 runner，没有修改生产 adapter、Gate、原生 Validator/Finalizer、E-only 契约或冻结包。
- 新许可 `PRO-TEST-991361F0-20261011-143000` 保存在既有固定 TEST-only SQLite 账本，先持久化消费，之后才创建 attempt 目录、读取凭据和创建真实 transport。消耗许可后再次以 unclaimed=True 只读验证，明确拒绝且账本行不变；没有第二次网络尝试。
- 真实 transport retries=0、follow_redirects=false、trust_env=false；OneShotTransport 绑定精确 URL / method / 请求 bytes / 截止并限一次；httpx 60 秒超时与 asyncio 总超时同时生效；请求 / 响应上限 16,000 / 65,536 bytes。没有余额、Flash、模型列表或 WordPress 请求。

操作与时钟证据：[execution-preflight.json](execution-preflight.json)、[trusted-clock.json](trusted-clock.json)、[attempt/authorization.json](attempt/authorization.json)、[attempt/preexecution.json](attempt/preexecution.json)。许可仍依赖本机文件系统信任，不代表生产 P1 抗回滚问题已解决。

## 原始结果与原生技术验证

| 项目 | Pro 实际结果 |
| --- | --- |
| 本轮真实生成 POST | **1** |
| HTTP / finish_reason | 200 / stop |
| 返回 model | deepseek-v4-pro |
| 完整原始响应 | 4,129 bytes，完整留存，没有改写 |
| 响应 SHA-256 | 3e164c7027cfe2d11793ad55105a0b874b4867c5356a835518c85e273180af68 |
| 模型文本 SHA-256 | b764d80f61bd1af235dd16c5a6dbac33bca8f0184effd32cd8204a3df0bc8b61 |
| Parser | PASS，现有严格 JSON / specification parser |
| Validator / Finalizer | **PASS**，现有 ContentDraftWorkflow / 原生 finalization，零修复 |
| 原生 Workflow | success，error=null，requires_human_review=true |
| 原生诊断 | numeric / claim type / block budget / competitor 均 null |
| 人工签核 | **未发生** |

Parser 与 Validator/Finalizer 的组合结果按原生实际边界报告，不伪造三个独立服务日志。原生 workflow 的成功路径确实完成 finalization；原始 JSON 没有预处理或修补。原生结果见 [native-result.json](attempt/native-result.json) 和完整序列化领域报告 [native-report.json](attempt/native-report.json)。本次没有技术失败候选；离线错误候选只存在于临时测试目录，不混入真实结果。

原始文件：[request.json](attempt/request.json)、[response-body.bin](attempt/response-body.bin)、[model-output.txt](attempt/model-output.txt)、[result.json](attempt/result.json)、[完整英文 Markdown](attempt/article-body.md)。[verification.json](verification.json) 复核了摘要、响应 content 与原文逐字节一致、请求未变、许可消费顺序及 E1。

## V4 Pro 完整英文文章

以下内容来自原生渲染文件，原样展示；正文含标题和 section heading 为 **153 词**，仅陈述为 142 词。统一词数正则为 `\b[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*\b`，数字和型号计入，Markdown 标记不计。

```markdown
NovaCNC machining center buyer guide

## spindle performance

Buyers need to evaluate spindle performance when comparing machining centers. A spindle rating should be read with its test conditions and intended application. Ask the supplier to identify the test method, operating duty and scope of any performance statement.

- Record the intended workpiece material and cutting application in the enquiry before agreeing acceptance criteria.
- Keep source documents beside the enquiry and refer unresolved applicability questions to a qualified reviewer.
- A bench test and a production acceptance test address different operating situations.
- Request evidence for the intended duty before relying on a rating in a purchasing decision.

## Test conditions and scope

SYNTHETIC ONLY: NovaCNC NCX7 spindle rated 7200 rpm continuously under NOVA-TEST-7 protocol at 20 C on an unloaded bench; applies only to NCX7 and is not a cutting-load or production guarantee.

Describe the planned cutting cycle, tooling and operating conditions before relying on a spindle rating.
```

## E1 独有事实与引用

两模型都完整复制同一 reviewed E quote。Flash 为 **E1→CL3**；Pro 为 **E1→CL8**。Pro 原生 claim 类型为 OBSERVED_PRODUCT_FACT，customer_refs=[E1]，page_refs=[]、source_refs=[]，没有把独有事实转给 P/S。证据 v2，F1，来源 `local:novacnc/E1/utf8-text`，区间 `[46,239]`，193 字符，与冻结来源逐字一致。

| 必须保留内容 | Flash | Pro |
| --- | --- | --- |
| NCX7 型号及仅适用于 NCX7 | 完整 | 完整 |
| 7200 rpm continuously | 原样 | 原样 |
| NOVA-TEST-7 protocol | 原样 | 原样 |
| 20 C | 原样 | 原样 |
| unloaded bench | 原样 | 原样 |
| 非 cutting-load / production guarantee | 完整 | 完整 |
| E1 独立引用，不混 P/S | 是 | 是 |

在这组合成材料内，未发现任何一方新增产品数值、单位换算、真实证书、加工保证或把台架结果外推成量产性能。此结论是证据一致性核对，不能证明合成测试是真实客户事实。Pro 将 E 放到条件一节更合适，但没有进一步解释这些条件如何影响采购适用性。

## 按冻结 rubric 逐项比较

规则文件仍为预检包中的 [rubric.md](../seo-model-comparison-preflight-2026-10-11/rubric.md)，没有因看到 Pro 结果而改规则。0–4 分，4 为本证据范围内充分；不合计总分掩盖事实问题。

| 维度 | Flash | V4 Pro | 具体依据与关键差异 |
| --- | ---: | ---: | --- |
| 客户事实 / E1 引用 | 4 | 4 | F-CL3 / P-CL8 均完整且独立。Pro 对普通背景主要只引 S1，引用角色更清楚；两者都未新增客户技术断言。 |
| 型号、数值、单位、条件、限定 | 4 | 4 | 上表全部保留，双方没有反向夸大条件。Pro 没有额外事实优势。 |
| 解释深度 | 1 | 1 | F-CL2/6/8 与 P-CL2/6 都只是要求看条件、区分 bench/production，没有展开“为何不同、如何判断当前应用是否可用”。E 的限制本身得到保留，未变成独立推理说明。 |
| B2B 搜索意图匹配 | 2 | 2 | 两者能回答基础 spindle checklist；都不足以兑现整个 machining center buyer guide 标题。Pro 重排 E 的位置改善局部组织，覆盖范围没有增加。 |
| 采购决策帮助 | 2 | 2 | 两者都提醒测试方法、工况、应用材料与证据，但没有形成连贯的适用性判断过程。P-CL9 增加应用描述的收尾动作，尚不足以提升整篇决策帮助档位。 |
| S1 照搬及重复 | 1 | 1 | Flash 5 条完整句逐字照搬，共 73 个空白分词；Pro 6 条，共 86 个，照搬增加。没有重复的整条内部 claim，但大量源句替代了自己的解释。E 强制原句不计照搬。 |
| 英文自然度与逻辑结构 | 3 | 3 | 两者语法基本自然。Flash 第二节有空泛解释与元话语收尾；Pro 将具体测试放到条件一节更贴切，但首节仍是来源句拼接。未形成明显等级差。 |
| CTA | 0 | 2 | F-CL10 只是说明这些内容的用途；P-CL9 明确要求描述 cutting cycle / tooling / operating conditions，构成较弱的准备动作。但未说明向谁、通过何种询盘动作提交。两者 CALL_TO_ACTION 类型均为 0，Pro 不能据此算明确询盘 CTA 已具备。 |

这里的 F-CL# / P-CL# 分别指 Flash / Pro claim ID，不是 page evidence 的 P#。

内部编辑可用建议条件是事实两项均 4、其余各项至少 3，且技术 PASS。**双方都未达到**。Pro 的改善集中在 E 的摆放和弱 CTA；没有解决深度、采购逻辑或照搬问题，不能据两项小改进判定明显优于 Flash。

客观文本指标见 [metrics-flash.json](metrics-flash.json) 与 [metrics-pro.json](metrics-pro.json)：

| 指标 | Flash 历史真实样本 | Pro 本轮真实样本 |
| --- | ---: | ---: |
| 全文词数，含标题与 heading | 170 | **153** |
| 陈述词数 | 159 | 142 |
| section / blocks / claims | 2 / 3 / 10 | 2 / 4 / 9 |
| S1 完整句逐字照搬 | CL4/5/6/7/9，共 5 条 | CL2/3/4/5/6/7，共 6 条 |
| S1 照搬空白分词数量 | 73 | **86** |
| 非 E claim 中照搬条数占比 | 5/9 | 6/8 |
| CALL_TO_ACTION 类型 | 0 | 0 |

照搬字数使用空白分词；全文词数使用上述英文正则，二者口径分别标示，不混算比例。P-CL9 并非 S1 的完整原句：S1 末尾本来截断于 tooling a；它是模型组织出的通用准备建议，不代表补齐了未验证来源的原文或获得了新的产品事实。

## 实际 Token 与费用

执行日 2026-10-11 为周日；双方实际调用均在空闲时段。公开官方人民币价格在调用前重新核对，与预检冻结费率相同。[DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

| 指标 | Flash 历史真实 | Pro 本轮真实 |
| --- | ---: | ---: |
| prompt_tokens | 2486 | 2485 |
| completion_tokens | 611 | **733** |
| total_tokens | 3097 | 3218 |
| 输入 cache hit | 1280 | **0** |
| 输入 cache miss | 1206 | 2485 |
| 实际 usage × 空闲费率估算 | ¥0.0036756 | **¥0.021078** |
| 同 usage × 高峰费率等价估算 | ¥0.0073512 | ¥0.042156 |

Pro 空闲公式：`(0 × 0.15 + 2485 × 4.5 + 733 × 13.5) / 1000000 = ¥0.021078`，低于本轮 ¥0.225 保守预算。没有查询余额或账单；这些数值是 usage 计价估算，非账户账单。原始 usage 留在 HTTP 响应；Pro 未返回 completion_tokens_details，不能伪造 reasoning 明细为 0。

本样本 Pro 实际费用估算约为 Flash 的 **5.73 倍**，其中包含 Flash 缓存命中而 Pro 未命中的影响。若 Flash 同样全未命中，按其实际 2486/611 Token 计算为 ¥0.004930；Pro 相比约 **4.28 倍**，仍不是在同输出文本上的严格单价倍数。输入相差 1 Token 不能作为输入被修改的证据，原始请求已经完成 byte 级核验；模型分词 / 服务计数可以不同。

Pro 文章更短而输出 Token 更多；其原始 JSON 有较多缩进与换行，结构化输出及序列化开销参与计费。因此不能把输出 Token 增长解读为文章更有深度。

## 对 MVP 模型与共同瓶颈的建议

**本轮没有充分升级到 V4 Pro 的依据。MVP 暂保留 Flash 作为成本较低的初稿模型候选，最终商业文章模型的选择尚未被这次实验充分验证。** 没有修改实际模型配置。这个建议来自同一受限输入下的结果，不是认定 Flash 或 Pro 在所有行业 / 任务上都更强，也不是允许 Flash 原稿直接交付。

双方只有 153–170 词，且分别仅用了 611/733 输出 Token、3/4 块、10/9 条陈述，远未达到 3000 Token、8 块、16 条上限。质量不足并非输出上限直接截断。模型确有未主动展开解释、未充分改写来源的表现；但单样本不能把它归结为模型能力不足。

Plan 只给一个 EXPLAIN 点和固定两节，没有成熟买家指南的采购问题链或 CTA 要求；Prompt 要求陈述短、词汇有据；更关键的是 P1 泛泛、E1 只有一个合成测试句、S1 仅 750 字符且截断未验证。这些共同限制让更深的技术解释缺少可用支持。

**最优先调整的一个共同瓶颈：采购决策证据包过薄。** 下一轮应先补齐并审核与采购问题直接对应的客户测试适用范围及可信技术背景，使文章能够解释测试条件与实际应用的关系；证据不足时要求补充材料。保持客户事实只能来自合格 P/E、E 引句完整及全部数字限制，不能用编造选型阈值或承诺补篇幅。本轮没有实施这些调整或进行后续实验。

## 验证、改动与停止状态

本轮先观察了两个预期 TDD 失败：未实现 runner 返回 None；缺失模型文本时 finish_reason 未保留。均在真实调用前修正。之后实际执行：

- 隔离 runner 的 `unittest discover -s docs/seo-model-comparison-live-2026-10-11 -p test_runner.py -v`：**15 项通过，0.814 秒**。
- `unittest tests.test_deepseek_content_draft_adapter tests.test_deepseek_draft_numeric_prompt tests.test_seo_e_only tests.test_content_draft_word_boundaries tests.test_web_deepseek_experiment -q`：**68 项通过，25.262 秒**，既有 Starlette/httpx deprecation warning。
- 冻结包核验、真实结果摘要 / 原生报告 / E1 核验通过，许可已消费且再次 unclaimed 验证被拒绝，没有发网络请求。

本轮未跑完整回归，没有把历史 1787 项当作本轮结果。只新增本独立目录的 runner、离线测试、原始真实结果、核验和比较报告。保留所有既有未提交修改和冻结包。WordPress、生产 Gate、P1、PostgreSQL、部署及 Git 写操作均未触及。

实验停止：真实 Pro POST 1；额外生成 0；自动重试 / 修复 0；余额 0；WordPress 0。当前无待执行的 live 任务，固定许可已消费，默认 runner 不会调用网络。所有 TEST-only 文章和 AI 内容评价均不产生生产权限或可信人类签核。
