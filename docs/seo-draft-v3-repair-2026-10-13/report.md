# READY_FOR_NEXT_EXPERIMENT

日期：2026-10-13。结论仅表示下一次**另行授权的实验**具备可验证的离线输入和程序路径，不表示真实模型通过、不表示 MVP 完成，更不授予生产或 WordPress 权限。

本轮未请求 DeepSeek，未写入 WordPress、部署、commit 或 push。原真实响应仍为 **REJECTED**。没有删除其多余字段、修补原文、补造 proposal、创建可交付 DraftItem 或批准语义。

## A. 根因及证据

### 证据完整性与层次

读取了原 [实验报告](../seo-draft-contract-v3-flash-preflight/real-v3-experiment-2026-10-13/report.md)、原始 response bytes、model output、冻结 request/manifest、integration Prompt/selection/input、sidecar codec、native parser/validator、fixture 与相关测试。

- 原 response SHA256：`9bf488c5bae70d2f688224595d4e8c5cf8cf90a79cbc8ed501189e8a6e696bca`。
- 原 model output SHA256：`a456ea3f966233e51d06e815796d0427b4391a0f9ba21b0fbbfc22e5179133b4`。
- response 中 `choices[0].message.content` 的 UTF-8 bytes 与保存的 model-output.txt 完全一致。
- 三个历史目录内的 **109 个文件**逐字节 hash 保持不变，包含原六文件、manifest、真实响应及历史材料；见 [前置指纹](preservation-before.json)、[后置复核](preservation-after.json)。

| 检查 | 实际结果 | 解释 |
|---|---|---|
| 正式 Layer 1 | FAIL `V3_EXPERIMENT_ENVELOPE_FIELDS` | 根对象唯一额外字段是 `$.type = "json_object"`；六个必需字段均存在，两个权限字段均为 false |
| 正式 Layer 2–4 | NOT_RUN | 完整保留原准入顺序，没有从正式入口绕过失败 |
| 隔离 Layer 2 | FAIL `UNKNOWN_CHANGE_REFERENCE` | 单独把原 candidate 交给原 parser，缺少 `$.candidate.draft.change_ref`；不修改 candidate |
| 隔离 Layer 3 codec | FAIL `V3_SIDECAR_INVALID` | 原 sidecar 独立解码失败 |
| 隔离 Layer 3 inspector | FAIL `V3_HASH_SHAPE` | 以保留所有原值的 dataclass 诊断视图调用原 inspector；空 hash 最先失败 |
| 隔离 Layer 4 | FAIL | 19 条 `UNKNOWN_SOURCE_REFERENCE`、六节 `SECTION_DIRECT_FACT_MISSING`、`PROCUREMENT_CTA_MISSING` |

Layer 4 无法获得“由原生 parser 成功解析的真实 specification”。因此仅构造**不准入的内存结构视图**：change_ref/type 来自冻结输入，保留原 heading、全部 text/ref、proposal=None，按每段最多四条进行诊断分组。没有生成修复 candidate 或保存为文章。原输出没有 blocks，无法声称其真实 block 布局是否超预算；该视图不证明 Layer 2 或原文 Layer 4 通过。Layer 3 的 typed view 同样不改 hash、枚举或正文。

原检查均为 fail-fast，故另行逐字段检查缺失项、类型、枚举、hash、selected ref/quote、正文公式及保留位。共列出 **271 条字段/规则诊断记录**，部分记录描述同一字段的不同问题，不能当作 271 个独立根因。所有下标为零基；完整路径在 [violation-paths.md](violation-paths.md)，值、预期及逐解释关联在 [diagnosis.json](diagnosis.json)。

### 已确认的责任归属

