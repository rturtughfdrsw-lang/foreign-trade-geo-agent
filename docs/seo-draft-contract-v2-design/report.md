# SEO draft contract v2：离线设计

日期：2026-10-12（北京时间）。状态：**DESIGN ONLY / TEST ONLY / NOT AUTHORIZED FOR LIVE**。

本轮目标是采购决策价值，不是 fact coverage 最大化。只分析本地 frozen-v1，新增离线 Mock；不改生产代码、Gate、原始实验文件，不调用模型/网络、不触碰 WordPress、不提交、不部署。此文、Mock 和 AI 阅读均不构成人类审核或工程批准。

## A. 当前问题根因

### A1. 可以确认的证据与不能确认的动机

基线是 [frozen-v1 原文](../seo-flash-contract-quality-live-2026-10-12/frozen-v1/model-output.txt)，SHA256 `880c9ab66f4380fe34cabf6bf4aeacf8afe5b968049950931d0a6126f3bb2747`，不是父目录的上一轮 Flash，也不是早期零 E 引用实验。

实测 6 sections、16 blocks、50 claims = 43 直接事实 + 6 解释 + 1 CTA；43/43 facts 被使用，P/S 错引为零，解释正文只有 186/1300 词（约14.3%）。[原始指标](../seo-flash-contract-quality-live-2026-10-12/frozen-v1/metrics.json)和[原生拒绝](../seo-flash-contract-quality-live-2026-10-12/frozen-v1/candidate-validation.json)区分了单条引用有效与整稿准入。

**没有“必须全部覆盖43条”的冻结指令。** [冻结 System Prompt](../seo-draft-contract-offline-2026-10-12/frozen-v1/system-prompt.txt)明确说 `Structured facts need not all be used.`；[User Material](../seo-draft-contract-offline-2026-10-12/frozen-v1/user-material.json)也写了 `the fact bank is not an all-ref quota`。不得把更早版本的全fact配额误归到本次输入。模型为什么做出选择无法直接观察；以下是与原文一致、仍需控制变量实验的解释。

| 输入层 | 实际内容 | 可能造成的倾向及证据边界 |
|---|---|---|
| 全局预算 | 48 claims、24 blocks 是尾部上限，未分配事实/解释/CTA份额 | 没有先做算术分配；全部事实逐条抄写后，加六章解释和CTA恰好50。无法从一次响应证明模型内部如何计算。 |
| E Candidate | 直接事实必须完整精确引用；新数量句被严格限制；演示是短事实加短解释 | 抄写是容易满足的局部目标；解释较难。43条精确复制与6条短解释支持这种倾向，但契约没有要求每个解释前提另起一个直接事实claim。 |
| coverage/routing | 每章至少一条直接事实、至少一条含固定limitation/action的解释；source集合须相等、requirements须覆盖 | “每source都要出现”可能被扩大为“每fact都要出现”。合法约束需要正向fact选择表，而不是取消证据边界。 |
| writing brief | 回答每个reader question，涉及配置、主轴、应用、量测、采购、交付；背景简短 | 没有要求覆盖全部facts，但问题/目标宽、缺少排除清单及边际价值排序。S2放入所有相关转速内容、S4放入所有相关试验内容，符合按主题堆积的现象。 |
| 解释要求 | 含limitation/action原句、proposal五字段；允许多句，但没有正文中的采购影响/失效条件/验证步骤要求 | 模型可以用一句概括加两句固定提示满足浅层结构。proposal有字段不代表正文完成论证。 |

43 facts + 每章1解释 + CTA = 50，已数学不可行；即便将claim cap放宽，解释深度与路由问题仍存在。因此不建议提高48上限或压缩两条事实以“修好”这一稿。

### A2. 路由失败不是未知引用

| 章节 | 实际错误 | 机制 |
|---|---|---|
| S2，F2，E1/E3 | CL18/19 使用 E5.F03 | 句子确实谈空载转速，但fact标记F5；主题相关不等于该章授权。 |
| S4，F4/F6，E3/E4/E6 | CL32/35 使用 E5.F04 | 句子谈匹配试验，但标记F5；把应用选择的提醒借到验收章。 |
| S6，F7/F8，E2/E5/E7 | 缺 E2 | 全文已在其他章使用E2，不能替代S6本章要求。 |

[逐章诊断](../seo-flash-contract-quality-live-2026-10-12/frozen-v1/section-routing-diagnostics.json)显示额外source与缺失source都可能触发 `SECTION_QUESTION_EVIDENCE_INCOMPLETE`。只告诉模型“只能用这些source”解决不了该source内哪些facts符合本章，也不能保证必需source出现。

