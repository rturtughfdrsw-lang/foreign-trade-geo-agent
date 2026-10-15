# REAL_V3_EXPERIMENT_COMPLETE

实验执行完成，模型候选状态：**REJECTED**。完成实验不代表输出通过验收。

本次仅执行一次 DeepSeek Flash 请求。响应接收完成时间为 **2026-10-13 00:35:06.914（Asia/Shanghai）**。没有重试、fallback、换模型、第二次请求、JSON repair、自动修正或语义批准。`semantic_approved=false`，`production_authorized=false`。已停止。

## 授权与冻结输入核验

依据项目所有者本轮消息对指定 request / manifest hash 的一次性授权。冻结文件中的 `FROZEN_NOT_AUTHORIZED` 和历史网络标志未改写；它们记录冻结时状态，本次明确授权独立保存在执行记录中。

| 必查项 | SHA256 | 结果 |
|---|---|---|
| request 文件字节 | `d9bd075042613882b47dad0d2e56b7a1bb5aabdffda7b1f9abfbf12dac70a7ae` | PASS |
| manifest 文件字节 | `589c090c0bff0d1e38f7615eb2b61b4ad568e36a723a172227e000f3f9d834f5` | PASS |
| selection 领域绑定 | `237fb0ac0f5c3d5f88872405868ef080f9ec989138ad1cd9402831c58a1012be` | PASS |
| snapshot 既有绑定 | `a26579024bfd100c92199e5fb2af8714247b48a2514a803aedddde8cdc438430` | PASS |
| plan 重算领域绑定 | `2bdef501ae0eb3e3afb9f232c924bcf81ae3327fa9911b6514f32f1e89105084` | PASS |
| prompt 原始文件字节 | `d5d06d66a202395847ecd98471cf54cadb00fee8dbd388538f077b33724e2a14` | PASS |

manifest 的 **10/10** 引用文件及 integration 清单 **57/57** 文件核验一致。使用既有 Selection codec 和领域校验，重算 Plan/Evidence digest，检查 selected facts 的逐节投影、Prompt 原文字节及 request 参数。Snapshot 核验范围是冻结输入中的绑定一致性；没有访问客户网站或重建原始 snapshot。

在结果子目录创建之前，原 `verify_package` 六文件集合检查通过；发送前再次执行只读 hash、领域绑定和参数检查。没有重新冻结或写入任何输入。原六文件的执行前 hash 保存在 [preflight-verification.json](preflight-verification.json)，执行后复核见 [verification.json](verification.json)。

## 请求与响应

| 项目 | 实际记录 |
|---|---|
| Endpoint | `https://api.deepseek.com/chat/completions` |
| model | `deepseek-flash` |
| temperature | `0` |
| thinking | `{"type":"disabled"}` |
| response_format | `{"type":"json_object"}` |
| max_tokens | `16384` |
| timeout | HTTP timeout 60 秒，同时使用总调用 60 秒边界 |
| 请求体 | 原 `request.json` 31,739 bytes，直接发送文件字节 |
| 请求次数 | **1**，OneShotTransport 计数；HTTP transport retries=0，follow_redirects=false |
| HTTP | **200** |
| finish_reason | **stop** |
| latency | **37.889030 秒**，包括接收和响应留存开销 |
| response body | **64,118 bytes**，完整、未压缩、未改写 |
| model output | **61,033 UTF-8 bytes**，原 content 字符串无清理、改写或补字段 |
| response SHA256 | `9bf488c5bae70d2f688224595d4e8c5cf8cf90a79cbc8ed501189e8a6e696bca` |
| model output SHA256 | `a456ea3f966233e51d06e815796d0427b4391a0f9ba21b0fbbfc22e5179133b4` |

原始 HTTP 响应以 [response-body.bin](response-body.bin) 保存实体 bytes，以 [response-http-headers.bin](response-http-headers.bin) 保存状态行和客户端提供的响应 headers。后者不是 TLS/TCP 抓包或 chunk framing；本次无敏感 header 被剔除。未保存请求授权 header 或凭据。[model-output.txt](model-output.txt) 是 provider JSON `message.content` 的精确 UTF-8 表达；从 JSON 中提取字符串不代表修复输出。

[reception.json](reception.json) 记录接收指标；其 `failure_stage=native_validation` 是既有接收 helper 最后设置的阶段标签，本次该 callback 只返回、不执行验证，**不能据此声称 Native Validator 已运行**。真实逐层执行结果以 [validation-layers.json](validation-layers.json) 为准。