| 类别 | 证据与判断 | 本次措施 |
|---|---|---|
| Prompt 不完整 | 只说“保持 native schema”，未展示完整 draft/section/block 形状；decision_labels 是映射但未明确必须输出字符串 key，也未显式列 recipient 枚举 | 新 Prompt 给出类型、精确字段集和可由 parser 解析的形状示例 |
| Prompt 内部契约不一致 | writer_projection 沿用 v2 的 `explanation_requirements.fields`，包含 `explanation_claim_id`，外层 v3 却用 `claim_id`；原 hash_creator 仍是 offline synthetic fixture producer | 仅在新 Prompt 的副本内对齐 v3 注释字段，明确 hash 由程序生成；历史 builder/材料不变 |
| 模型未遵循已提供指令 | proposal/直接事实保留位/P-S planning-only/公式/权限边界原本有说明；模型遗漏前四类要求，权限 false 则遵守 | 把遗漏规则集中写明，保留原严格检查；无法仅凭一次输出证明模型必然能遵循新版 |
| 系统组装职责 | SHA256 是确定性计算；原模型空填 21 个输出 hash，而旧实验入口要求这些 hash 已算好 | 单独的 `assemble_model_v3_output` 仅计算新 wire 明确声明为 null 的三个种类 hash |
| Parser/Validator | 对额外字段、错误原生结构、错误引用和空 hash 的拒绝均符合现有规则 | 不修改、不放宽。没有建立“应接受却拒绝”的实现缺陷 |
| 语义质量 | CL1 将台面载荷的 centered/static 条件附着到行程；CL3–4 只要求 review 未产生的试验记录；部分 unknown 与条件变化未区分 | 新指令明确条件归属和待验证责任；真实语义仍须人工审核，程序不能修复或批准 |

根因不是单独的 `$.type`。即使删掉它，原生结构、引用空间、proposal、direct-fact reservations、hash、枚举和实现公式仍各自阻断。没有针对本次响应写字段删除器。

## B. 19 条解释的违规分类

**共同问题，19/19：** native claim 多出 `claim_id`，缺少 `proposal`；`page_refs` 非空且 `source_refs` 填入 E 来源 ID（共 28 个错误来源元素）；`decision_object` 与 `verification.next_decision` 是 `{label: ...}` 对象而非 enum string；`text_sha256` 为空；`non_applicability` 没有按双槽公式同时拼接 boundary_condition 和 section.required_limitation。

**共同正向观察，19/19：** selected_fact_refs / customer_refs / evidence_reference 的集合对应，均限定在本节 selected facts，source_quote 精确一致；三个可见部分拼成 claim.text；owner 合法。它们只证明引用和文本对应，不证明推理成立或 artifact 真实存在。三项输入上下文 hash 与冻结 selection/snapshot/plan 一致。

表中“数字上下文”表示原句含数量且不是任何自身引用证据的完整原句；这是原 proposal 数值上下文规则的独立检查。原始输出缺 proposal，所以不是宣称正式 validator 已经走到该分支。补齐 proposal 后仍不能保留这些改写句；新增反例测试实际验证此拒绝。

| Claim | 节 | 对象显示标签额外问题 | recipient 枚举错误 | 数字上下文问题 | verification 正文公式不符 |
|---|---|---|---|---|---|
| CL1 | S1 | — | — | 是 | 是 |
| CL2 | S1 | — | — | 是 | 是 |
| CL3 | S2 | spindle capability 不在允许标签中 | — | 是 | — |
| CL4 | S2 | spindle capability 不在允许标签中 | — | 是 | — |
| CL5 | S3 | application fit 不在允许标签中 | — | 是 | — |
| CL6 | S3 | application fit 不在允许标签中 | — | 是 | — |
| CL7 | S3 | application fit 不在允许标签中 | — | — | — |
| CL8 | S4 | — | 是 | 是 | 是 |
| CL9 | S4 | — | 是 | 是 | 是 |
| CL10 | S4 | — | 是 | 是 | 是 |
| CL11 | S5 | — | 是 | — | 是 |
| CL12 | S5 | — | 是 | — | 是 |
| CL13 | S5 | — | 是 | — | 是 |
| CL14 | S6 | — | 是 | — | 是 |
| CL15 | S6 | — | 是 | — | 是 |
| CL16 | S6 | — | 是 | 是 | 是 |
| CL17 | S6 | — | 是 | 是 | 是 |
| CL18 | S6 | — | 是 | 是 | 是 |
| CL19 | S6 | — | 是 | 是 | 是 |

