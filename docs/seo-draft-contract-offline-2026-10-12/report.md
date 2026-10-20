# Draft Prompt 契约与采购分析：离线复核及独立冻结

当前渲染的 Prompt 已消除指定历史实验中的 P/S 与 E 竞争指令；合法 Mock 的原生待审链路通过，历史错误响应继续拒绝。**本轮真实模型请求 0、WordPress 请求 0，未签发调用许可；真实遵循率和写作质量均未验证，生产 NO GO。**

工作区进入本轮时已经存在模式化 Prompt、按问题选择结构化事实的原生逻辑、相关测试及多个历史冻结包。本轮保留这些未提交改动，重新审计和实测，不把既有实现、旧 RED 日志或旧完整回归冒充本轮新增成果。实际补修仅为冻结脚本的陈旧覆盖描述和虚构的本轮公开核查记录，新增两项先失败的回归。没有修改生产源码、Parser、Validator、Gate/P1、数据库契约或历史实验。

## A. 根因审计：以真实消息为准

指定审计对象是 [历史 request.json](../seo-flash-quality-live-2026-10-12/request.json)，不是其他后续实验。本轮读取了完整 system/user 两条消息、原始模型 JSON、全部 Validator 错误和原文章；分别无改写提取为 [历史 System](historical-system-prompt.txt) 与 [历史 User](historical-user-material.json)。完整来源、参数和章节均来自 request 的实际 JSON。

| 项目 | 真实发送的片段／位置 | 冲突或写作影响 | 当前处理 |
|---|---|---|---|
| 旧固定结构 | System 第13行：`Every claim is exactly {"text","claim_type","page_refs","source_refs"}` | 与 E 必须增加 customer_refs、解释必须增加 proposal 无法同时成立；旧类型枚举也没有解释类型 | E Prompt 不拼接旧 operation/claim 契约；P/S 模式继续保留 |
| P-only 事实规则 | 第17行：`must cite at least one P page` | E-only 客户事实没有合法 P 数值来源 | E 事实精确 quote + 一条 E ref；结构化任务的 P/S 仅规划上下文 |
| 数值来源 | 第18行：`must appear verbatim in the cited P evidence`；content_points 又给 required P/S refs | 真实客户参数只在 E；旧规则与 E-only 来源相竞争 | E 数值、单位、主体和条件仍按原生 E 校验；User 明示 page_source_role |
| 解释候选 | 第25行：`E CANDIDATE RULE supersedes P-only and claim-type rules for E. Claims add customer_refs.` | 依靠尾部覆盖前部互斥指令；User 有 proposal 说明但不能消除 System 的 exact 四字段要求 | 模式独立说明五个基本字段、解释第六字段及五个 proposal 字段 |
| 短文遗留 | 第23行：`Keep every claim short and lexically grounded in its cited evidence`；末尾又说短/词汇规则不限制 E 分析 | 有互相覆盖的词汇和长度倾向 | 普通 P/S 保留；E 独立使用原生1200字符解释容量，允许多句综合 |
| 枚举倾向 | 第25行：`Cover every fact_ref across facts/premises` | 43条事实容易变成全量引用任务；48 claims 实际封顶，但不能据此证明模型把上限当目标 | 当前结构化事实库按问题选材，章节来源和义务仍必须覆盖；明确容量是上限 |
| 章节写作 | User 有六章 reader_question/explanation_goal；content_points 的类型/来源提示仍是 P/S | 有完整问题地图，但未明确划开规划材料与写作事实权限 | 按真实 source/fact requirement_ids 路由；不能仅按主题近似分配 |
| Schema／优先级 | Parser 接受旧四字段；Validator 按结构化 E 拒绝 | Parser PASS 仅说明兼容形状，不是证据合规 | 保持历史兼容 Parser，拒绝继续发生；没有补 refs 的转换层 |

原代码定位可在保留的 [旧 adapter 源码](../seo-prompt-contract-fix-2026-10-12/baseline-deepseek_content_draft.py.txt) 核查：53行固定四字段、57行 P-only、63行短/词汇要求、95–119行尾部 E Candidate 覆盖、107行全 fact_ref 覆盖。当前 adapter 对应位置是 `_SYSTEM_PROMPT` 51–66行、`_E_SHARED_RULES` 110行、`_e_system_prompt` 127行、`build_system_prompt` 170行。