## Usage 与费用边界

| Usage 字段 | 实际值 |
|---|---:|
| prompt_tokens | 8,356 |
| completion_tokens | 12,681 |
| total_tokens | **21,037** |
| prompt_cache_hit_tokens | 0 |
| prompt_cache_miss_tokens | 8,356 |

五项 token 摘要见 [usage.json](usage.json)，供应商完整 usage 对象见 [provider-usage.json](provider-usage.json)，另含 `prompt_tokens_details.cached_tokens=0`。建议预算 USD 0.05 不是供应商账单金额。响应未提供收费金额，本次没有额外调用定价或账单 API，也未引用历史单价当作当前单价。因此实际美元费用记录为 **null / 未核实**，不能声称已确认低于 USD 0.05；实际结算以供应商对上述 usage 的计费为准。

## 严格五层验证

| 顺序 | 层 | 结果 |
|---|---|---|
| 1 | JSON envelope parse | **FAIL — `V3_EXPERIMENT_ENVELOPE_FIELDS`**；JSON 语法可解析，但顶层多出 `type: "json_object"`，不符合严格 envelope key 集合 |
| 2 | native candidate parser | **NOT_RUN**，Layer 1 失败 |
| 3 | Explanation Contract v3 | **NOT_RUN**，没有通过原生解析的 specification |
| 4 | Native Validator | **NOT_RUN**，没有通过原生解析的 specification |
| 5 | Review state | **REJECTED**；两个批准标志均为 false |

未删除多余 key 后重跑，未绕过 Layer 1，未构造修复 candidate，也未执行 finalizer 或创建可交付 DraftItem。以下是拒绝后的原文只读审查，**不是** Layer 2–4 的运行结果或语义验收。

## 解释链专项检查

模型生成 **19 条** explanation，六节分别 **2 / 2 / 3 / 3 / 3 / 6** 条。达到每节至少两条的数量下限，但不是所要求的 12 条合格链。既有 v3 实现以 explanation_budget 为下限，不能单凭 19 大于 12 宣称违反其数量上限。

| 检查 | 只读观察 |
|---|---|
| 完整契约合规链 | **0/19**：每条 decision_object 类型错误且 text_sha256 为空；正式 v3 inspector 未运行 |
| selected refs 与证据原文 | **19/19** 引用组限定在本节 selected facts，source_quote 精确一致，正文/sidecar 引用集合对应 |
| decision_object | **19/19 存在，0/19 类型合规**；模型写成 `{label: ...}`，契约要求枚举字符串；`spindle capability`、`application fit` 也不是允许的决策标签 |
| output hashes | sidecar_hash、candidate_hash 及全部 19 个 text_sha256 均为空；只记录，不补算回填 |
| boundary_type | **19/19 为 unknown**，枚举本身合法；未体现 condition_change，语义适用性未获通过 |
| boundary 正文模板 | **0/19** 精确匹配；只出现一份限制句，未按冻结公式同时拼接 boundary_condition 与 required_limitation |
| owner | **19/19** 在允许角色枚举内；这不证明真实责任主体或履约行为存在 |
| recipient | **7/19** 枚举合规；其余 12 条写 `buyer and supplier`，契约为 `both parties` |
| artifact | 均有字段和可理解名称；实际存在性未核验，材料是 synthetic/test-only，不能当作真实试验记录或签署承诺 |
| visible text 三段拼接 | **19/19** 等于自身三段拼接；不等于每段满足契约公式 |
| native proposal | **0/19** 存在；全部解释缺失既有 native proposal metadata |
| direct facts | 全文只有解释型 claims，缺少各节 required_direct_facts 对应的 OBSERVED_PRODUCT_FACT 保留位 |

逐条记录见 [explanation-audit.json](explanation-audit.json)。模型 native candidate 还使用 `draft.title/sections`、section 的 `heading/claims`，没有要求的 `change_ref/draft_type`、`outline_heading/blocks`。这些是直接读取 JSON 的结构观察，未调用 Parser 来产生额外层结果。

## A / B / C / D 失败分类

**A — Contract failure：已观察。** 正式首个失败是额外 envelope key。只读还发现 native schema、proposal、空 hash、decision/next_decision 类型、recipient 枚举、边界公式及直接事实保留位不满足契约。详见上表。

