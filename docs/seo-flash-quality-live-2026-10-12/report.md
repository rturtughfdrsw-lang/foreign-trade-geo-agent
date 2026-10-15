# DeepSeek Flash 真实 SEO 文章质量实验

**结论：唯一一次真实请求完成，JSON Parser 通过，原生 Validator 拒绝。没有达到 COMMERCIAL SEO DRAFT READY。**
文字主要是参数与限制的改写，加少量泛化解释；按本轮成功标准，生成质量不足。更直接的交付阻断是模型忽略整个 E 引用/解释候选契约。
实验已结束：真实 POST 1 次，重试 0，fallback 0，JSON 修复 0，润色/二次生成 0。

所有客户资料、文章和审阅记录均为 **SYNTHETIC / TEST ONLY**。没有 WordPress、发布、部署、Git commit/push、PostgreSQL 或生产 Gate 变更。

## 真实请求、usage 与费用

执行时间（Asia/Shanghai）：2026-10-12 **00:34:55.821879 → 00:35:06.467724**。
记录的总处理延迟为 **10.643521 秒**，包括 HTTP、留存和原生校验；没有独立声称精确的纯推理时间。

| 项目 | 实际结果 |
|---|---|
| model / temperature / thinking | deepseek-flash / 0 / disabled |
| response format / output cap / timeout | JSON / 16,384 tokens / 60 秒 |
| HTTP / finish_reason | 200 / stop |
| prompt_tokens | **7,610** |
| prompt_cache_hit_tokens / prompt_cache_miss_tokens | **1,024 / 6,586** |
| completion_tokens / total_tokens | **3,387 / 10,997** |
| 完整响应 / 模型文本 | 14,018 / 12,642 bytes，未超限、未截断 |
| 低峰费用估算 | **USD 0.003023172** |
| 同 usage 高峰等价估算 | USD 0.006046344 |

低峰公式：`(1024 × 0.003 + 6586 × 0.15 + 3387 × 0.6) / 1,000,000`。
费率来自执行前核查的 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)；调用发生于周日 UTC 的低峰时段。
这是 usage 计价估算，没有查询账户余额或账单。响应没有 reasoning tokens 明细，不将其伪造为零。
费用、完整 usage（含 cached_tokens）见 [cost-estimate.json](cost-estimate.json)；执行状态见 [result.json](result.json)。

## 冻结核验

执行前独立核对 75 个产物和 173 个代码文件，全部 SHA256 相同；当前 SQLite Intake snapshot 与冻结快照一致。
task v1、Plan v2、evidence v2、writing brief、System Prompt、User Material 和重建 request 均未改变。
七份资料、43 facts、六章结构保持不变。冻结有效期内执行，没有重新生成/修补冻结材料。
既有 loader 仅在内存刷新 TEST review 时间戳，随后再次确认请求 bytes 完全一致；它不产生真人签核。
预请求 tokenizer 精确计数仍未知，冻结报告的估算不确定性被保留；本次已获得用户对一次真实请求的明确授权，实际用量以上述服务端 usage 为准。

- request SHA256：`7163ba11207bed8636053ce39779c5fc4d424933b23c3cce22d99295f6573bb9`
- bundle SHA256：`e1a416ed8794d86c8e4f656eac7fb47b8076d9639422c993ec27ce39c9d0e043`
- response SHA256：`c524233d3ecdb3f244ce7ded84cf035361ce1aa48ccccad63cac7e6d1d05eed2`
- model text SHA256：`9725b1334f3c7f38a6f2095552597625d6388e6d00fbc309a8281320c2b74840`

许可在现有固定 TEST-only SQLite 账本中先持久化消费，再加载凭据并创建 HTTP transport。
OneShotTransport 限定精确 endpoint、POST、请求 bytes 和一次调用；HTTP 与总超时均为 60 秒，零 transport retries、不跟随重定向。
请求与原始响应留存目录限制为当前本机账户访问；凭据没有写入日志/报告/产物。