历史真实输出48条 claims均无 customer_refs，解释/proposal均为0，47条非CTA被 CLAIM_TYPE_CONTRACT 拒绝；有全部六章的解释/问题证据错误。HTTP 200、stop、3387 completion tokens不支持截断归因。历史上“模型输出匹配旧契约”是根因嫌疑证据；**本轮只证明程序可消除竞争指令，没有真实因果实验，不能认定它是全部质量问题的唯一原因。**

未发现本次实际消息要求固定词数或每段固定 Fact→Meaning→Limitation→Action 句型。原来的48/24写的是上限；全事实覆盖和短/词汇规则才是可定位的枚举/浅改写诱因。

## B. 三种模式及 P-only 隔离

选择复用原生 `ContentDraftInput.customer_evidence` 与 `propose_interpretations`，没有新增业务模式状态或行业判定器。

| 模式 | 原生选择条件 | 当前有效契约 |
|---|---|---|
| 普通 P/S | 没有 customer_evidence | 旧四字段claim、原P/S类型及第一方/数值来源规则；System与指定历史请求的E追加段之前逐字相同 |
| 已审核 E | 有customer_evidence，propose_interpretations=False | 五字段直接事实／非事实文字；解释精确复制已审text及有序fact_refs，有已审proposal则精确复制，否则不输出proposal |
| 自主解释 E Candidate | 有customer_evidence，propose_interpretations=True | 五基本字段；新解释类型 EVIDENCE_BASED_INTERPRETATION 加必填proposal；只进入待审候选 |

有结构化facts的E任务只允许E事实/解释及非事实editorial/CTA；P/S和content_points提示是PLANNING_CONTEXT_ONLY。旧式全部没有facts的E输入仍可独立使用合法P/S内容，不能混引E与P/S。P-only TEST通过既有 `run_p_only` 的确定性生成和专用审核/覆盖路径执行，不因E Prompt改造而全局禁止P/S或放宽该路径。

## C. 具体文件、方法与本轮差异

| 文件／方法 | 当前职责与实测情况 | 本轮增量 |
|---|---|---|
| `adapters/deepseek_content_draft.py`：build_system_prompt、_e_system_prompt | 共享安全底座；独立P/S、已审E、候选E规则；四个合法示意claim；Mock捕获实际HTTP请求并对照最终消息 | 保留既有实现，源码不变 |
| `core/content_draft.py`：ContentDraftPrompt.material_json | E/P/S权限投影、覆盖要求、已审proposal完整投影；writing_brief缺省时也保留proposal | 保留既有实现，源码不变 |
| `core/draft_customer_evidence.py`：reference_selection_valid | 当前结构化库允许非空合法子集；旧式/混合quote-only仍全覆盖；不替代单claim或章节验证 | 保留进入本轮时的逻辑，不再改动 |
| `core/draft_candidate_review.py`、DraftItem、finalize_draft_item | 共用当前引用选择规则，其他事实/审核安全保持 | 源码不变 |
| `scripts/accept_draft_prompt_contract.py`：prepare | 原生Mock验收和独立冻结 | 103行起保存结构化/legacy覆盖规则及当前User原文，output-contract与audit共用；185行起改为本轮未做公开核查，checked_at=null |
| `tests/test_draft_prompt_contract_acceptance.py` | 完整链路及冻结包回归 | 增加覆盖指令一致性、不得伪造公开核查两项测试；旧断言均保留 |
| 本报告目录 | 审计、失败/成功日志、独立核验、新冻结包 | 新增；不覆盖任何旧包 |

[独立核验](independent-verification.json)比较2294个会话基线文件：仅上述script/test两个已有文件发生改变；既有生产源码、历史docs、旧冻结及失败输出均未变化。新增的本目录单独留存。

## D. 原生 Schema 一致性

Parser：`workflows/content_draft.py::_parse_claim` 84行起；事实校验：`core/content_draft.py::_validate_claim_evidence` 1555行起；proposal：`core/draft_customer_evidence.py::InterpretationProposal`；章节检查：`article_quality_findings` 1724行起。源码摘要及行号冻结于 [parser-validator-source-summary.json](frozen-v1/parser-validator-source-summary.json)。