本次还含独立拒绝 `CL40: COMPETITOR_MENTION`（原文“The RFQ”）；AI认为可能误报，但本轮保留它，不改Gate、不宣称已修复。解释还存在铭牌与空载台架混同、把全部量测条件概括为不同、把所有商业条款归于签署配置等语义疑点，见[旧稿AI预审](../seo-flash-contract-quality-live-2026-10-12/frozen-v1/human-review.md)。限制语不能补救错误推理。

## B. 是否需要换模型

**现在没有足够证据要求换模型。** 单次 frozen-v1 已证明该输入下能遵循 E refs、精确引用及 proposal 形状，但没有证明预算、逐章选择和深入推理的稳定性。主问题优先在契约中消除；先用相同模型、同份证据做受控实验，再决定是否值得做模型比较。本轮不访问模型文档、不比较实时价格或声称其他型号更强。

可选方案：①仅加Prompt“少用facts”，成本低但仍让模型同时选材和写作；②**推荐：生成前锁定section evidence budget，原生输出形状保留，增加独立解释设计检查**；③改为逐章多次调用，隔离更强但增加调用/合并/重复检测复杂度，当前不采用。v2并非增加一个自主Agent或扩展GEO分支。

## C. Contract v2设计

### C1. 优化目标与 fact priority

`maximize procurement decision value; subject to total claims <=48, total blocks <=24`。价值不是可被Validator证明的真实效用；排序是可审查的编辑启发式。

对候选fact记录：适用问题、改变哪项采购决策、错误使用风险、可验证性、新增信息、冗余、直接引用长度成本。可采用0–3分的固定人工评分：`value = 3*decision_impact + 3*misuse_risk + 2*actionability + novelty - 2*redundancy`；这不是模型自动给自己的质量分。先做routing/证据有效性过滤，再排序；同分按fact_ref固定排序。无需新库或复杂优化器。

优先级：P0＝本章决策必需/防止错误推广/必要source及requirement的最小见证；P1＝能回答另一采购分支的可选事实；P2＝重复参数、工艺细节或对当前问题没有边际价值，默认省略。P0不是“全部高风险facts”；解释某结论时，其关键前提与限制须一并进入选集，否则该结论不得写。若缺少关键证据，报告未决验证，不能补造事实。

`required_facts` 表示必须被本章真实使用的前提；`required_direct_facts` 是其中必须原样单独显示的子集。解释可引用已验证前提而不再复制为直接claim。跨章同一fact可作各自相关解释的前提，但相同直接引文只显示一次，遵守现有全文去重。

**生成前冻结选择，生成时不自行加facts。** Planner先从required+optional挑选 `selected_facts`；Writer只能用selected。optional没选就不写，不扣覆盖分。每个省略项在本地selection artifact记录理由；不要求把省略理由加入文章或模型输出。预算不够先删P2/P1，不删必要条件/验收边界；P0本身超预算或路由不可满足则停止，回到Plan审查，不能硬写。

### C2. 本次合成材料的逐章预算

完整、可执行的本地草案见 [contract-v2.json](contract-v2.json)。表内required是当前问题集的设计选择，不是所有行业的固定必选事实。

| 章节 | required facts（包含解释前提） | optional facts，未选不输出 | 本例直接claim数 / 解释数 / block上限 |
|---|---|---|---|
| S1 | E2.F01/F03/F05/F07，E5.F01 | E2.F02/F06，E5.F02 | 5 / 2 / 4 |
| S2 | E1.F01，E3.F01/F02/F03 | E3.F04 | 4 / 2 / 3 |
| S3 | E4.F01/F04/F05/F08 | E4.F02/F03/F06 | 4 / 2 / 3 |
| S4 | E3.F05/F07，E4.F01，E6.F03 | E3.F06，E4.F07，E6.F02 | 3 / 2 / 3 |
| S5 | E6.F01/F04/F05 | E6.F06 | 3 / 2 / 3 |
| S6 | E2.F09，E5.F05，E7.F01/F03/F04/F05 | E7.F02/F06/F07 | 6 / 2 / 4 |

S4的E4.F01作为解释前提，不重复S3的直接引文；S6显式分配E2.F09，避免全文覆盖冒充本章覆盖。E5.F03/F04在这个固定问题集中默认省略；S2/S4可从本章原始记录推理，不借用越界提醒。如果未来确有必要移入，必须在生成前人工修订问题/requirement/source映射并重验证，禁止Writer或校验后自动重标facts。

本例25个不同facts、26次章节required分配、25个直接claims、12个解释、1个CTA＝**38 claims、20 blocks**。全量fact coverage为25/43，这不是退步指标。优先验证问题是否回答、必要限制是否保留、选中前提是否真正支持结论。未选择的18个facts无需补齐。

