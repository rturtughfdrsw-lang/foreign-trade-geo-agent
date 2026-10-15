# SEO Draft Contract v2 — REAL FLASH EXPERIMENT

最终状态：**REAL_EXPERIMENT_BLOCKED**

2026-10-12，项目所有者授权的唯一一次冻结请求已执行并完整保存。HTTP 成功，但冻结响应 Parser 在解释结构检查处拒绝输出；Validator 未运行，Finalizer 未运行。生成流程已停止，无重试、fallback、修复或第二次请求。以下分析仅读取保存的输出，不改变原结果。

## A. 真实请求信息

| 项目 | 实际记录 |
|---|---|
| Endpoint | `https://api.deepseek.com/chat/completions` |
| 请求次数 | **1** 次 DeepSeek HTTP POST |
| 开始时间 | 2026-10-12 22:35:05.008364，Asia/Shanghai；UTC 14:35:05.008364 |
| 请求／响应 model | `deepseek-flash` / `deepseek-flash` |
| 参数 | temperature=0；thinking={type:disabled}；response_format={type:json_object}；max_tokens=16384 |
| 超时 | 60 秒；HTTP timeout 与整个请求处理 deadline 均设为 60 秒 |
| HTTP status / finish_reason | **200 / stop** |
| latency | **20.084025 秒**；从 POST 开始至完整响应保存和供应商 envelope 提取，排除 Parser/Validator |
| 整次尝试耗时 | 20.097976 秒 |
| prompt / completion / total tokens | **8593 / 5599 / 14192** |
| cache hit / cache miss tokens | **0 / 8593**；prompt_tokens_details.cached_tokens=0 |
| 原始响应大小 | 29898 bytes；完整、未压缩、未超过响应上限 |
| raw response SHA256 | `ea45a5837fe3edd2c0b4e7e777b754cd64a9b84dbb8fb82af519ee85c517e24c` |
| model-output SHA256 | `ece11a7e83225e5a2e4d449b2a8621f9b759aa496b0faefdc45a3622ff8996d6` |

原始 entity bytes 保存在 `response-body.bin`；模型返回 content 的原始 UTF-8 字节保存在 `model-output.json` 和 `model-output.txt`，三者均未修复、重写或补引用。`request.json` 是冻结请求的字节副本，直接作为 POST content 发送。`attempt-started.json` 在发送前以独占创建方式消耗本次授权；已有标记阻止再次执行。`OneShotTransport` 核对 endpoint、方法、完整 body，且第二次传输被拒绝；底层 retries=0，redirects=false。

费用：执行前通过工具查阅了 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)，未发送 tokenizer 或探测模型请求。该公开文档查询独立于上面的唯一一次 DeepSeek POST。官方当前 Flash 每百万 tokens 非高峰费率：cache hit USD 0.003，cache miss USD 0.15，output USD 0.6；峰值费率分别为 USD 0.006 / 0.3 / 1.2。本次 UTC 14:35 在公布的峰值时段之外，使用非高峰费率。

`(0 × 0.003 + 8593 × 0.15 + 5599 × 0.6) / 1000000 = USD 0.00464835`。

这是根据实际 usage 和官方费率计算的估算，未核实账单扣费。usage 各字段均为非负整数，prompt=hit+miss、total=prompt+completion，completion 未超过 max_tokens；未发现 usage 异常。费用记录见 `cost-estimate.json`，价格核验见 `pricing-verification.json`。不存在进一步实验授权。

## B. 冻结验证

执行前使用所有者在聊天中给出的可信 manifest SHA256 验证，54 个文件及文件集合全部一致。请求重建、writer 投影、selection、task、Plan、evidence、解释要求和历史 frozen-v1 字节绑定全部通过；344 个保留源码／历史文件的完整性映射一致。工作区原有未提交修改保留，未要求工作区为空，也未丢弃修改。