| 对象 | 当前实际支持的字段／约束 |
|---|---|
| Draft | 顶层只有draft；NEW_RESOURCE_DRAFT仅change_ref、draft_type、sections；C1绑定真实operation |
| Section／Block | outline_heading精确匹配原六章且顺序一致；PARAGRAPH为kind/claims，BULLET_LIST为kind/items |
| E基本claim | text、claim_type、page_refs、source_refs、customer_refs；E的P/S数组为空 |
| 直接客户事实 | OBSERVED_PRODUCT_FACT，一条有效E fact_ref，完整精确原文，无proposal；不允许将改写文字标为精确事实 |
| 新解释 | EVIDENCE_BASED_INTERPRETATION，1–20个不同的真实premises，增加proposal；正文最多1200字符，候选文字须单空格且无外部空白 |
| proposal | procurement_question、reasoning、assumptions均非空且≤300字符；limitation、procurement_action非空且≤150字符；question等于本章reader_question；限制/动作逐字出现在text中 |
| 非事实文字 | EDITORIAL_TRANSITION或CALL_TO_ACTION，全部refs为空，无proposal/数量/能力或承诺；结构化E transition仍仅两条原生允许句，不能隐藏事实 |
| 容量 | 总48claims/24blocks；每段≤4claims、每章≤4paragraphs、每列表≤6items且item≤220字符；直接事实/普通claim≤300字符；output≤16384tokens |

本轮运行了嵌入示例的原生Parser及claim Validator测试。四例覆盖精确E事实、多事实解释、transition和CTA，另有完整六章Mock通过章节层验证。[schema-examples.json](frozen-v1/schema-examples.json)的E999仅为隔离示意，不属于实际43个允许refs，Prompt明确禁止复制示例ref/正文/question。示例不是预批准分析，也不是可以直接作为真实六章文章提交的完整响应。

Parser为兼容旧JSON允许四字段claim；E安全准入仍由Validator负责。缺少引用不会被从正文猜测补齐，proposal中自签核字段被FIELD_CONTRACT拒绝。

## E. 从事实清单转向采购判断

当前实际System包括：`Use the evidence bank, not a checklist of quotes`、`Structured facts need not all be used`、`Explain how parameters change selection, exclusions or conditional candidates`、`Budgets are ceilings, not quotas. Do not pad or fill claim/token caps.`

写作由goal/search intent/reader_problem和每章reader_question决定。先说明选型排除或条件候选、哪些表面参数仍不能决定适用性、什么资料/试验可以缩小不确定性，再选相关事实。支持多句、多前提解释和不同长度段落，不要求每段重复四步模板或泛化提醒；具体结论所需限定必须保留。自然衔接可在有依据的解释中完成，不扩张无事实transition的原生权限。

数值留在精确事实中，定性采购分析独立引用真实premises；不能从空载转速推出扭矩、试件推出量产精度、少样本推出长期效率，或将拟议条款写成正式承诺。CTA请求图纸版本、材料状态、夹具布局、目标循环和验收重点等相关输入，不能保证应用可完成。此处是写作要求和离线示范，**不是对真实Flash已改善的结论**。

当前原生仍要求各章至少一条直接事实、一条包含brief限制/动作的解释，以及准确的章节来源集合/requirement覆盖。这是保留的准入边界，不等于每段必须采用固定句型；专业相关性和推论充分性最终仍需人工判断。

## F. 安全与兼容边界

错误E ref、P/S替代E、变造quote、数值/单位/型号/主体/条件错配、proposal藏数字、自签核字段、无proposal解释、旧审批绑定漂移、证据不足和超预算继续拒绝。没有改变数字扫描器、原文规则、证据充分性或审核准入。

对本次**实际新Mock**独立检查：候选为PENDING_SEMANTIC_REVIEW；未经审核Finalizer返回INTERPRETATION_PENDING_REVIEW且draft=None；已有明确TEST-only决定回填后的同一正文才通过Finalizer。TEST审核不产生专业真人签名或生产授权。旧P/S、legacy E、P-only TEST、comparison不可用、预算与历史V1 artifact重读均在本轮定向／完整回归范围。

## G. 本轮实际测试及失败记录