预算策略：直接事实最多30条；解释固定预留12条（每章2条不同决策单元）；CTA预留1条；transition默认0。软目标≤43 claims、≤20 blocks，硬上限保持48/24，保留5 claims和4 blocks余量；不是鼓励用满余量。直接事实预算按**出现次数**计算，独立fact数量不是claim数量。解释引用多个facts仍只算一个claim，不能把多个不相关决策塞进一个巨大claim逃预算；每条解释聚焦一个采购判断。

### C3. section routing contract

建议在Plan导出的写作预算artifact里增加每章：`section_id`、原heading/question、`requirement_ids`、`required_sources`、`required_facts`、`optional_facts`、`selected_facts`、`required_direct_facts`、claim/block预算、解释任务。该artifact绑定evidence snapshot、Plan输入hash和版本；Writer不能重分配。

预检不靠模型承诺：selected必须来自required∪optional、required必须已选；每个fact的source在本章required_sources中，fact.requirement_ids与本章requirements相交；required的source集合等于本章supporting_evidence，并覆盖全部requirements；所有限额合计可行。这样能在调用前发现无法完成的Plan。

生成时为每章提供**正向fact allowlist及原句/边界**，将全库移到规划侧；如本轮为可比较性仍保留全库，也必须把section selected list放在显著位置。不得同时保留一个暗示全库覆盖的竞争清单。路由检查包括直接facts和解释的全部premises；“至少一个引用在本章合法”不足以通过。

现有source集合相等和requirement覆盖规则保留。v2新增逐fact分配是更严格的生成计划，不是放松“只能使用source”。对optional被Planner选中后，required_sources仍须相等；不能顺手扩大source。

### C4. explanation contract

每条解释必须在**读者可见正文**回答三个问题，不能只写在proposal.reasoning里：

1. **buyer implication**：这组前提如何改变候选排除、试验设计、验收判定或合同责任？写明决策对象和因果连接，不只是“很重要”。
2. **non applicability**：当什么材料/几何/负载/配置/量测/合同条件变化时，这个推论不再适用？区分未知与已证明失败，不能把无证据写成否定事实。
3. **verification action**：谁要提供/核对什么记录或输入；以什么条件进行复核；结果进入哪个下一步决策？未约定的判定标准要先协商，不能凭空生成阈值或承诺。

每章两个不同问题侧面的解释，而不是同一提醒改写两遍。每条三部分建议总60–160英文词、≤1200字符；本地Mock检查设三部分最低20/12/20词（只作反模板的结构代理）。保留原生proposal五字段和现有各自字符上限；非适用条件写在正文并在assumptions/limitation保持一致。数值留在完整精确事实句，解释定性，不计算新数值/排名。

正文同时逐字包含本章固定limitation/action；固定句只是最低边界，不是完整解释。更具体的采购影响、非适用条件、验证记录必须另写。禁止“加限制语即可抵消过度推理”。本例专门区分铭牌与台架、相同试验条件与未测特性、dispatch触发条件与各自支持/质保条件。

**输出形状兼容优先：** `mock-response.json`保持现有五字段claim和五字段proposal，不向生产JSON塞新字段。三部分在 [explanation-annotations.json](explanation-annotations.json)中绑定claim位置、正文hash和candidate hash；正文由三部分按顺序组成。该sidecar仅用于本轮可验证设计，不是由Parser自动生成的批准信息。未来若要把三字段变成正式domain contract，需单独批准版本化schema和迁移；本轮不做。

词数/字段/出现位置通过，只能表示 **EXPLANATION_STRUCTURE_PASS**。因果是否成立、失效条件是否准确、动作是否可执行、前提是否相关仍需语义审核。不得用模板标签、长文本或自报PASS替代这些判断。

## D. Prompt修改建议

可供下一轮审阅的文本在 [prompt-v2-proposal.md](prompt-v2-proposal.md)，不是已接入的生产Prompt。关键改动：

- 开头直接宣布目标和预算分配：不是全量fact覆盖；先保留解释/CTA；不得用满claims当成功。
- Writer只接受已冻结selected_facts；给出S1…S6正向表、required direct与解释premise的区别。显式指出E5.F03不能放S2、E5.F04不能放S4、S6必须使用E2.F09。
- 保留精确事实、P/S规划上下文、数值/版本/offset/snapshot、去重、未审核proposal和人审边界；删除容易暗示“每个前提必须再抄一遍”的示例安排，不取消精确引用规则。
- 示例用“决策影响→条件失效→验证动作”的完整段落，演示同一前提可进入解释而无需重复直接quote；示例refs不得复制到正文。
- 提交前自计claim/block及检查每章selected覆盖。模型自查是辅助，Parser/Validator仍独立验证；本轮不自动修复旧失败稿，不做二次生成。

## E. Validator是否需要修改

**本轮不需要、也没有修改生产Validator/Gate。** 原生Validator已能拒绝50 claims、越界E5与S6缺E2；直接使用它做新样例的兼容性检查。