## Parser / Validator / Finalizer

| 环节 | 实际结果及解释 |
|---|---|
| 原始 provider JSON / envelope | 有效，完整留存，model=deepseek-flash、finish=stop |
| 原生严格 Parser | **PASS**；旧 P/S 四字段 claim 仍是合法解析形状，不等于当前 E 契约合格 |
| 原生 candidate Validator | **DETERMINISTICALLY_REJECTED** |
| claims / blocks / sections | 48 / 16 / 6；claim 数达到上限，块数和输出 tokens 未触顶 |
| E 引用 / fact binding | 所有 48 条 claim 都无 customer_refs；47 条非 CTA 报 CLAIM_TYPE_CONTRACT；原生成功绑定事实 **0/43** |
| 解释候选 | EVIDENCE_BASED_INTERPRETATION=0，proposal=0 |
| 其他原生发现 | CUSTOMER_EVIDENCE_COVERAGE；六章各有解释/行动/限制、问题回答及问题证据覆盖错误；BACKGROUND_DOMINATES |
| Finalizer | **NOT_RUN_VALIDATOR_FAILED**，依用户“Validator 失败即停止”要求未继续；不伪报 Finalizer 通过或 pending |
| 正式 Draft / 真人批准 | 未产生正式准入 Draft；没有真人批准 |

错误完整记录见 [candidate-validation.json](candidate-validation.json)。原始候选另外留存在 local-review.sqlite3；这是拒绝候选留档，不是正式内容 artifact 或语义批准。
原始 JSON、原始文本和 rejected-candidate.txt 保持逐字节相同；没有补 customer_refs、改 claim_type 或加 proposal。

数字、型号与限制：AI 编辑逐条对照发现，43 条 E 事实的文字内容均有相应改写，未观察到新增技术数值、交叉挪用 NCX7/NCX10、价格、认证、客户案例或性能保证。
例如 CL13 保留 7200 rpm / NOVA-TEST-7 / 20 C / unloaded / 非生产保证，CL23/29 仍只把钢试验归给 NCX10，CL41–46 保留拟议商业条款和排除范围。
**这不等于数字校验通过**：原生检查先在错误 claim 类型/引用边界拒绝，后续完整数值绑定未获通过。
诊断来源对照覆盖 43/43 只说明文字可追溯核对，绝不替代模型缺失的 fact binding。

## 文章全文与质量审阅

[完整英文文章](article-full.md) 保留每条模型文字，按原始段落/列表排版；标题取自冻结 Plan，外层醒目标记 SYNTHETIC / TEST ONLY 与 Validator 拒绝状态。
[逐条标注版](article-annotated.md) 提供 S#/B#/CL# 定位；[原始模型 JSON](model-output.txt) 和 response-body.bin 未改写。

已生成 [七维真人 review 表](human-review.md)：事实准确性、条件和限制、解释深度、采购价值、搜索意图、原创性/模板感、CTA，均提供具体段落和原因。
**真人 0–4 分尚未填写，没有真人审阅人。** 表内观察是非盲 AI 编辑预审，不是自动评分或真人判断的替代品，不计算总分。

AI 编辑结论：限制保留较充分，选型/RFQ/支持内容覆盖比历史稿广，但主要把资料中的既有推论一并改写。CL12/19/25/33 是泛化的“检查条件有帮助”句，没有展开参数意义、适用性推理或下一步验证设计。
CL10 的夹具排除和 CL18 的转速不可排名本来已经写在 E5，不证明模型独立产生了深入采购分析。
CL48 有克制的询盘动作，但输入要求泛泛。按用户“参数列表 + 泛泛解释即质量不足”的标准，本次内容未达标。

## 与历史低资料 Flash 比较