| 步骤 | 实际结果／日志 |
|---|---|
| 初始现有相关模块 | 28项，OK；只用于核对工作区已有实现 |
| 新增回归首跑 | 4项中1FAIL/1ERROR；coverage仍是旧string造成类型错误，public记录错误；保留tests-red.txt |
| 修正测试的失败表达后再跑 | 4项中2个预期FAIL；明确断言覆盖结构及核查状态，见[tests-red-confirmed.txt](tests-red-confirmed.txt) |
| 最小脚本修复后 | 30项，7.660秒，OK，exit0，见[tests-green.txt](tests-green.txt) |
| Draft/Evidence/审核/P-only/预算/数字定向 | 197项，42.359秒，OK，见[tests-targeted.txt](tests-targeted.txt) |
| 独立新包原生验收 | exit0，见[offline-acceptance.txt](offline-acceptance.txt)；Mock而非真实模型 |
| 独立只读完整性与准入检查 | PASS，见[independent-verification.json](independent-verification.json) |
| 本轮一次完整回归 | **1901项，458.330秒，OK，exit0**；见[tests-full.txt](tests-full.txt)及[退出码](tests-full-exit-code.txt) |

既有Starlette/httpx弃用提示仍存在；未因它更换依赖。旧模式修复自身的历史RED/修复日志保留在[旧failure-ledger](../seo-prompt-contract-fix-2026-10-12/failure-ledger.md)，它们不是本轮重新执行的失败记录。