| 文件 | 实际 SHA256（与 manifest／授权相符） |
|---|---|
| manifest.json | `5bfc54d91e5c0ba24b3043ef10871e937a84a9ad2abae968ad0fd86f06f85754` |
| request-body-template.json | `67556e8190c96aa554dd7cadbfc40c30a4e96513e23de6e5c27c29426e4dea40` |
| selection-artifact.json | `b75b0bb2808c3c1e9ed51bc73f48493386ed1b8161fc7b4daff66cbbf4109746` |
| evidence-snapshot.json | `dafa519a39d8c86292dad4066fb382c9c2bb03a1a23cb531685640a95af6f1bd` |
| plan.json | `83036daad9d1df1cfa1c939808c746b4e1a25de8b7f9cf7f37ba9f5c1d49d3d1` |
| source-integrity.json | `fd8842330d897e242bb8dd8aa29b1c9937c39782e1f2d7a770ca710ae27cb808` |

文件字节 hash 与领域绑定 hash 的范围不同，不混用。领域 selection / snapshot / Plan 绑定分别为：

- `237fb0ac0f5c3d5f88872405868ef080f9ec989138ad1cd9402831c58a1012be`
- `a26579024bfd100c92199e5fb2af8714247b48a2514a803aedddde8cdc438430`
- `2bdef501ae0eb3e3afb9f232c924bcf81ae3327fa9911b6514f32f1e89105084`

执行后再次完整复核通过，见 `post-execution-integrity.json`。没有重新冻结或向旧冻结目录追加产物。

## C. 模型输出统计与 frozen-v1 比较

历史基线来自 `docs/seo-flash-contract-quality-live-2026-10-12/frozen-v1/model-output.txt`，SHA256 为 `880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747`，已经核对。下表直接从两个原始模型输出计数。

| 指标 | frozen-v1 | v2 |
|---|---:|---:|
| sections | 6 | 6 |
| 合法 E fact refs：唯一标识符数 | 43 | 25 |
| 合法 E fact refs：出现次数 | 81 | 52 |
| 带合法非空 E refs 的 claims | 49 | 32 |
| 非法 E refs | 0 | 0 |
| 使用 P/S refs 的 claims | 0 | 0 |
| claims | 50 | 33 |
| blocks | 16 | 13 |
| 直接事实 claims／exact quotes | 43 / 43 | 26 / 26 |
| interpretation claims | 6 | 6 |
| 显式 explanations 标注 | 0（V1 无此 wire 要求） | 6 |
| CTA | 1 | 1 |
| 正文英文词数 | 1300 | 1053 |
| interpretation 正文词数 | 186 | 362 |
| 多出 source 的章节 | 2 | 0 |
| requirement 不匹配的 claims | 4 | 0 |
| 重复正文 claim 对 | 0 | 1：CL12 / CL19 |

“合法 refs”仅表示标识符存在于冻结事实库，不证明引用与推理语义匹配，也不等于整篇获准。V2 使用了全部 25 个选定唯一 facts；26 条直接引语包含一次跨章重复。合法 refs 总数减少来自缩小选择范围，不能把数量减少本身当作质量提升。

## D. Parser 结果

**冻结实验响应 Parser：FAIL，原始错误 `PREFLIGHT_RESPONSE_INVALID`。** 外层 JSON 可读取，无重复 key，顶层确为 candidate / explanations；补充只读诊断中，原生 candidate Parser 为 PASS。原生语法通过没有改变实验响应 Parser 的失败结果。

冻结 adapter 在构造 `ExplanationAnnotation` 时执行既有结构检查。第一个标注 CL6 的 buyer_implication / non_applicability / verification_action 为 **40 / 7 / 7** 词，要求至少 **20 / 12 / 20**，对应最早可定位原因 `EXPLANATION_PART_DEPTH`；adapter 将此类失败统一映射为上述公开错误码。

| 标注目标 | 所属章 | 三部分词数 | 合并词数 | 指向 interpretation／正文一致 |
|---|---|---|---:|---|
| CL6 | S1 | 40 / 7 / 7 | 54 | 是／是 |
| CL11 | S2 | 39 / 5 / 8 | 52 | 是／是 |
| CL16 | S3 | 50 / 6 / 8 | 64 | 是／是 |
| CL21 | S4 | 53 / 7 / 7 | 67 | 是／是 |
| CL25 | S5 | 47 / 5 / 8 | 60 | 是／是 |
| CL33 | S6 | 50 / 6 / 9 | 65 | **否／否** |

