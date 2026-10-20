# 单次真实 DeepSeek E-only 实验结果（2026-10-10）

**实验失败：原生 Finalizer 拒绝；响应留存成功。一次余额查询、一次真实生成，已停止，不重试。生产 NO-GO，PostgreSQL BLOCKED。**

授权仅绑定 `106eaa38e82a2802c267a876fad93e81b83171cb458e7a8be80966b1a46042f7`，至北京时间 2026-10-11 20:00:00；本次额度已使用，不延续到后续生成。请求参数及冻结材料未变。未修改项目源码、生产 Gate、P1 或数据库产品边界；没有 WordPress、发布、部署或 Git 写操作。

## 冻结与调用

报告定位的唯一冻结目录：[frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09)。14 个输入文件、117 个源码摘要、Bundle、Prompt 和请求均在调用前核对，并在结果审阅时再次核验。请求 SHA-256 为 `53a77560a5446b7d5e15699aa7f060112b7ae4dfe82f3e2d98ad9195edf1ed6b`，共 12,002 bytes；模型 deepseek-flash、thinking disabled、temperature 0、max_tokens 3000、总生成等待 60 秒，无重试/重定向。

一次 GET /user/balance：HTTP 200，账户可用，余额 ¥18.92。按峰时缓存未命中价格和 32,000 输入 Token 预留，保守费用 ¥0.088，要求余额至少 ¥0.10；这是估计而非账单封顶。来源：[DeepSeek 官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[官方余额接口](https://api-docs.deepseek.com/api/get-user-balance/)。

一次 POST /chat/completions：HTTP 200，finish_reason=stop，完整响应 5,314 bytes。输入 2,604 Token（命中 1,152，未命中 1,452），输出 972，合计 3,576。按返回 usage 估费约 ¥0.00536304（闲时）至 ¥0.01072608（峰时），未二次查询余额，也未验证账单。

## 实际判定与最小方向

原生 Parser：PASS。原生 Finalizer / Draft 校验：FAIL，`CLAIM_TYPE_CONTRACT`。未生成 DraftItem，后续 report Validator、SQLite 有效 Draft 保存/读回、原生 Markdown 导出均未到达。不能宣称文章技术通过。

阻断位置：`draft.sections[1].blocks[1].claims[1].claim_type`，规则 `EDITORIAL_CTA_FACTUAL_CONTENT`。原文 CTA 为：

> Contact the supplier to confirm how a stated test applies to your planned cutting cycle.

实际观察：has_numeric_expression=false，has_promotional_term=false，has_first_party_expression=true。核心检测以 `marker in folded` 匹配 `our `，命中了 `your planned` 中的子串。原生离线重放得到相同拒绝；最小探针 `your planned cutting cycle` 命中，`planned cutting cycle` 不命中。语义上此句是通用采购 CTA，没有企业能力承诺。这是一个可复现的词边界误判，未修改校验器或候选来绕过它。

最小修复方向仅为建议：另开有授权的离线修复工作，为 your/our 等边界增加 focused regression，修正第一方标记的词边界，保留真实第一方、型号、数值和促销约束。修复后需新冻结包与新真实调用授权；本次不实施、不再次生成，不开展新研究。

## 质量核对

| 验收项 | 实际结果 |
|---|---|
| E1 引用 | PASS：Q3 为完整原句，customer_refs=[E1]，page_refs/source_refs 均为空 |
| E1 独有事实 | 完整准确：NovaCNC NCX7；7200 rpm；continuously；NOVA-TEST-7；20 C；unloaded bench；only NCX7；not a cutting-load or production guarantee |
| 型号、条件、单位、限制 | 全部逐字保留，未换算单位，未转贴到 P/S |
| 无依据能力或营销承诺 | 本次 Codex 语义审阅未发现；不等于正式人工签核 |
| 原生 Draft Validator | FAIL：上述 CTA 误判；不能以语义合理替代技术通过 |
| 英文文章质量 | 两节、5 blocks、12 claims、约 209 词；有开头/清单/结尾，英语通顺；解释浅、段落重复，采购参考价值有限 |
| 原创性 | Q4/Q6/Q7/Q8 四句直接复用 S1；E1 原句复制属于冻结要求，单独核对 |
| SQLite 保存/读回与原生 Markdown | BLOCKED：Finalizer 已拒绝，无有效 Draft 入库；另行保留了拒绝候选 Markdown 预览 |
| /mvp 待审展示 | BLOCKED：现有桥接要求 SUCCESS + 有效 SQLite Draft；未强行把失败候选注入工作台 |

采购建议覆盖测试方法、工作制、工件材料、切削用途、验收标准和资料保留，但未充分解释空载连续转速不能证明负载切削性能的原因，也没有将型号/协议/温度逐项转成采购询问。当前更接近短清单文章，达不到成熟采购指南的质量要求。技术验收、Codex 语义审阅和正式人工签核分别为 **FAIL / 有限通过需改进 / 未签核**。

后续 MVP 建议：先离线解决这个确定的拒绝点；之后再考虑 Web 一次生成操作、失败留存/usage 展示和文章审核流。本轮未实施 Web 生成，也未把 TEST-only 审核升级为生产许可。

## 文件与验证

原始响应、模型正文、原样 rejected candidate、usage/finish_reason、解析结果、实际校验判定、逐项 P/S/E ledger、E1 核对、质量报告及英文预览均保存在新目录 [live-attempt](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09/live-attempt)。独立调用前核验、余额与费用记录在 [审计目录](E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-live-20261010-authorized-106eaa38)。原始文件逐字节与响应 content 对齐，SHA-256 与 diagnostics 一致。

本轮实际执行：`python -m unittest tests.test_seo_e_only_retention tests.test_seo_e_only_experiment tests.test_seo_article_experiment -v`，59 项 OK，退出 0；未运行全套测试。真实实验 CLI 退出 1（如实反映 CLAIM_TYPE_CONTRACT）；离线 Parser PASS / Finalizer FAIL 重放一致。存在已有 Starlette/httpx deprecation warning。

本轮只新增本地实验/报告文件，没有更改源码或历史实验。以下为完整拒绝候选的格式化预览，不是通过校验的正式 Draft。

---

> REJECTED CANDIDATE — native Finalizer failed (CLAIM_TYPE_CONTRACT). SYNTHETIC / TEST ONLY. No human signoff or production authorization.
> Formatting-only preview: all English claim text below is unchanged; the title comes from the frozen plan. The original JSON remains model-output.txt / rejected-candidate.txt.

# NovaCNC machining center buyer guide

## spindle performance

Spindle performance is one of the engineering topics a buyer is expected to evaluate when reviewing a machining center. A spindle rating should be read together with its test conditions and intended application. SYNTHETIC ONLY: NovaCNC NCX7 spindle rated 7200 rpm continuously under NOVA-TEST-7 protocol at 20 C on an unloaded bench; applies only to NCX7 and is not a cutting-load or production guarantee.

A bench test and a production acceptance test address different operating situations. Buyers should request evidence for the intended duty before relying on a rating in a purchasing decision.

- Ask the supplier to identify the test method, operating duty and scope of any performance statement.
- Record the intended workpiece material and cutting application in the enquiry before agreeing acceptance criteria.
- Keep source documents beside the enquiry and refer unresolved applicability questions to a qualified reviewer.

## Test conditions and scope

Test conditions and scope determine how far a stated spindle result can be applied to a buyer's own process. Buyers need to evaluate spindle performance, machining tolerance and certification scope as separate engineering topics.

Where a performance statement is limited to a named model or a defined protocol, that limitation belongs in the enquiry record. Contact the supplier to confirm how a stated test applies to your planned cutting cycle.