实际运行命令（均为本地unittest；没有执行verify_live脚本）：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_draft_prompt_contract tests.test_draft_prompt_contract_acceptance tests.test_flash_prompt_refinement tests.test_flash_draft_replay -v
.\.venv\Scripts\python.exe -m unittest tests.test_deepseek_content_draft_adapter tests.test_content_draft_core tests.test_content_draft_workflow tests.test_evidence_intake tests.test_evidence_backed_article tests.test_autonomous_interpretation tests.test_full_article_budget tests.test_draft_revalidation tests.test_content_draft_review_workflow tests.test_p_only_draft_consumption tests.test_content_draft_table_coordinates tests.test_content_draft_numeric_boundaries tests.test_content_draft_word_boundaries -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
.\.venv\Scripts\python.exe -m scripts.accept_draft_prompt_contract --output-dir docs/seo-draft-contract-offline-2026-10-12/frozen-v1
.\.venv\Scripts\python.exe docs/seo-draft-contract-offline-2026-10-12/verify_offline.py
```

离线场景A：E1-only要求完整采购指南，Evidence Sufficiency BLOCKED，writer=0；F1–F8分别缺配置/夹具、loaded/功率条件、材料循环、测量方法、条件筛选、RFQ/验收、交付服务、版本适用性。E1有空载主轴资料，但不足以回答F2的完整问题，不能按“有一条事实”放行。

场景B：7份SYNTHETIC资料、43facts、六章、输入预写解释0。脚本Mock包含6条精确直接事实、14条多前提候选解释、1条CTA，共21claims/15blocks；段落长度不同，有采购问题、未知、限制和具体动作。Parser→candidate Validator→追加Candidate Review→明确TEST-only复验→SQLite独立Reader→Markdown/Web全部执行。原始输出与REJECT/REQUEST_CHANGES/APPROVE历史均保存，审核后重新走原生Workflow；未把Mock成功解释为模型学习或专业语义证明。

## H. 真实失败对照

| 检查项 | 历史实际结果 | 当前离线证明 |
|---|---|---|
| 最终Prompt模式 | 旧规则+E尾部覆盖 | E Candidate独立契约；当前消息重新渲染并核对 |
| E来源指导 | 有，但与P-only竞争 | 五字段和E-only权限明确；事实目录完整 |
| proposal | 存在说明，实际输出为0 | 原生字段完整，样例兼容；新Mock14条待审 |
| 旧四字段要求 | 混入E任务 | 仅普通P/S模式保留 |
| 写作导向 | 全事实覆盖及短/词汇要求 | 问题优先、必要选材、有边界推理、具体CTA |
| 历史原始JSON | Parser PASS、Validator REJECT | **仍REJECT，48条仍无E引用，无任何修补** |
| 合法新Mock | 历史实验不涉及 | 待审、显式TEST审核、原生复验和留存通过 |

历史request SHA256：`7163ba11207bed8636053ce39779c5fc4d424933b23c3cce22d99295f6573bb9`。

历史response SHA256：`c524233d3ecdb3f244ce7ded84cf035361ce1aa48ccccad63cac7e6d1d05eed2`；model text：`9725b1334f3c7f38a6f2095552597625d6388e6d00fbc309a8281320c2b74840`。本轮核对未变化。

相对于指定历史实验，结构化事实选择逻辑也已在进入本轮前改变。不能把未来差异全部当成单变量Prompt因果效果。本轮未再调整该逻辑，也未重写旧输出使它合格；安全事实检查与章节义务继续验证。

## I. 新独立冻结包与 readiness

唯一新交付包是 [frozen-v1](frozen-v1/readiness.json)，不是任何旧包的覆盖或已消费授权的重试。含原七份SYNTHETIC原文、43facts及offset/version/source映射、原生TEST审核快照、任务/Plan/brief、当前实际System/User/request、输出契约、Parser/Validator摘要、冲突报告、Mock及review历史、SQLite/Markdown/Web、成本/Token不确定性、原响应留存和授权过期方案。

新包Plan和全部customer sources与指定历史输入相等；新隔离TEST快照重新建立绑定，writing_brief只有snapshot_sha256不同，非正文任务变化。[实际User差异](historical-user-material-diff.json)另记录三个契约说明字段的新增/修改。没有改原实验的快照、审核时间或文件。

- [request](frozen-v1/request.FROZEN-NOT-AUTHORIZED.json) SHA256：`9273e145beaacb122e57261294143c1a9df0cd4faba8554a03609c194e86ab0f`。
- 交付bundle SHA256（artifact-sha256.json的摘要）：`ad96bbb5d8fee7d35fee5832d51cea96d65bce607e08e8b9fa09868ed875a9cf`；[82个产物清单](frozen-v1/artifact-sha256.json)。内部原生Web bundle摘要另存readiness，不与交付摘要混用。
- System7968字符、User22861字符、request32751 UTF-8 bytes；未扩大8000字符System上限。
- deepseek-flash、temperature=0、thinking.disabled、json_object、max_tokens=16384；提案一次请求、零retry/fallback、60秒timeout、256KiB响应边界。
- 两条消息字符估算7708–15415 tokens，**不是精确Tokenizer或已证明上界**。保守场景65536输入+16384输出，按未再次核实的历史峰值费率估算USD0.0393216，提案上限USD0.05；实际支出授权USD0。嵌套原生helper旧CNY估算明确标为历史临时假设，不是本包的执行预算或账户限额。
- 本轮没有访问模型服务、查询余额或核查现价/参数公开文档；不猜测当前别名、上下文/输出上限或参数支持。真实预检保持 **BLOCKED_PUBLIC_CONFIGURATION_AND_TOKEN_BOUND_CONFIRMATION**，不能称REAL_REQUEST_READY。
- 准备创建时间2026-10-12 16:21:36 +0800，有效期至2026-10-13 16:21:36 +0800；这不是调用许可。authorization.issued=false、expires_at=null。未来许可提案仅本包一次且10分钟，须由用户另行明确授权；不能复用旧许可。
- 原生审核还有自身的新鲜度条件；包未过24小时不代表审核仍新鲜。执行前必须按现有入口核对当前证据/Plan/审核及源码/hash、公开配置和成本。不满足、过期或有漂移则停止，重新核查/冻结并取得新授权。
- [预检与完整留存方案](frozen-v1/real-request-preflight.json)：原响应bytes、原模型文本、model/finish_reason/usage/cache统计、时间和独立SHA在解析前留存；失败原文不改，超限仅留有界前缀并标明不完整；凭据/headers不落盘。当前仅准备方案，没有执行下一次请求。

## J. 结论与停止条件

- **PROMPT_CONTRACT_CONFLICT_FIXED**：当前实际渲染消息自洽；普通P/S与E独立。
- **OFFLINE_E_CANDIDATE_READY**：合法Mock的原生待审、明确TEST审核、复验和留存链通过。
- **REAL_FLASH_INSTRUCTION_FOLLOWING_UNTESTED**。
- **REAL_WRITING_QUALITY_UNTESTED**。
- **PRODUCTION_NO_GO**。

真实调用配置/Token成本预检仍BLOCKED；没有签发许可。事实安全由Python确定性校验，推论充分性、专业采购价值和真实文章质量仍须后续独立实验与人工判断。本轮在离线交付后停止。