六条标注全部缺少要求的边界／验证深度；前两条合并正文还低于 60 词。最后标注写为 CL33，但 CL33 是 CTA，实际解释在 CL32，导致目标、refs 与正文绑定不成立。没有纠正编号、延长正文或构造可接受 sidecar。详细原文与计数见 `parser-diagnostics.json`。

## E. Validator 结果

**NOT_RUN：响应 Parser 先失败。** 没有对失败产物调用 Validator，没有进入 Finalizer，没有创建 DraftItem，没有赋予 PENDING_SEMANTIC_REVIEW 状态。历史 frozen-v1 的原 Parser PASS 和 Validator 拒绝记录原样保留。

只读计数还发现逐章仅 1 个 interpretation，冻结 selection 每章要求至少 2 个；CL12 与 CL19 是同一条 E4.F01 完整引语，违反唯一正文指令。这些是保存产物的可见不符合项，**不是声称已经观察到本次 Validator 的错误码或完整结果**。源码和 Validator 均未修改。

## F. 质量分析

本次是 **controlled comparison**：同一历史 synthetic task/evidence、同一模型别名与参数；Selection Contract、Writer context、Explanation requirement 一起变化。采用 **observed improvement** 描述观察，不能推断单个变化的因果作用。不是 strict A/B；模型后端可能随别名更新，审读未盲化，由本助手完成，不构成人工批准。

### Section routing

| 章节 | frozen-v1 观察 | v2 观察 |
|---|---|---|
| S1 配置筛选 | E2 / E5，与要求一致 | 一致；覆盖所有选定 refs |
| S2 主轴 | 多出 E5；CL18、CL19 使用不属于该章 requirement 的 E5.F03 | 仅 E1 / E3；没有该错路由 |
| S3 应用 | E4，与要求一致 | E4，与选定范围一致 |
| S4 验收测量 | 多出 E5；CL32、CL35 使用不属于该章 requirement 的 E5.F04 | 仅 E3 / E4 / E6；没有该错路由 |
| S5 采购验收 | E6，与要求一致 | E6，与选定范围一致 |
| S6 交付支持 | 缺少所需 E2 | E2 / E5 / E7 齐全 |

可记录 routing 的 observed improvement。所有 v2 章节 used refs 等于各自 selected refs，required_direct refs 无遗漏。但每章的解释 reservation 都未满足，所以不能写“完整 V2 contract PASS”。

### 采购解释深度：逐章原文依据

| 章 | frozen-v1 → v2 观察 | 质量限制 |
|---|---|---|
| S1 | V1 CL7 仅称筛选为有条件候选；V2 CL6 用夹具超出小机型台宽和拟议载荷解释为何只保留大机型为待核候选。决策机制更具体，有 observed improvement。 | 仍只复述固定一句边界和下一步，没有展开谁提交哪些布局／动态载荷记录；解释只有 1 条。 |
| S2 | V1 CL19 概括空载铭牌不是切削能力；V2 CL11 把其定位为负载试验的边界条件，并明确不支持机型切削能力比较。 | 定性解释稍多，但没有设计代表性工况、扭矩记录核验责任或验收判断；不能以更长正文证明更深推理。 |
| S3 | V1 CL25 覆盖铝和钢两种试验；V2 CL16 围绕选定铝材、毛坯、夹具和图纸缩小适用范围。事实范围不同，不能按钢案例是否出现直接评优劣。 | CL16 引用 E4.F04/F05 的循环记录，却未解释小样本、排除装卸对采购节拍判断的作用，仍有引用未被充分用于分析的问题。 |
| S4 | V1 CL35 泛称方法、夹具和不确定度不同；V2 CL21 延长为为何验收不能只看记录值。 | **关键推理错误**：CL21 说 measured/proposed 使用不同 coupon counts；E3.F07 明确每台 three coupons，E6.F03 是 three consecutive coupons。现有证据支持连续性／程序约定区别，不支持样本数量不同。S4 不认定 observed improvement。 |
| S5 | V1 CL40 仅称责任尚未固定；V2 CL25 连接节拍未约定、台架时间不构成合同限制与书面验收安排。可观察到更明确的采购机制。 | “没有这些协议就没有放行依据”应作为待双方认可的建议；没有详细列出测量／纠正／复验职责。边界和行动仍很短。 |
| S6 | V1 CL49 概述配置绑定；V2 CL32 把报价配置与测试基础配置一致性连接到交付／支持依赖。 | 仍以通用的条件／排除条款概括，没有逐项解释响应与恢复、远程培训与现场调试的区别；侧车还指向了 CTA。 |