| 项目 | 历史 Flash | 本次丰富资料 Flash |
|---|---|---|
| 资料/主题范围 | 一条 E1 主轴事实、基础两节 | 7 documents / 43 facts / 六章 |
| 全文词数（同一英文正则，含标题/heading） | 170 | 1,174 |
| 正文 claim 词数（同一正则） | 159 | 1,136 |
| blocks / claims | 3 / 10 | 16 / 48 |
| 客户证据引用 | E1→CL3 正确，原生通过 | E refs 完全遗漏，原生拒绝 |
| 解释 | 看条件、索要证据等基础提醒 | 覆盖更多条件/场景，但仍以资料改写和泛化解释为主 |
| CTA | 无 CALL_TO_ACTION，收尾元话语 | CL48 明确请求应用、记录和条款，仍偏泛 |
| 商业可交付状态 | NEEDS_REVISION | REJECTED / NOT READY |

历史依据为 [metrics-flash.json](../seo-model-comparison-live-2026-10-11/metrics-flash.json) 和 [原对照报告](../seo-model-comparison-live-2026-10-11/report.md)。
这是整体条件变化后的质量实验，**不是严格单变量实验**：输入资料、任务范围、Evidence contract、Prompt、Plan 和容量均改变。更长不构成成功，也不能把差异纯归因于模型能力。

## 问题归因与最终决定

直接技术原因已确认：模型输出沿用 P/S 四字段 schema，把仅存在于 E 的客户事实标为 P1/S1–S4，没有 customer_refs/新解释 proposal。
原生 Validator 在 `core/content_draft.py` 的结构化 E 防逃逸规则处拒绝，这是安全边界正常生效，而不是资料丢失或网络截断。

| 归因类别 | 本次证据支持的判断 |
|---|---|
| A 模型能力 | 观察到指令遵循失败和浅层改写；只有一次样本，不能确认是 Flash 固有能力上限 |
| B Prompt | 高优先级嫌疑：System Prompt 前部写“Every claim is exactly”四字段旧 schema、P-only 和短/词汇受限规则；末尾 E CANDIDATE 才覆盖，user contract 又另列 E 规则。实际输出吻合旧 schema。存在竞争指令的证据，但未经单变量验证，不能宣布因果已证实 |
| C Planning | 六章、问题、资料和 brief 齐备，模型实际遵循 heading，未见 Plan 丢失；部分测量/验收章节重叠可能削弱阅读衔接，不能解释 E 引用全部消失 |
| D Evidence contract | 输入完整，43 facts 和 refs 都在 request；失败在模型未实现绑定与解释边界。Parser 为兼容历史格式接受 P/S shape，Validator 随后正确拒绝。不应误称“原生链路成功”或“证据不足” |
| E 其他 | 未见超时、截断、JSON 破损、输入漂移、响应超限或重试；输出 3,387 tokens 远低于 16,384，不能归因于输出 token 截断。48 claims 恰好封顶可能影响展开，但现有观察不能确认原因 |

最终决定：**COMMERCIAL SEO DRAFT READY = NO**。同时存在硬性证据契约失败和实质解释深度不足；即使文字数值看似正确，也不能准入。
真人专业质量评价仍待填写；本轮未修改 Prompt、Plan、契约、模型参数或文章，也没有开始下一轮实验。

## 修改与验证范围

本轮只新增 `docs/seo-flash-quality-live-2026-10-12/` 下的隔离 runner、原始响应/请求、诊断/全文/审阅与报告；既有源代码和冻结材料未改。
另有授权所需的固定本机 TEST-only 许可账本新增并消费一条记录；不涉及生产许可。

实际运行相关 unittest：**47 tests，44.743 秒，OK，exit 0**，命令见 [public-price-and-verification.md](public-price-and-verification.md)。保留既有 Starlette/httpx 弃用提示；本轮未跑全量回归。
真实 Validator 失败为本次实验结果，已准确保存，不以测试通过掩盖。最终完整性与许可消费核验见 verification.json。
最终核验的首轮命令曾使用相对路径调用要求 absolute Path.as_uri() 的 Reader，导致只读重读失败；改用解析后的绝对路径后，16 项完整性检查均通过。没有更改 SQLite、生产代码或响应，也没有再次 HTTP 调用。