所有对象字段本身均类型错误；表中的“—”不表示对象合规。CL3–7 的两个对象字段各有不支持的显示标签，共 10 项额外细节。12 个 recipient 写成 `buyer and supplier`，允许值是 `both parties`。14 条 verification 公式不一致；boundary 公式 19 条不一致，总计 33 项。buyer_implication 仅在使用模型自己的 label 作只读对照时能匹配，不能据此认为原非法对象可以执行 `render_parts`。

其他完整路径摘要：

- `$.candidate.draft.title` 多余，`.change_ref` / `.draft_type` 缺失。
- 每个 `$.candidate.draft.sections[i]` 多出 `.section_id` / `.heading` / `.claims`，缺 `.outline_heading` / `.blocks`。
- `.claims[j].claim_id` 多余、`.proposal` 缺失；全部对应 JSON 下标在逐条清单中列出。
- `$.sidecar_hash`、`$.v3_sidecar.candidate_hash` 及 19 个 `.text_sha256` 为空，共 21 项 hash 错误。
- 六节都缺 required_direct_facts 对应的 OBSERVED_PRODUCT_FACT，末尾也没有 CALL_TO_ACTION。
- 解释数 2/2/3/3/3/6，满足每节至少两条，**19 本身不是上限违规**；现有 explanation_budget 为下限。
- 文本/关系长度未发现超限；数值 token 在按原生方式正规化后的各自证据中可定位，没有另报 NUMERIC_NOT_GROUNDED。但 **13 条改写数字句仍违反更严格的 numeric-context 规则**。历史 “different coupon counts” 错误本次未出现，不代表整体数值安全通过。

原生诊断的第一错误仍会遮蔽 proposal 和 numeric-context 等问题，本报告将直接字段观察、规则检查、隔离调用和正式准入结果分别保留。artifact 非空不证明试验已实施；全部证据依然是 SYNTHETIC / TEST ONLY。

## C. 最小修复及文件差异

只改一个已有源码文件：[draft_contract_v3_experiment.py](../../src/foreign_trade_geo_agent/workflows/draft_contract_v3_experiment.py)。该模块仍是未接入生产 runtime 的实验模块。逐行变化见 [workflow.diff](workflow.diff)，变更前字节单独保存在 workflow-before.txt。

1. 新增 `build_model_prompt_v3_material`，保留历史 `build_prompt_v3_material`。新契约明确各层原生结构、全部 sidecar 字段和类型、可见公式、枚举、proposal、直接事实、CTA、证据引用及字符预算。以拷贝消除 v2/v3 字段命名歧义，不修改输入 projection。`output-contract.json` 是显式类型/字段契约，**不是供应商强制 JSON Schema 模式**；请求仍用 json_object，真正拒绝规则仍在原 codec/parser/validator。
2. 新增 `assemble_model_v3_output`：使用独立 wire 标识 `v3-model-null-output-hashes-1`。仅接受 `sidecar_hash=null`、`candidate_hash=null` 和所有 `text_sha256=null`；缺失、空字符串、旧 hash、0/false 均拒绝。按原生全文章 claim 顺序验证 CL/section 绑定，计算 exact-text hash → canonical candidate hash → canonical complete sidecar hash，再跑未改动的完整离线验证。只在全部通过后返回**单独的 assembled envelope**。
3. 组装不增加/修改证据、quote、refs、decision、proposal、审批或授权；不自动生成 direct facts、CTA 或任何语义字段；输入原文不变。context hashes 必须精确对应冻结输入，不能覆盖错误绑定。没有接通 Writer、最终准入、WordPress 或任何网络路径。