正式采用v2时建议新增独立的Plan budget预检和candidate selection/解释结构诊断，优先放在现有review流程的provider-independent边界：新contract应是core数据合同；流程只调用ports；adapters负责传输；runtime装配；storage保留版本和hash。不必为本次设计重构这些层。

需要新增的检查是selected-fact白名单、required/direct履行、解释三部分正文绑定、预留预算和sidecar版本/snapshot绑定；这些不能由现有limitation/action包含检查推断。若正式输出增加三字段，需Parser/序列化/core及相应tests共同版本化；仅增加Prompt不等于解释深度Gate已实现。

仍保持fail-closed、全文去重、精确facts、数字主体/条件保留、全部前提引用、每章source相等、requirement覆盖、人工审核与create-only/draft-only交付边界。不能把semantic pending改为approval。RFQ疑似误报另开独立离线问题；不与本次预算设计混修。

### E1. 离线 Mock及其证明范围

[offline_mock.py](offline_mock.py)只读历史输入/原文，使用现有Parser/Validator；新增checks完全位于设计目录。没有模型client、HTTP transport、WordPress或历史SQLite写入，也不执行旧实验run脚本。负例从新样例复制到内存修改，不修补历史失败响应。

运行方式及最终结果见 [verification.json](verification.json) 和 [verification.log](verification.log)。测试覆盖原始frozen-v1继续拒绝、合法新样例、49 claims、25 blocks、S2/S4越界、S6缺E2、required缺失、非法optional、selected覆盖、三部分缺漏/空话/正文不绑定、数值篡改、P/S替代、snapshot/hash不匹配、proposal缺失、重复文本及网络禁止。

实际执行：`.\.venv\Scripts\python.exe docs/seo-draft-contract-v2-design/run_verification.py`（本轮另传本地起始hash快照用于保留检查）；内部使用标准库 `unittest discover -s docs/seo-draft-contract-v2-design -p test_offline_mock.py -v`。**27项测试全部通过，退出码0；本轮测试没有失败，未运行全套测试。**

| 检查 | 观察结果 |
|---|---|
| 原始frozen-v1 | 原bytes/hash保留，仍为DETERMINISTICALLY_REJECTED，含CLAIM_BUDGET及S2/S4/S6路由拒绝 |
| 新样例 | 25直接事实 + 12解释 + 1 CTA = 38 claims；20 blocks；原生errors为空，PENDING_SEMANTIC_REVIEW |
| section routing | 六章全部PASS；每章所有前提合法，source集合相等，selected/required覆盖 |
| explanation contract | 12条三部分正文绑定、长度/边界检查PASS；语义仍待人审 |
| 浅解释独立负例 | 固定limitation/action保留且原生可进入语义待审，新增深度代理仍拒绝；不是仅靠正文hash不匹配拒绝 |
| 外部动作 | socket/DNS防护下网络尝试0、真实API调用0、WordPress调用0 |
| 既有文件保留 | 2,433个起始文件hash未变；新增内容仅在本目录 |

新例全文可读视图：[mock-article.md](mock-article.md)。43个facts的P0/P1/P2与18个省略理由均保存在contract-v2.json；未把“省略”误表述为源网站缺失。

新样例的claims、routing与explanation结构PASS，不证明模型会生成同样质量。原生新样例预期状态为 `PENDING_SEMANTIC_REVIEW`；人工审核、生产授权、正式Draft和商业可交付均未完成。精确实测值以verification.json为准；本报告的38/20预算不是用历史数值冒充实测。

## F. 下一次真实实验是否值得

**值得，但先完成v2契约审阅和可消费的冻结输入；本轮到设计停止，未授权下一次调用。** 推荐继续同一个Flash与同一合成证据/六章问题，只改选择表、解释预算和示例，冻结差异及hash。它能检验这组contract修改是否改善结果；一次同时修改多个相关项不能证明每个单项的因果贡献。

未来成功条件预先固定：原生Parser/Validator PASS；claims≤48、blocks≤24（软目标43/20）；逐章required/selected/source/requirement PASS；12条解释均有三部分正文；没有数字/承诺扩大；语义审核确认具体采购影响、准确失效条件和可执行验证动作；结尾CTA含图纸、材料、夹具、周期、验收及配置/交付输入。全库coverage不作为排名指标。

若再次只失败预算/路由，优先查Plan与Writer接口是否真的传递锁定表；若结构通过但解释仍泛化，先标注是哪条因果/适用条件错误，再考虑经授权的对照模型实验。任何真实调用、次数、费用、持久化范围都需届时具体授权；不继承frozen-v1已消费许可，不自动重试、不发布。

完成范围：新增本目录设计与离线Mock。限制：合成材料、手工构造的正例、结构代理不能自动证明语义质量；未实施生产v2、未测真实模型稳定性、未运行全套测试。现有工作区所有改动须保留。
