# Frozen-v1：唯一一次 DeepSeek Flash 契约与质量实验

技术契约：**基本 E Candidate 输出形状遵循；完整 Candidate Validator FAIL**。内容质量：**相比旧契约失败实验，证据绑定和询盘指引改善；相比上一轮真实 Flash，没有证明采购分析整体提升**。商业交付：**NOT_READY，未达到 COMMERCIAL SEO DRAFT READY**。

本报告是 Codex AI 预审，不是真人工程审核、商业签核或稳定性测量。真实请求使用合成 CNC 资料；“真实”指真实调用和模型原文，不代表真实客户参数。单次拒绝不证明模型能力上限。

## 1. 冻结与授权

唯一输入是 `docs/seo-draft-contract-offline-2026-10-12/frozen-v1/`。执行前先读取 readiness，再重算以下绑定：

| 项目 | 实测 SHA256 |
|---|---|
| Request | `9273e145beaacb122e57261294143c1a9df0cd4faba8554a03609c194e86ab0f` |
| Bundle（artifact-sha256.json 原始 bytes） | `ad96bbb5d8fee7d35fee5832d51cea96d65bce607e08e8b9fa09868ed875a9cf` |
| 内部原生执行包 | `a759d82ac2f6c6f1ecbf49a92e80beb9d32a818a728bee817d748fb529305dad` |

82 个冻结产物、175 个源码文件全部匹配，Parser/Validator 摘要中的六个函数源码摘要独立匹配。task、Plan、writing brief、7 份资料、43 facts、E Candidate contract、System Prompt、User Material 均在该绑定内且未改变。原生 request builder 重建 payload 与冻结 bytes 相同。执行后再次核验一致；未重新冻结。

本轮用户消息明确授权该 request/bundle 的一次真实实验。固定本机 permit 账本未发现相同 request/bundle/permit；新增一次性许可 `WEB-TEST-FLASH-FROZEN-V1-2026-10-12-ONE-SHOT`，在 HTTP 前持久化消费。许可不扩展到重试、其他模型、生产交付或 WordPress。

readiness 中的 `BLOCKED_PUBLIC_CONFIGURATION_AND_TOKEN_BOUND_CONFIRMATION` 是离线冻结时状态，未改写为 PASS。执行期另存 [preflight.json](preflight.json)：核对官方公开参数和价格，记录 tokenizer 未精确验证、估算不是账单硬上限。官网正文抓取超时，公开信息来自本次检索返回的官方文档内容；未将其表述为成功直接抓取。当前用户明确指定模型、参数并授权本轮；未沿用上午已经消费的旧许可。

保持冻结文件只读。只在实验内存中刷新现有 TEST reviewer 的审核时间，并对同一个 snapshot 执行既有 FactsOnlyReviewer 检查；源事实、Plan、brief、版本、offset 和 payload 没有变化。原始输入与有效输入分别留存在 `frozen-native-input.json`、`native-input.json`；此时间变化不是真人批准。

同日父目录已有上午另一个 hash 的真实实验，全部保留。本次文件存入该目录的 `frozen-v1/` 子目录，避免覆盖历史报告。

## 2. 唯一请求与留存

| 项目 | 实测 |
|---|---|
| 模型 / temperature / thinking | deepseek-flash / 0 / disabled |
| response_format / max_tokens / timeout | json_object / 16384 / 60 秒 |
| 真实 POST / retry / fallback / JSON 修复 / 二次生成 | **1 / 0 / 0 / 0 / 0** |
| 开始 / 完成（北京时间） | 2026-10-12 17:14:26.432729 / 17:14:44.783225 |
| HTTP / finish_reason / 返回 model | **200 / stop / deepseek-flash** |
| prompt / completion / total tokens | **7812 / 4915 / 12727** |
| cache hit / miss / cached_tokens | **512 / 7300 / 512** |
| 响应获取和留存延迟 | **18.311725 秒**，含客户端初始化、完整 body 留存与 provider envelope 提取；不含原生候选解析验证，不等同于纯推理耗时 |
| 端到端延迟 | **18.349762 秒**，含原生检查及候选入库 |
| 原始 HTTP body / model text bytes | **20289 / 18685**，完整，无截断 |
| 费用估算 | **USD 0.008091072**，实际扣款未核实 |