可由程序可靠生成但本次未扩展实现的元数据包括：来自可信输入的 change_ref/draft_type/固定 outline、来源版本与位置、按全篇顺序派生的 ID；未来可以简化模型负担，但这次只落地已证实的输出 hash 职责。证据选择、推理、条件归属、验证角色/目的、proposal.reasoning/assumptions、审批与执行授权不能由 hash 程序伪造。

新增 [诊断脚本](../../scripts/diagnose_v3_real_output.py)、[9 项回归测试](../../tests/test_draft_v3_real_output_repair.py)，以及本目录的报告、预检、日志、合成结果和局部构建/测试脚本。没有修改原六文件、旧 manifest、原 response、核心 Validator 或严格六文件 helper。

### 目录冲突的原因与处理

`verify_package` 检查 `set(directory.iterdir().name) == PACKAGE_NAMES`，目录也算额外条目。历史实验将真实结果放在原冻结目录下面，所以内容 hash 未变仍会触发 `PACKAGE_FILE_SET`。这是布局冲突，不是 hash 变更或模型契约错误。

保留历史布局及证据，保留 helper 拒绝额外条目的规则。新增回归将原六文件复制到临时目录：检查通过；在旁边建立结果目录仍通过；在冻结目录里面建立结果目录必然失败。

后续布局固定为同级 `next-frozen/`（严格六文件）、`next-inputs/`（Prompt/类型契约）、`next-results/<unique-run-id>/`（未来原始响应、hash、组装输出、分层检查）。本轮没有生成 next-results 中的真实实验记录。

## D. 测试结果

详见本目录 `red.log`、`green-first.log`、`focusedfinal.json`、`relatedfinal.json`、`full.json`。按 Verification Before Completion 对实际日志与指纹复核，没有把已知红灯隐藏为全绿。

- 首次 7 项新增测试红灯：32 个失败断言（含 subtest），原因是新 Prompt/组装入口尚未实现；两个现有行为测试已通过。
- 实现后首次 7/7 通过；补充数字上下文反例、旧上下文与非法 JSON 后，最终 **9/9 通过**。
- 相关回归最终 **119 项，0 failure、1 error**；错误为 `tests.test_seo_draft_v3_request_freeze.V3RequestFreezeTests.test_frozen_real_package_matches_deterministic_sources` 的 `PACKAGE_FILE_SET`，即上述历史目录冲突。未删测试、未弱化断言、未搬走历史证据来使其变绿。
- 全量 `unittest discover -s tests -p test_*.py -v` 经外部网络 guard runner 实际运行 **2,041 项，0 failure、1 error、0 skipped**，耗时约 475 秒，唯一错误同上。全量进程在最后两项新增反例及 Prompt 字段对齐/220 字符说明落地前已加载测试模块；最终状态由其后的 119 项相关回归及 9 项最终 focused 回归覆盖。没有宣称最终 2,043 项全量已重跑或完整 suite 全绿。全量中的 Starlette 弃用提示、asyncio 慢任务提示和负面 CLI 参数输出不是额外测试失败。
- 原真实输出回放仍在 Layer 1 拒绝，组装入口也拒绝；没有把历史空 hash 当成新 wire 的 null。
- 显式标记的 [合成结果](synthetic/result.json) 在**同一冻结输入上下文**通过 Layer 1–4：6 节、12 条解释，状态仅 `PENDING_SEMANTIC_REVIEW`，两个批准字段 false。模型 wire 与组装后 envelope 分文件保存；不等同于真实模型生成通过。
- 反例覆盖额外 key、非法对象/recipient、丢失 hash、错误旧 hash、篡改 quote、越界 refs、错误/重复 CL、正文公式不一致、native 多余字段、错误引用空间、direct facts/proposal 缺失、数字改写、旧上下文、重复 JSON key、NaN 及权限字段。
- 外部 socket/DNS guard 用于 related/focused/full Python 测试进程及 Python 子进程；允许本地 loopback fixtures。没有执行任何 live verification 脚本。

