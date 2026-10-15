# 修复 Prompt 后的唯一一次 DeepSeek Flash 真实质量实验

**技术契约 FAIL；内容质量部分提升；商业交付 NOT_READY。**

本次已实现 E 引用和自主 proposal 的基本输出形状，未重现上一轮全量缺失 E refs；但整篇原生 Candidate Validator 仍拒绝。六条解释通常只是把现有资料重新组合为判断、限制和行动，采购分析深度仍未达到商业文章要求。本报告是 **Codex AI 预审**，不是真人评分、工程验证或生产签核。

## A. 授权与冻结验证

本轮项目所有者明确接受 tokenizer 未精确验证、实际计费与估算不同的风险，并只授权下述三个哈希绑定的一次 SYNTHETIC Flash 实验。授权不扩展到未来包、请求、其他模型或重试。

| 绑定 | 执行前重算结果 |
|---|---|
| Request | `8fd2b8834c9aa50f4ebaeba6229b4a9b01b59d033effa8637cce5ed223428431` |
| 交付 manifest | `e797983c2d20d63b6f57491c377142a57aa05886f58bd8b7abdc27447adb094a` |
| 原生执行 bundle | `e114a55bd2e55c80a3f8b869f9e00d90acdefb4da376837515bb28e75ab4ca01` |

三者均匹配。49 个冻结产物、174 个源码文件、1992 个既有基线文件通过现有 verify_bundle_final.py 核验。准备期截止 2026-10-13 10:50:36+0800，本次在有效期内执行。

System Prompt、User Material、完整 wire bytes、task v1 / Plan v2 / evidence v2 / snapshot revision 3、Writing Brief、7 份 SYNTHETIC 资料、43 facts、六章英文标题和零条预写解释均核对。snapshot SHA256：`ac42f39b6c4b02b1dd25e4cee8556787e8a0a74a6f710d0d5241ab521a2bae58`。

实际请求包含 E CANDIDATE MODE、五字段 claims、proposal 契约和全部 43 个合法 fact_refs，没有上一轮旧四字段/P-only 竞争指令。原生 request builder 重建结果逐字节相同；候选形状与当前 Parser/Validator 契约已由本轮 52 项离线定向测试验证。