本次处于周一 UTC 09:14，属于官方工作日 06:00–10:00 峰值窗口。按每百万 token 的 cache hit 0.006、cache miss 0.3、output 1.2 美元估算：`(512×0.006 + 7300×0.3 + 4915×1.2)/1000000`。参数及费用依据：[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion)、[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。未查询余额或账单。

留存包括：

- [response-body.bin](response-body.bin)：原始 HTTP entity bytes；[http-response.json](http-response.json) 保存状态、HTTP 版本及允许留存的响应头。请求授权头及敏感响应头不持久化。
- [response.json](response.json)：与原始 body 逐字节一致的 provider JSON；[model-output.txt](model-output.txt) 与 [model-output.json](model-output.json) 是原始 content，后者直接复制原 bytes，没有重新序列化。
- [provider-result.json](provider-result.json)、[cost-estimate.json](cost-estimate.json)：在模型 JSON Parser 调用前写入 usage、cache、finish_reason、延迟及估算。
- [execution-summary.json](execution-summary.json)、[stage-order.json](stage-order.json)：一次调用计数和实际验证顺序。
- [article-full.md](article-full.md)、[article-annotated.md](article-annotated.md)：原文只读视图；标题来自冻结 Plan，正文逐 claim 原样保留，注释与模型文字分开。

HTTP body SHA256：`a69e3ceb43fbbf2432c17efce6dca64bdeaf81c287bff3b140bd08a12a7c578a`。

Model text SHA256：`880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747`。

目录在调用前已限制为当前 Windows 账户访问。先 fsync 原始响应，再解析 provider envelope 以提取原始 content/usage；模型内容解析与验证发生于全部必需留存之后。

## 3. 技术契约结果

执行顺序为：Provider response 留存 → 原生 JSON Parser PASS → Candidate Validator REJECTED → 原生 Candidate Review SQLite 入库 → 停止。因为 Validator 拒绝，TEST-only review replay 与 Native Finalizer 均 **NOT_RUN_VALIDATOR_REJECTED**。没有手工补 refs/proposal、调整 claim_type、生成批准或正式 Draft。

| 指标 | 本次 |
|---|---|
| sections / blocks / claims | **6 / 16 / 50**，claim 上限48 |
| 引用非空且所有 E refs 合法的 claim | **49**；另1条 CTA 无引用 |
| E 引用 claim 中无单条原生错误 | **48**，不是48条已正式准入 |
| OBSERVED_PRODUCT_FACT / 精确源句 | **43 / 43** |
| EVIDENCE_BASED_INTERPRETATION / proposal | **6 / 6** |
| 多事实解释 / 无单条错误的解释 | **6 / 5** |
| unique fact coverage | **43/43，100%** |
| 无效 E fact_ref | **0** |
| 错误 P/S 引用数 / 使用 P/S 的 claim 数 | **0 / 0** |
| 正式准入解释 / Finalized Draft | **0 / 0** |

事实覆盖是描述性指标。冻结契约已明确 structured facts 只需必要的合法子集，保留章节 source/requirement 约束；本轮没有全量43条硬配额。模型仍逐条输出全部43 facts，再加6条解释和CTA导致50条超限。100%覆盖不抵消预算和路由失败，也不是写作质量提升证据。

完整原生拒绝诊断见 [candidate-validation.json](candidate-validation.json)：

```text
CL40: COMPETITOR_MENTION
CLAIM_BUDGET
SECTION_EVIDENCE_OUTSIDE_QUESTION: Read spindle and cutting trial evidence
SECTION_FACT_OUTSIDE_QUESTION: Read spindle and cutting trial evidence
SECTION_QUESTION_EVIDENCE_INCOMPLETE: Read spindle and cutting trial evidence
SECTION_EVIDENCE_OUTSIDE_QUESTION: Specify representative acceptance tests
SECTION_FACT_OUTSIDE_QUESTION: Specify representative acceptance tests
SECTION_QUESTION_EVIDENCE_INCOMPLETE: Specify representative acceptance tests
SECTION_QUESTION_EVIDENCE_INCOMPLETE: Agree delivery training and support
```

S2 的 CL18/19 使用 E5.F03，超出允许的 E1/E3 与 F2 路由。S4 的 CL32/35 使用 E5.F04，超出 E3/E4/E6 及该章 requirements。S6 只使用 E5/E7，缺少冻结要求的 E2。S1、S3、S5 的 source 集合匹配。这里的 `INCOMPLETE` 也包含 source 集合不相等，不能全解释为某个主题完全没写。详情见 [section-routing-diagnostics.json](section-routing-diagnostics.json)。

CL40 的检测命中原文 **“The RFQ”**。既有算法将不在 first-party 文本中的连续首字母大写词视作竞争者候选。AI 阅读认为此处 RFQ 是询价缩写，未观察到实际竞争者品牌；保留原生拒绝，不据此宣布模型虚构竞争者，也不绕过 Validator。只读诊断在 [competitor-diagnostic.json](competitor-diagnostic.json)。即便不考虑此项，预算及章节路由仍独立失败。

SQLite 保存一条原始 PENDING_REVIEW revision，正文和原始模型 content 一致，decision 为空。PENDING_REVIEW 是留存状态，不等于 Validator PASS 或商业批准。

## 4. 七维 AI 预审

| 维度 | 结论与原文证据 |
|---|---|
| 1. factual accuracy | **直接事实较强，解释仍有过度归纳。**43条直接事实均为准确源句，未观察到造数或新增认证。CL19称“Unloaded ratings and nameplate power describe bench conditions”，其 reasoning 进一步说两者都来自 unloaded bench；资料只把转速定义为空载台架测值，铭牌不是同一种测量，不能合并。CL35、CL49亦需语义审查，详见下文。 |
| 2. limitation preservation | **明显保留，仍不足以保证推理正确。**六条解释逐字包含本章 limitation/action；直接事实保留空载、居中静载、小样本、排除装卸、未覆盖材料、提案非承诺等条件。CL35明确“The samples do not establish production capability.”，没有转为生产保证。但限制句可能只是附在过宽前提后面。 |
| 3. explanation depth | **不足。**50条中43条是事实引文，仅6条解释，解释正文186词，占正文约14.3%。CL7只说“The envelope comparison narrows the shortlist to conditional candidates rather than a settled choice.”，没有自己展开哪个条件排除哪台设备；具体排除结论已在E5原句中。没有完成从参数罗列到充分采购判断分析的转变。 |
| 4. procurement decision value | **局部有用，缺少操作细节。**CL19请求 loaded trial/torque records；CL25提出应用匹配；CL35提醒量测及不确定度程序；CL40要求书面分工。但多是引用后的短提醒，未明确对应哪类应用变化、如何设定试验边界、如何区分铝/钢或怎样完成量测判定。六份 proposal 并不自动等于六段高价值推理。 |
| 5. search intent match | **主题匹配，决策完成度弱。**六章覆盖配置、主轴、材料、验收、采购和交付。读者仍需从长引文中自行提取 shortlist、记录可比性和协议缺口；周期数据被放进验收章，未用于第3章说明完整生产周期与试验周期的边界。未做搜索排名或真实SERP实验。 |
| 6. originality / AI template feeling | **仍强烈模板化。**每章固定“事实若干 → 一条短概括 → limitation → action”，直接复述43份事实句，重复 SYNTHETIC 标记也降低阅读性。部分重复是冻结证据条件造成，但用户已允许筛选必要事实，模型仍全量罗列。相比上一轮，解释词数由236降至186，没有看到多层判断或更丰富的论证形式。 |
| 7. CTA quality | **相比旧契约更具体，相比上一轮退步。**CL50要求 drawing revision、material condition、fixture layout、target cycle、acceptance priorities，能指导询盘；但省去冻结指导及上一轮CTA中的 configuration/delivery inputs。六章内各有动作提示，不能替代文章结尾完整的询盘交接。 |

三处需真人重点审查的解释：

1. **CL19：铭牌与台架条件混同。**引用的 E3.F01/F02 仅界定 nameplate，不建立“来自 unloaded bench”的测量事实。结论“不能据此排名切削能力”合理，但支撑表达不够精确。
2. **CL35：把所有记录和拟议标准概括为不同 methods、fixtures、uncertainty assumptions。**铝件记录与拟议验收均使用 drawing A / fixture A，且均列 assumed uncertainty 0.005 mm；钢件 B 的区别不能自动扩张到整个证据集合。比上一轮“results sit close to criterion”更谨慎，但仍未逐项区分共同条件和差异，泛化本身可能不准确。
3. **CL49：将全部交付/培训/支持/质保统一条件化为 signed configuration。**资料明确 dispatch 起算依赖 deposit 和 signed configuration；其他条款各有适用条件。将全部归到同一个前提，和上一轮一样有扩大解释范围的疑点。

针对用户的核心问题，答案是：**本次展示了“事实 + 采购提醒”，尚未稳定升级为“采购判断分析”。**主轴段虽表达空载不等于切削，并给出试验动作，但关键判断已直接存在于 E5.F03；新解释较短，还混同铭牌与空载测值。应根据这些具体内容判断，不能以 Validator PASS/FAIL 或词数替代质量判断。

## 5. 与历史真实实验的区别

同时保留两个基线：`seo-flash-quality-live-2026-10-12/` 是用户提到的 E refs/proposal 均为0的旧契约实验；本报告父目录是本次之前最近一轮真实 Flash 实验，已产生 E/proposal，但仍失败。不能把旧基线误称为最近一轮。

| 指标 | 旧契约失败 | 上一轮真实 Flash | 本次 frozen-v1 |
|---|---:|---:|---:|
| 合法 E refs claim | 0 | 46 | 49 |
| 解释 / proposal | 0 / 0 | 6 / 6 | 6 / 6 |
| 直接源句 | 0（改写且未绑定E） | 40 | 43 |
| fact_ref绑定 | 0；编辑交叉表不算模型引用 | 40/43 | 43/43 |
| claims / 上限 | 48/48 | 47/48 | **50/48** |
| 解释正文词数 | 无合法解释候选 | 236 | **186** |
| 正文词数 / 含标题heading | 1136 / 1174 | 1274 / 1312 | 1300 / 1338 |
| Parser | PASS | PASS | PASS |
| 完整 Validator | REJECTED | REJECTED | REJECTED |
| 最终商业状态 | NOT_READY | NOT_READY | NOT_READY |

新文章比上一轮总词数增加很少，增加来自补回事实引用，解释反而减少。配置排除写得更泛；验收段换成“不直接互换”的论点，但没有准确展开适用条件；采购段省去了上一轮明确指出 cycle criteria / measurement decision rule 未定的内容；CTA少了配置/交付输入。故不能判定内容质量比上一轮整体提升。相比零E/proposal旧实验，结构契约和可追溯性改善明确，采购指引仅局部改善。

历史原判含当时 Validator 的数值标识符误拒和全fact覆盖规则。当前冻结源码已经与当时不同；不能用9条与历史8条错误的个数排名模型表现。本轮没有修改这些规则，也没有回写历史结论。

## 6. Prompt 改动的影响与比较限制

**可能显著影响结果。**本轮没有修改 frozen-v1 Prompt；但 frozen-v1 与历史两个请求本来就不同。相较旧契约，它去除了四字段/P-only竞争指令，明确五字段、E refs、proposal及规划上下文边界。相较上一轮，它强调定性解释与独立精确数字源句，取消全部fact硬配额，明确每章 source/requirement 路由，并调整写作指导和示例。

这些变化可能解释：旧实验0引用变成有引用、上一轮CL7数字上下文错误本次未出现；但模型没有遵守全量筛选和章节路由要求，不能把变化视作已成功解决。历史与本次客户 sources 和 Plan 完全相同；writing brief 的业务内容相同，仅 snapshot binding 不同；System Prompt、User Material 及部分 Validator 行为不同。[historical-comparison.json](historical-comparison.json)、[prompt-change-comparison.json](prompt-change-comparison.json)、[system-prompt-historical.diff](system-prompt-historical.diff) 留存精确对照。

单次样本无法分离 Prompt、Validator 版本、模型采样/服务端部署等因素，也不能估计稳定遵循率。temperature=0 不是重复输出保证。本次只依据 response 声明的 deepseek-flash，不推断服务端具体权重版本。

## 7. 商业状态与下一步决策建议

**未达到 COMMERCIAL SEO DRAFT READY。**理由分别成立：完整技术契约被拒绝；解释深度与语义准确性仍需审核；材料为 SYNTHETIC TEST-only，且没有真人批准。即便未来某次 Validator 通过，也只说明确定性约束通过，不能自动证明商业可用。

**建议保留 DeepSeek 为候选，但目前不作为商业自动交付默认。**本次确认它能输出合法 E refs 和完整 proposal，也保留许多关键限制；失败还含 RFQ 检测误报，不能据此宣布“模型不行”。与此同时，预算/路由违规与浅层分析是真实观察，不能由低成本掩盖。

**建议下一步决策考虑与至少一个其他模型做受控比较。**需要相同证据、Plan、评价口径与人工盲审，分别评价结构遵循、采购分析、总成本和人工修改量；跨模型差异应只包含必要 API 适配并记录。该建议不是授权，本轮没有调用其他模型、修复或开始下一轮优化。

## 8. 实际验证、文件范围与停止状态

本次只新增当前 `frozen-v1/` 实验子目录内的留存、阅读视图、报告、校验记录及本地实验工具；没有修改 `src/`、`scripts/`、`tests/`、冻结包或既有历史文件。另按授权向固定本机许可账本新增并消费一条记录。

实际执行：

- 冻结完整性预检及执行前/后复核：82个产物、175个源码、六函数摘要及原生请求重建匹配。
- `python -m unittest tests.test_draft_prompt_contract tests.test_flash_draft_replay tests.test_autonomous_interpretation -v`：**37项通过，0 failures/errors**；未运行全套测试。有现有 Starlette/httpx deprecation warning。
- 新建实验工具最初两次只读预检因函数引用名错误失败，随后更正工具名称引用并预检通过；失败均发生于发请求前，没有改变冻结源码，也不是两次模型失败或重试。
- 单次真实请求：原始输出完整留存；原生 Parser PASS、Candidate Validator FAIL，9条诊断，原文入库，无模拟审批及 Finalizer。
- 最终独立核验见 [verification.json](verification.json)，产物哈希清单见 `artifact-sha256.json`。

限制：单一模型样本、合成资料、AI预审、公开文档检索缓存、账单未独立验证，均不能支撑生产成熟度或稳定通过率声明。[human-review.md](human-review.md) 保持真人审核待办。

实验到此停止。没有修复、重试、后续优化、WordPress 请求、部署或 Git 提交；等待下一步决策。