诊断开发中曾将未正规化的证据直接传入底层 numeric helper，产生 7 项假阳性；对照原调用链后已改为与 native 相同的 `_normalized_text`，最终无这 7 项。另一次只读探查把 v2 键名误写为 explanation_contract，触发 KeyError；实际键为 explanation_requirements。两者均为本次探查问题，不归因于模型或产品 Validator。

## E. 下一次真实生成的预检条件

[next-preflight.json](next-preflight.json) 和 [next-frozen/manifest.json](next-frozen/manifest.json) 已生成并再次离线复核：

- request SHA256：`be6b56286855a884ef9cdb69b25892d210ee0577f479651bbbd4cd740a1c81b9`。
- manifest SHA256：`1145fcfa8196b601a72e12e809e5f112ac75e595d14c7519f6aa9874019cae78`。
- request 41,049 bytes，Prompt 34,364 bytes，system 4,001 字符，均在现有边界内；14 项文件引用已核验，selected-only 检查通过。
- 原参数保持 flash、temperature=0、thinking disabled、json_object、max_tokens=16384、timeout=60、零重试/fallback/repair。合成 wire 49,808 bytes 小于原真实输出，但这不保证真实输出 token 数或 finish_reason。

真实请求前还必须满足：

1. 用户对**新 request/manifest hash**明确授权；旧一次性授权不能复用。本轮状态一直是 FROZEN_NOT_AUTHORIZED。
2. 重新核验新 manifest、request 字节、源码 hash、selection/plan/evidence/snapshot 绑定和严格六文件集合；有漂移就停止，不能原地重新封印以掩盖漂移。
3. 使用独立结果目录，保留原始 HTTP/body/content bytes、接收指标和 hash；原文永不覆盖。只有完整接收且 finish_reason=stop 才进入后续检查；截断不能补全后伪称模型通过。
4. 明确使用新 wire 组装入口，单独保存组装结果和原文 digest；不能把 null 原文直接当作已完成的旧 envelope，也不能调用此入口修复旧空字符串响应。组装校验后，仍按 envelope → native parser → v3 → native validator → review 顺序记录正式结果。
5. 任一层失败则保留 REJECTED，零重试；成功也只能 pending human review。检查 CL1 条件归属、试验实施/产出责任、unknown/condition_change、数字上下文和真实引用语义。
6. 不执行 WordPress、部署或生产准入。下一次实验通过后再另行评估 MVP 接入；不把测试证据当商业真实性证明。

## F. MVP 剩余阻断项

**仍会阻止英文文章闭环：** 尚无真实模型候选通过全部原生/v3 契约；新版 Prompt 的遵循率未验证；真实推理与验证责任须人工审查；当前样本为 synthetic/test-only；v3 实验路径尚未接入现有文章审核/保存入口。下一次实验是验证这些生成契约修复是否有效的最小步骤，不是生产发布。

**不是本轮必要扩展：** 多供应商调度、自动重试/修复框架、更多模型比较、通用语义裁判、重建证据系统、生产级编排、GEO/AI Visibility 扩展、自动发布，以及只为消除历史布局报错而改写冻结目录。精确边界与 artifact 责任能否支撑采购决策属于人工语义审查，不能用额外非空字段冒充已完成验证。

明确保留的不确定性：无法证明单次失败有多少由 Prompt 歧义、多少由模型能力造成；不能保证下一次成功；没有对供应商计费、真实试验记录或责任主体做外部核验。修复建立在确证的接口缺口和实际失败类型上，没有放宽证据真实性、引用绑定或人工审核要求。