S4 可复核原文片段：`different coupon counts`（CL21）。它没有新增数值，但新增了没有证据支持的定性比较，不能靠合法引用标识符掩盖。正文完整上下文见 `article-reading-view.md`，事实原文保留在冻结 `evidence-snapshot.json`。

### CTA 质量

V1 CL50 请求图纸版本、材料状态、夹具布局、目标节拍和验收优先项。V2 CL33 在这些项目上增加 configuration and delivery inputs，仍请求 scoped review，未承诺适用性。输入覆盖更完整，可以记录 CTA 的 observed improvement；尚未明确回复责任人、交付核验材料或评审步骤。CTA 改善不能抵消标注绑定失败和 S4 推理错误。

整体：claims／事实堆积减少、routing 改善、部分决策机制更具体；解释数量没有增加，结构深度要求被忽略，存在实际推理错误。没有任何人工质量批准或商业审核。

## G. 失败原因与分类

| 分类 | 本次结论 |
|---|---|
| **A Contract failure** | 已观察到输出违反 explanation contract：分段最少词数、部分总词数、最后标注目标／正文绑定不符合；每章解释 reservation 未满足。指输出不符合合约，并不说明冻结合约本身矛盾。现有 synthetic mock 在相同合约下通过。 |
| **B Instruction following failure** | 明确要求每章至少 2 个解释、20/12/20 分段词数和全局正确 claim ID，实际未遵守；重复引语也违反唯一正文指令。与 A 同时记录。 |
| **C Reasoning quality failure** | S4 “样本数量不同”与所引用事实不符；S3 未充分分析引入的节拍前提；多个章节验证步骤仍空泛。此为原文审读发现，尚未经过人类语义复核。 |
| **D Validator issue** | 本次未建立：Validator 未运行，不能把本次拒绝归因于 Validator 误判。历史基线中的争议诊断不自动迁移到本次结果。 |

最早阻断层是冻结响应 adapter 的解释结构构造。没有传输、超时、截断、usage 异常或价格未确认事件。本次单样本不足以评价模型能力上限，不触发换模型。

## H. 下一步建议、验证与停止边界

下一步仅建议由人审阅本报告及 CL21 的证据对照，并确认是否需要另行授权离线改进任务表达／解释生成约束。若后续修改 prompt、contract 或代码，必须使用新版本冻结包和新的请求授权；本次输出、旧冻结包和拒绝结果保持不变。本轮不实施这些建议，也不请求第二次模型生成。

本轮实际验证：

- 冻结 CLI verify：执行前 PASS；执行后 PASS，54 个清单文件及源码完整性一致。
- 隔离 runner 默认 offline check：PASS；已有 synthetic envelope 达到 PENDING_SEMANTIC_REVIEW；MockTransport 收到完全相同 body，第二次请求被 guard 拒绝，真实 API 调用为 0。
- 真实唯一请求：HTTP 200、stop；**响应 Parser FAIL，Validator NOT_RUN，Finalizer NOT_RUN**。
- 原始响应／content 字节一致性、baseline hash 和最终来源复核：PASS。
- `python -m unittest tests.test_seo_draft_v2_flash_preflight tests.test_draft_contract_v2 tests.test_draft_explanation_contract -v`：**55 tests，9.292s，OK，exit 0**。没有运行全量 suite；这些测试不代表本次真实输出通过。

新增文件全部位于本报告目录：隔离 `run_once.py`、只读 `analyze_readonly.py`、本报告、请求／响应、执行／价格／诊断／比较／完整性记录及正文阅读视图。没有修改生产代码、Validator 或原冻结包；没有 WordPress、部署、Git commit/push、补引用、JSON 自动修复或人工／商业批准。

局限：一次历史 synthetic evidence 比较、非盲化助手审读、参数别名可能跨时间改变后端、费用为估算、未完成本次 Validator 和人类语义／商业评审。所有生成已停止，等待项目所有者下一步指示。