**B — Instruction following failure：已观察。** 未遵守保持 native schema、保留 proposal、受控枚举、hash 和逐字模板的指令。数量足够不代表链合格。正向观察是所引用事实及 source_quote 保持所选证据范围、批准标志保持 false；这些不能抵消结构失败。

**C — Reasoning quality failure：独立记录条件归属和验证闭环问题。**

- **CL1 条件归属过宽**：rationale 把“recorded travels and proposed table loads”一起归入 centered static loading 条件。证据中 centered/static 修饰台面载荷；行程另有 fixture/tool clearance 检查。数值本身没有改错，但条件跨对象附着，属于有依据的质量问题。
- **CL3–CL4 验证责任未闭合**：写成 buyer review loaded-trial / torque records，交由 supplier 决策，却没有指定谁实施尚缺的试验、产出记录。角色和 artifact 字段非空仍不足以证明可执行的验证链。
- **CL1–CL2 可见 recipient 不一致**：正文为 `for the configuration review`，结构字段为 supplier。
- **边界类型区分不足**：CL6、CL8、CL10 讨论记录设置、测量程序及不确定度条件，却全部归入 unknown。未知生产表现与“改变已记录条件后需重验”未清楚区分；这属于语义审查问题，不能由枚举合法推出通过。
- **未观察到无证据的新性能保证**：正文普遍保留 unassessed / proposed / pending 限制。但 CL1 已展示条件归属问题，因此不能宣称完全没有无依据推理。
- **历史 CL21 专项**：旧错误是 `different coupon counts`，实际两个来源都是三个 coupon。本次 CL9 保留 `three coupons per machine`，CL10 保留 `three consecutive ... coupons`，未声称样本数量不同。±0.02、±0.025、0.005 mm 等数值与相应引用一致；这只是只读证据对照，**不是 Native Validator PASS**，也不构成整体数值安全认证。

**D — Parser/Validator issue：未建立实现缺陷。** Layer 1 对真实多余字段的拒绝符合既有 exact-key 契约。其他三层未运行，不能把模型失败归咎于 Parser/Validator，也不能断言它们完全没有问题。冻结 Prompt 仍写有 offline synthetic hash_creator，并未嵌入完整 native draft/block schema，可记录为指令清晰度限制；本轮不修 Prompt、不改 Contract。

机器可读分类见 [failure-taxonomy.json](failure-taxonomy.json)。

## 文件、验证与剩余限制

新增内容全部位于授权目录内的 `real-v3-experiment-2026-10-13/` 子目录。包括执行器 `execute_once.py`、只读分层脚本 `validate_stored.py`、只读审查脚本 `audit_stored.py`，以及 preflight、started、原始响应/headers/hash、model output、usage、reception、validation、逐链审查、失败分类、execution summary、本报告与最终 verification / artifact manifest。没有修改生产源码、测试、原六个冻结文件或历史实验结果。

实际执行：只读冻结核验通过；单次 HTTP 接收完成；存储输出正式 Layer 1 **失败**；Layer 2–4 未运行；只读逐链审查完成；最终原六文件、57 项源文件、响应和输出 hash 及 usage 对照复核见 verification.json。**没有运行 unittest 或完整 suite，不引用历史测试通过作为本轮结果。**

最终复核的首次运行曾因将接收 helper 的五字段 usage 摘要与供应商完整 usage 对象直接比较而触发 AssertionError（exit 1）。只读定位确认差异仅为 helper 白名单未纳入的 `prompt_tokens_details: {cached_tokens: 0}`；五项计数完全一致，完整 usage 始终保留在原响应中。另存 provider-usage.json，分别核验摘要字段与完整对象后再次复核；不修改原 usage.json、响应或模型输出。此复核脚本假设错误不归入模型 A/B/C 或产品 Parser/Validator 缺陷。

目录布局限制：原 `verify_package` helper 要求目录条目严格等于六文件；本次按授权范围在该目录添加结果子目录后，直接对整个目录重跑该集合检查会拒绝额外子目录。原六文件内容未变。本轮最终检查按可信 manifest 及原六文件 hash 逐项复核，并未修改或放宽原测试/helper，也未重新冻结 manifest。

本次仅一次 synthetic 输入实验，不能外推模型整体能力或商业生产质量。真实 artifact/责任主体未核验，美元账单未获取，原生后续验证层未执行。未执行 WordPress、部署、生产发布、Git commit 或 push。没有后续自动任务。**REAL_V3_EXPERIMENT_COMPLETE；REJECTED；已停止。**