本轮读取 [DeepSeek 官方当前价格](https://api-docs.deepseek.com/quick_start/pricing/) 和 [Chat Completion 参数](https://api-docs.deepseek.com/api/create-chat-completion)：deepseek-flash 对应 V4.1-Flash，指定 temperature=0、thinking.disabled、json_object、max_tokens=16384 仍支持。按当前峰值 cache-miss 费率，65536 输入 + 16384 输出的规划场景 USD 0.0393216，小于授权 USD 0.05；这仍是场景估算，没有伪称 tokenizer 精确上界或服务端账单硬限额。

执行使用 final-v2 原生目录的逐字节副本，**没有重新冻结**。原生审核会追加 SQLite check 记录，因此只允许它修改副本里的审计记录；原冻结包保持不变。注入已有 FactsOnlyReviewer，核对精确 supplements、fixture task/Plan、资料日期和原生 assessment 版本/绑定/5分钟新鲜度。reviewer_id 明确为 `SYNTHETIC-DOSSIER-REVIEW-NOT-HUMAN`，不产生真人批准。

固定本机账本执行前没有本次 bundle/request/permit；签发10分钟一次性 TEST permit，通过现有 compose -> FrozenWebGeneration.start -> FrozenWebExecutor -> OneShotTransport 路径持久化消费后发送。留存目录在发送前禁用继承 ACL，仅当前 Windows 账户有访问权限；本轮 icacls 已实查。详情见 [preflight.json](preflight.json)、[execution-summary.json](execution-summary.json)。

## B. 实际请求、usage、费用和延迟

| 项目 | 实测 |
|---|---|
| 真实 POST / retry / fallback / repair | **1 / 0 / 0 / 0** |
| 记录开始 / 完成（北京时间） | 2026-10-12 11:46:19.179156 / 11:46:34.707704 |
| HTTP / finish_reason / 返回 model | **200 / stop / deepseek-flash** |
| prompt / completion / total tokens | **7747 / 4615 / 12362** |
| cache hit / miss | **0 / 7747**；cached_tokens=0 |
| 总处理延迟 | **15.750539 秒**；包括受控启动、HTTP、留存和原生候选检查，未声称是纯推理耗时 |
| 原始响应 / 模型 JSON 文本 | **19147 / 17613 bytes**；完整，无超限或静默截断 |
| 本次峰值费用估算 | **USD 0.0078621** |

发生于周一 UTC 03:46，在官方 01:00–04:00 峰值窗口。计算为 `(7747 × 0.3 + 4615 × 1.2) / 1000000`。同 usage 低峰等价 USD 0.00393105。本轮未查询余额或账单；实际扣款未独立核实。完整 usage 见 [cost-estimate.json](cost-estimate.json)。

## C–D. 原始文章、JSON 和 SHA256

- [真实英文文章全文](article-full.md)：标题来自冻结 Plan，正文每条 claim 原样保留，按原段落排版；未润色、未补引用、未删错误。
- [带 S#/B#/CL# 的全文](article-annotated.md)；[claims 索引](claims-index.json)。
- [原始模型 JSON 文本](model-output.txt)；[完整原始 HTTP response](response-body.bin)；[实际请求 bytes](request.json)。

Response SHA256：`9f69992de2e7a9d0c16a66893a07b72dd39cbb8fe5e538f47ed10378383398db`。

模型 JSON 文本 SHA256：`04c311ca5fc7a85833f3662dd11d21a97aae00cc95a40afe2604dd5e4ba202e0`。

原始 content 与 model-output.txt、rejected-candidate.txt 以及待审 SQLite 记录一致。文章排版文件是只读视图，不替代原始 JSON。

## E–F. Parser、Validator、refs 和 proposals

原生 Parser **PASS**。Candidate Validator **DETERMINISTICALLY_REJECTED**，8 条完整诊断如下：

```text
CL7: NUMERIC_CONTEXT_NOT_PRESERVED
CL19: NUMERIC_NOT_GROUNDED
CUSTOMER_EVIDENCE_COVERAGE
SECTION_EVIDENCE_OUTSIDE_QUESTION: Read spindle and cutting trial evidence
SECTION_FACT_OUTSIDE_QUESTION: Read spindle and cutting trial evidence
SECTION_QUESTION_EVIDENCE_INCOMPLETE: Read spindle and cutting trial evidence
SECTION_FACT_OUTSIDE_QUESTION: Specify representative acceptance tests
SECTION_QUESTION_EVIDENCE_INCOMPLETE: Agree delivery training and support
```

| 统计 | 结果 |
|---|---|
| sections / blocks / claims | 6 / 15 / 47 |
| 有非空且全部合法 customer_refs 的 claims | **46** |
| 不存在的 fact_ref / 错误 P/S claims | **0 / 0** |
| 直接事实 claims / 与引用原文完全相同 | **40 / 40** |
| EVIDENCE_BASED_INTERPRETATION | **6**，每章1条，全部多事实引用 |
| 完整五字段 proposal | **6**；Parser 已接受结构、长度和字段 |
| claim 级无原生错误的解释 | **5**；CL7 不通过数值上下文规则 |
| 完整文章通过 Validator 的解释候选集合 | **0**；整篇拒绝，不能把5条局部通过算作正式准入 |
| 唯一 fact_refs / 原生要求 | **40 / 43** |
| 完全没有合法 E 证据的事实/解释 claims | **0** |
| 合法无引用非事实 claim | **1**，结尾 CTA |

遗漏 `E4.F04`、`E4.F05`、`E5.F04`：两个铝件周期观察及匹配试验/小样本不可排名的条件。这是冻结契约覆盖失败，不是要求凑满48条 claim。

CL7 的“**The 520 kg fixture points to exclusion of NCX7 on the supplied envelope, while the 180 kg fixture keeps both models conditionally in scope.**”引用真实存在的量，但它不是完整原文句；冻结 numeric-context 规则要求新解释中的量只出现在完整引用句中，因此此项拒绝合理。模型可用定性分析，但本次没有遵守该限制。

CL17/18 在第2章引用 `E5.F03`，语义上与主轴采购有关，但冻结该章只允许 F2 / E1、E3，E5.F03 属于其他 requirement。CL25 在第4章使用 F2 的 `E3.F04`，超出该章 F4/F6；第6章冻结 supporting_evidence 包含 E2，但实际只用 E5/E7。详见 [section-routing-diagnostics.json](section-routing-diagnostics.json)。这些是原生路由/覆盖契约不符；不把所有章节位置问题等同于事实造假。

所有 proposal 保有 assumptions、limitation、procurement_action，没有 approval/review_status/signature。新解释全部未获语义批准。现有入口把原文存为 PENDING_REVIEW，但 candidate_state 明确为 DETERMINISTICALLY_REJECTED；外层 error=INTERPRETATION_PENDING_REVIEW 是候选入口的通用停止标记，不能据此声称 Validator 通过。准确结果以 [candidate-validation.json](candidate-validation.json) 为准。

Finalizer **未运行**，没有正式 Draft、没有自动批准新解释。

## G. 与上一轮的统一技术对照

| 维度 | 上次 | 本次 |
|---|---|---|
| JSON Parser | PASS | PASS |
| E 引用完整契约 | FAIL，E绑定0 | FAIL，格式明显改善，但覆盖40/43及章节路由失败 |
| 有合法 E refs 的 claims | 0/48 | 46/47，另1条CTA无需refs |
| 自主解释候选 / proposal | 0 / 0 | 6 / 6；5条局部无错误，全部未审批 |
| Validator | REJECTED | REJECTED |
| 全文词数（同一正则，含标题/heading） | 1174 | 1312 |
| 正文词数（同一正则） | 1136 | 1274 |
| 输入 / 输出 tokens | 7610 / 3387 | 7747 / 4615 |
| 深入采购分析 | 不足 | 有组合分析，但整体仍不足 |
| 采购决策价值 | 有限 | 局部改善，尚不完整 |
| CTA | 偏泛 | 更具体 |

本次同时改变 Prompt 契约和写作指导，即使有提升，也不能分离两者贡献。两次真实样本不能用于估计稳定遵循率。本轮实际模型仍是响应声明的 deepseek-flash，未查询或猜测服务端具体部署版本。

## H. 文章质量：Codex AI 预审

没有真人评分，不自动按词数判断质量。1312词较上次1174词增加约12%，其中40条为证据原文，六条解释正文合计236词。直接引文重复“SYNTHETIC / TEST ONLY”是本案例事实契约结果，也影响阅读；不能据此夸大为更成熟的商业文案。

| 评价维度 | 具体原文、定位与判断 |
|---|---|
| 六章问题回答 | 六章都有判断及行动。CL7给出排除/条件候选，CL18区分空载与切削，CL24说明应用匹配，CL31讨论测量，CL37列出协议缺口，CL46区分拟议条款。但缺少 E4.F04/F05/E5.F04，无法充分回答周期差异/生产节拍采购问题。 |
| 多事实分析 | CL31：“**The coupon results sit close to the proposed criterion while the comparator uncertainty is assumed, so the decision rule and measurement procedure carry the acceptance outcome.**”比上次CL33“Agreeing measurement responsibilities and acceptance criteria…”更明确连接观察、拟议标准及不确定度。这是本轮较有价值的新增组合；但未清楚隔离钢试件、铝件 drawing A 和不同测量方法，须语义审核。 |
| 是否过度列参数 | 第1章12条claim中11条是直接事实，仅CL7解释；CL8–12在判断后继续堆表面/刀库/选配资料。47条里40条原文引用，仍以资料列表为主体，不能认为采购论证充分。 |
| 是否只是改写资料 | 现在直接事实为精确引用，不是轻度改写。六条新proposal主要是资料组合/概括；CL7排除结论已由E5.F01/F02给出，CL18空载不能排名已由E5.F03给出，不能把“有proposal”直接当成新颖深入推理。 |
| 事实对决策的意义 | CL24：“**fit depends on how closely the intended material, geometry, tooling and coolant match those conditions.**”比上次CL25“Matching material, geometry, tooling…”多了适用性判断；但未进一步明确特定几何/工况变化怎样改变试验设计，提升有限。 |
| 观察/适用性/保证边界 | CL13–16保留空载与铭牌限制，CL27–29保留试件/型号范围，CL31明确“**The samples do not establish production capability.**”，CL38–43保留拟议商业条款及排除项。未观察到新增数值、单位转换、认证、真实客户案例或生产保证，但CL19存在原生数值扫描器问题，不能把全篇数字校验说成通过。 |
| 询盘、试验、验收设计 | CL37：“**cycle criteria and the measurement decision rule stay open until both parties agree them in writing.**”比上次仅列拟议条款更明确指出下单前的协议缺口。仍没有展开记录格式、量测判定规则选择或钢/铝适用性区分；采购分析未完整。 |
| 泛化/重复 | 六条解释都采用判断→限制→Send/Request/Submit/Agree/Confirm，且大量出现proposed/conditions/agreement。必要限制有保留，但仍有模板感；第5/6章更多是概括现有条款。 |
| CTA | 本次CL47：“**Send the drawing revision, material condition, fixture layout, target cycle, acceptance priorities and configuration and delivery inputs for a scoped review.**”相比旧CL48“Send the intended application and request applicable records and written commercial terms…”显著具体，能直接指导询盘资料准备。 |
| 不支持/过宽推论 | CL31泛称coupon results接近criterion，把E4.F07钢测量也并入drawing A铝件标准论证，未解释可比性；CL18把nameplate power概括为recorded bench conditions也过于笼统；CL46“**The delivery, training and support items are proposals tied to a signed configuration**”及reasoning将warranty一起条件化，资料仅明确dispatch以签署配置为起点，不能自动扩张到全部条款。这些是AI预审疑点，确定性Validator通过的局部claim也不能自动批准。 |

逐条 proposal 原样见 [interpretation-proposals.json](interpretation-proposals.json)，全文与引用定位见 [article-annotated.md](article-annotated.md)。

## I. 新技术问题与根因优先级

**已复现独立 Validator 缺陷**：CL19逐字等于E4.F01，但 `extract_numeric_expressions` 将 `6061-T6` 拆为 `6061-t` 和 `t6`；whole-token检验随后均返回false，导致 NUMERIC_NOT_GROUNDED。不是模型改写、造数或漏引用。只读诊断保存在 [numeric-diagnostics.json](numeric-diagnostics.json)，本轮没有改Validator。即使未来修复此误拒，其他7条拒绝原因仍成立，本次不会转为通过。

故障不能单一归因于模型。按下一步诊断必要性排序：

1. **其他：Validator标识符缺陷**。精确合法源句也被拒绝，下一步最优先做离线回归复现并修复whole-identifier解析，不扩大准入、也不删除有效安全检查。本轮止于记录。
2. **Schema/映射复杂度**。全部43事实覆盖、章节requirement与supporting_evidence精确集合，以及解释量必须完整原句，是同时存在的严格要求。本次CL7及章节路由说明其仍未被完整执行；应先离线核对事实/章节映射与Prompt对约束的可理解性。
3. **模型指令遵循**。新输出显示基本E/proposal能力，仍漏3事实且未守numeric-context。单样本可确认此次违规，不能确认Flash能力上限。
4. **Prompt/写作指导**。旧四字段冲突已消除，不能继续拿旧冲突解释本轮失败；可读性与证据列表占比、浅层proposal仍有改进空间，但不应先盲目加长Prompt。
5. **Planning**。六章和brief未丢失；F2/F5路由使语义相关E5主轴分析不能进入第2章，F2热身事实不能进入第4章，提示未来需独立检查设计合理性。本轮按冻结规则准确拒绝。
6. **Evidence**。7份资料/43facts全部在输入且有效；未见证据失效或缺少主轴/试验资料。问题在输出覆盖和消费规则，不是资料未送达。

## J–K. 三个独立结论和下一步

1. **技术契约：FAIL。** E refs基本形状和完整proposal均出现，零旧P/S误绑，但整篇未满足覆盖、章节路由及数值上下文要求，另有一项Validator误拒。
2. **内容质量：部分提升。** CL31/37有更明确的组合判断，CL47询盘CTA更具体；主体仍是参数/资料原文列表，缺周期比较，解释深度和适用性边界不足。不能因为更长或proposal数量增加判定成熟。
3. **商业交付：NOT_READY。** 确定性Validator拒绝且AI预审发现推论范围问题。没有可信真人签核，没有生产交付授权，也没有正式Draft。

最有必要的下一步是 **先离线处理已确认的6061-T6误拒，并核对章节事实映射与数值解释约束**，以免下一轮把程序误拒和模型违规混为一谈；之后是否修改Prompt或进行新实验由所有者决定。其他模型值得作为未来受控比较选项，但目前没有证据证明换模型能解决Validator/映射问题，也没有证据证明Flash已到能力上限。不自动换模型或请求额外样本。

## 修改、验证与停止状态

只新增本目录实验runner、精确输入副本、请求/原始响应、原生诊断、全文、AI预审报告。固定本机TEST许可账本新增并消费一条记录。原始冻结包、历史响应、生产源码、P1、PostgreSQL均未修改。

本轮实际执行 **52项相关unittest，0失败、0错误**，详见 [targeted-tests.txt](targeted-tests.txt)。未跑1887项全量回归。测试保留既有Starlette/httpx弃用提示。实验Validator拒绝与单元测试通过分别记录；没有用测试通过掩盖模型结果。

最终完整性、原文SQLite重读、许可消费和ACL检查见 [verification.json](verification.json)。无WordPress、部署、发布、Git写操作、重试、fallback、二次生成、润色或解释批准。本轮已停止，等待项目所有者决定。
