# 修复后 v3 唯一真实 Flash 质量实验

日期：2026-10-13，Asia/Shanghai。**结论：修复后的 v3 仍不足以产出一篇可按现有契约准入 SEO Agent Web 人审流程的英文商业草稿。** 技术形状和证据呈现明显改善，采购分析仅部分改善；本次候选保持 REJECTED。唯一一次请求已经消费，不再生成。

| 决策 | 本次结果 |
|---|---|
| 技术契约 | **FAIL** |
| 文章质量 | **PARTIALLY_IMPROVED** |
| 人工语义审核 | **PENDING**（没有伪造人审；不表示已进入 Layer 5） |
| 商业草稿 | **NOT_READY** |
| 生产交付 | **NO_GO** |

始终 `semantic_approved=false`，`production_authorized=false`。全部事实仍是 SYNTHETIC / TEST ONLY。没有 WordPress、部署、P1/生产 Gate/Validator/PostgreSQL 改动、commit/push/merge。

## 1. 执行前验证

阅读 AGENTS.md、最新 repair/report.md、next-preflight.json、冻结六文件、新 Prompt/类型契约、实验 workflow、native parser、v3 contract、native inspection、OneShotTransport/有界留存、现有 TEST-only SQLite 许可机制和相关测试。当前工作区大量既有改动全部保留；未要求 clean tree。

| 要求 | 实测结果 |
|---|---|
| 指定 request SHA256 | PASS：`be6b56286855a884ef9cdb69b25892d210ee0577f479651bbbd4cd740a1c81b9` |
| 指定 manifest SHA256 | PASS：`1145fcfa8196b601a72e12e809e5f112ac75e595d14c7519f6aa9874019cae78` |
| Selection/Evidence/Snapshot/Plan | PASS：source_context 严格解码并验证 selection、原生输入、source 版本/quote/位置；领域 hash 对应配置 |
| Prompt/Parser/v3/Validator 版本 | PASS：14 项 manifest 文件逐字节 hash/size；旧来源 artifact 清单亦核对；新 Prompt 从当前 builder 只读重建结果与原文件完全相同 |
| 冻结漂移 | 无；执行前后六文件 hash、manifest 引用均一致 |
| 严格六文件集合 | PASS：只有 request.json、request-body.sha256、experiment-config.json、manifest.json、manifest.sha256、report.md |
| 独立结果目录 | PASS：本目录位于 next-results，与 next-frozen 同级 |
| 新组装器接入 | PASS：使用当前 `assemble_model_v3_output`，Mock 同一输入组装正例通过；真实响应只调用该合法入口 |
| 新请求未消费 | PASS：发送前固定许可账本中没有本 request/manifest/permit；next-results 没有历史 attempt；本 request hash 在历史材料中仅是未执行预检引用 |
| 原始留存可用 | PASS：Mock exact body/content、独占 fsync 写入、本地 ACL、现有重复消费拒绝机制；相关中断/超限测试通过 |

完整证据：[preflight-verification.json](preflight-verification.json)、[retention-selftest.json](retention-selftest.json)、[post-execution-integrity.json](post-execution-integrity.json)。109 个历史文件按 repair/preservation-before.json 再次核验无变化。这里只验证冻结 snapshot 的领域及来源绑定一致性，没有新增客户事实真实性调查或外部原站重抓。

领域绑定：selection `237fb0ac0f5c3d5f88872405868ef080f9ec989138ad1cd9402831c58a1012be`；snapshot `a26579024bfd100c92199e5fb2af8714247b48a2514a803aedddde8cdc438430`；plan `2bdef501ae0eb3e3afb9f232c924bcf81ae3327fa9911b6514f32f1e89105084`；evidence `e38bb8cc65ee824a25696e99012546147ae691c5f438977d8952381331c52500`。这些不是相应文件字节 hash，不混用。

**历史 PACKAGE_FILE_SET：仅以临时副本验证。** 已运行的修复回归把历史六文件复制到 TemporaryDirectory：纯冻结集合通过；外部同级 results 仍通过；内部 results 触发原 `PACKAGE_FILE_SET`。未移动、删除或改写历史真实实验。没有声称历史冻结目录布局冲突已经消失，也没有放宽 helper。

本轮隔离 runner 首次离线探查误将 preservation-after 的摘要当成 hash 映射，触发本地 FileNotFoundError；改为读取 preservation-before 的真实指纹映射后核验通过。该问题发生于许可消费/凭据加载/网络之前，只修正本目录 runner，没有修改任何冻结输入或生产源码，也未隐藏或归因给模型。

## 2. 官方参数、预算与唯一传输

执行前只读核查 [官方 Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)、[thinking 开关](https://api-docs.deepseek.com/guides/thinking_mode/)、[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)。冻结参数均支持：deepseek-flash、temperature=0、thinking disabled、json_object、max_tokens=16384；60 秒、零重试/fallback/redirects 是本地 transport/deadline 设置。json_object 不能替代本项目结构验证。

保守规划采用整个 41,049 request bytes 各按 1 token、另加 2,048 framing tokens，共 43,097 input tokens；全部 cache miss、最大输出、高峰价：

`(43097 × 0.3 + 16384 × 1.2) / 1000000 = USD 0.03258990 < USD 0.05`。

这是有余量的规划场景，不是 tokenizer 的数学上界，也不是服务端硬计费上限。未查询账户余额、未发连接测试或额外模型请求。

复用现有 `WebExperimentLedger` 固定本地 TEST-only 账本，以新 request/manifest 唯一绑定 issue/claim。SQLite `synchronous=FULL`、BEGIN IMMEDIATE 和提交消费完成于 **12:30:10.145628 Asia/Shanghai**，早于凭据加载及 HTTP；消费回执在 [permit-consumed.json](permit-consumed.json)。冻结配置的 FROZEN_NOT_AUTHORIZED/false 历史声明原样保留；本次授权来自当前所有者聊天与独立许可，不回写冻结文件。

使用现有 OneShotTransport 校验 exact endpoint、POST、原始 request bytes 和单次计数；底层 `AsyncHTTPTransport(retries=0, trust_env=False)`，`follow_redirects=False`，HTTP timeout 和整次 deadline 均 60 秒。网络 client 关闭之后才做组装/本地检查。现有 create-only 文件写入防覆盖。失败不会重新 issue、claim 或发送。

## 3. 原始响应与费用

| 项目 | 实测 |
|---|---|
| HTTP POST | **1** |
| HTTP status / finish_reason | **200 / stop** |
| latency | **27.598659 秒**（含凭据加载/传输/留存，不含后续组装） |
| 完整接收结束时间 | 2026-10-13 12:30:37.760393 Asia/Shanghai |
| prompt / completion / total tokens | **10383 / 7615 / 17998** |
| cache hit / miss | **128 / 10255** |
| response body / model content bytes | **35240 / 33192** |
| response SHA256 | `f2ab8d0cccbf387f95e0e680e005a8322458c4c89c4f2b216d75a3f9afa45a9a` |
| model-output SHA256 | `cc48b2887b4ba6a21898eee2b0a97d05bba6b400b6b3ae9e8392557646914eb4` |
| 估算费用 | **USD 0.006107634**；未核对实际账单 |

UTC 04:30 在官方两个高峰时间窗以外，使用非高峰每百万 input hit/miss/output USD 0.003/0.15/0.6：`(128×0.003 + 10255×0.15 + 7615×0.6)/1000000`。usage 非负、prompt=hit+miss、total=prompt+completion，输出未达到 token 上限。没有超时、断线、截断或未知结果。

[response-body.bin](response-body.bin) 保存原 HTTP entity bytes（未压缩）；[model-output.txt](model-output.txt) 与 [model-output.json](model-output.json) 保存 content 的原始 UTF-8 字节，两个文件完全一致。已核对 `choices[0].message.content.encode('utf-8')` 精确等于这些字节。HTTP status、finish、延迟和有界安全信息在 [reception.json](reception.json)，usage/价格计算在 [cost-estimate.json](cost-estimate.json)；请求字节副本为 [request.json](request.json)。没有保存/回显 API key、Authorization header 或 cookie。

## 4. 组装与正式分层结果

新 wire 正确使用 8 个 null：sidecar_hash、candidate_hash、6 个 text_sha256。它们是合法占位，不是旧输出的空字符串。实际调用 `assemble_model_v3_output` **FAIL `V3_CLAIM_BINDING`**。

全篇解释真实顺序为 CL6、CL11、CL16、CL21、CL25、**CL32**。最后 sidecar `$.v3_sidecar.explanations[5].claim_id` 写成 **CL33**，该条是 CTA。组装器先用原生 parser 获取真实 claim 顺序，再拒绝此错误；没有改编号或语义，未返回合法组装 envelope。其在失败前的临时内存 hash 计算结果未作为候选输出保存。

因此**没有 assembled-envelope.json，也没有合法 assembled SHA256**；[assembly-diagnostics.json](assembly-diagnostics.json) 明确记录 assembled_sha256=null。制造一个“修过编号/补哈希”的独立文件将违反授权，故未这样做。原始输出 hash 和拒绝诊断保留。

| 层 | 正式结果 | 精确说明 |
|---|---|---|
| Layer 1 Envelope | **PASS** | 原始 null-hash wire，精确六键、版本、candidate 根形状、权限 false；不等于旧完整 hash 契约已满足 |
| Layer 2 Native Candidate Parser | **PASS** | 原始 candidate 的 change_ref/type/sections/blocks/claims/proposal 可由未改 parser 解析 |
| Layer 3 Explanation Contract v3 | **NOT_RUN** | 合法组装前置失败，没有可提交正式完整哈希检查的 envelope |
| Layer 4 Native Candidate Validator | **NOT_RUN** | Layer 3 未通过 |
| Layer 5 Pending Semantic Review | **NOT_RUN** | 状态 REJECTED；人类审阅本实验报告仍为 PENDING |

[validation-layers.json](validation-layers.json) 是正式记录。组装器这次在 CL 绑定环节退出，未进入其内部 run_offline_v3_experiment。未调用 finalizer、未创建 DraftItem，也未运行生产 Gate。

另外允许的只读诊断把**原始 candidate 的实际 native spec**交给现有 inspect_specification，观察到 **CL16 NUMERIC_CONTEXT_NOT_PRESERVED、CL19 DUPLICATE_CLAIM**。这是 [native-diagnostic-only.json](native-diagnostic-only.json) 的独立诊断，不是 Layer 4 正式准入；没有替换正文、引用、proposal 或构造修复 spec。逐字段 v3 规则对照同样只是诊断，不把尚未 hash 完成的 sidecar 伪装为正式通过。

## 5. 契约统计与被遮蔽错误

| 指标 | 本次 |
|---|---:|
| sections / claims / blocks | **6 / 33 / 12** |
| direct facts / exact quotes | **26 / 26** |
| interpretations / 完整五字段 proposal | **6 / 6** |
| CTA | **1** |
| selected fact refs 唯一数 | **25** |
| 正确章节 selected 集合及 required direct reservations | **6/6** |
| 每节解释数 / 冻结最低数 | **1 / 2**（六节都失败） |
| annotations / 正确指向 interpretation | **6 / 5** |
| 完整 v3 chain | **0** |
| 正文词数（本轮统一正则） | **1267** |

旧问题改善：没有顶层 type；native section/claim 结构正确；所有解释有 proposal；E facts 没填 P/S；8 个输出 hash 全部 null；decision_object / next_decision 是合法字符串；recipient/owner 合法；直接事实和 CTA 恢复；25 个选定事实均在正确章节使用，原句与版本/位置绑定仍可追踪。

**其他独立阻断不因修一个 CL 编号消失：**

- 六节解释都少于冻结下限；block/claim/direct/CTA 上限没有超限，但不能以总量较小替代最低分析要求。
- 六条正文都只含一次 limitation，sidecar.non_applicability 含 boundary_condition + required_limitation（本次两者相同，因此重复），拼接不等于正文，六条均 `V3_BODY_BINDING`。
- 4 条 verification_action 与精确公式不符：S2 的 artifact 已含 `a`，公式前置 `the`，实际省掉了 `the`；S4–S6 使用 “Both parties” 而公式为 “The both parties”。这些是现有公式约束的事实，不表示这种机械措辞本身具有编辑价值。
- CL16 的正文和 proposal.reasoning 改写含 6061-T6 的来源句，违反现行完整数值原句规则。原生检查确证该 claim 失败；两字段独立路径加一条 native claim 诊断是同一类问题，不能算成三条不同 claim。
- E4.F01 在 S3 CL12 和 S4 CL19 以同一直接原句重复；S4 虽选定该 ref，仍不能忽略全篇 duplicate 检查。它本可参与不同的解释，而无需重复相同正文，但本轮不更改模型结果。

逐字段 [contract-diagnostics.json](contract-diagnostics.json)、[violation-paths.md](violation-paths.md) 含全部已识别路径和值/预期；下标零基。28 条诊断记录包含同一规则的字段观察和 native 再确认，不等于 28 个独立根因。没有泛称已穷尽所有语义或未来遮蔽错误。

## 6. 采购质量与 v2 / v3 对比

完整逐节结论与八项问题回答见 [AI 编辑预审](ai-editorial-pre-review.md)，原文见 [英文阅读版](article-reading-view.md)。主要结论是 **PARTIALLY_IMPROVED**：事实呈现和结构变好，实际采购分支/责任链仍不足；S1 新增更强的适配断言；unknown 被统一当 condition_change；S2 虽改为 supplier 提供记录，仍不清楚谁执行缺失试验；S4 没有重复 v2 的不同样本数量错误，但测量判断仍浅；S6 过度合并条款条件。不能因措辞变长、关系字段非空或引用合法就认为推理合格。

历史对比来源为保存的真实 v2 与前次真实 v3，不是 synthetic 正例。结构分层名称在版本间不同，表中明确区分正式/隔离结果。

| 维度 | 真实 v2（10-12） | 前次真实 v3（10-13） | 修复后本次 v3 |
|---|---|---|---|
| sections / claims / blocks | 6 / 33 / 13 | 6 / 19 / 原输出无 native blocks | 6 / 33 / 12 |
| direct / interpretation / CTA | 26 / 6 / 1 | 0 / 19 / 0 | 26 / 6 / 1 |
| 每节解释数 | 各 1，未满足下限 | 2/2/3/3/3/6 | 各 1，未满足下限 |
| proposal | 已有 native proposal | 19 条全部缺失 | 6 条完整 |
| formal / native parser | 响应解释 parser FAIL；隔离 native PASS | Layer 1 FAIL；隔离 native FAIL | Layer 1–2 PASS；合法组装 FAIL |
| hash / enum | v2 无同一 v3 wire | 21 个空 hash；对象类型/recipient 错 | 8 个 null 合法；enum 正确；未合法完成 hash |
| 引用 | selected-only，路由正确 | selected refs/quote 基本正确，E 填进 P/S | selected-only、原句精确、P/S 空；末尾 ID 错误 |
| 解释绑定 | CL33 错指 CTA | 19 个正文与三段对应，但公式等失败 | 再次 CL33 错指 CTA；六条正文与 sidecar 不同 |
| 推理 | S4 错称 different coupon counts | CL1 错附 centered/static；review 缺失记录 | 原句条件保留，supplier 提供材料改善；S1 适配过强、全部 condition_change、试验责任不闭环 |
| 人工工作量 | 解释短、编号错、需改 S4 推理 | 需重建 native/补 proposal/direct/CTA，且全篇语义复核 | 大规模 native 重构需求减少；仍需补至少六条分析、同步六条正文/关系、修 ID/公式/重复，并审全部解释 |

这不是稳定遵循率估计，也不是严格 A/B：同一 synthetic selection/evidence/plan 提供受控背景，但 Prompt 完整性、wire 和 hash 职责一起变化，模型别名也可能随时间变更。没有把改善归因于一个 Prompt 句子；单次结果不能证明模型能力上限。

## 7. 实际验证、文件范围与下一项任务

实际运行（`.venv/Scripts/python.exe`）：

- 隔离 execute_once.py 默认 offline preflight：最终 PASS（首次本地指纹读取脚本错误如上）。Mock 留存/同一输入组装/重复许可消费检查均 PASS，真实 API 调用 0。
- `python -m unittest tests.test_draft_v3_real_output_repair tests.test_draft_explanation_contract_v3 tests.test_draft_contract_v3_experiment tests.test_seo_e_only_retention -v`：**76 tests，15.157 秒，OK**。进程加载现有 socket/DNS guard，禁止外网；包含临时冻结目录布局反例、原历史响应保持拒绝、hash/null/CL/权限/引用/公式/数值/留存中断等检查。日志 [offline-tests.log](offline-tests.log)。
- 唯一真实 execute_once.py --execute-once：POST 1，200/stop；合法组装 FAIL；正式 Layer 1–2 PASS、Layer 3–4 NOT_RUN；没有第二次执行。
- 保存输出的 analyze_readonly.py：完成诊断、费用、原句阅读版和指纹复核；外网 guard 开启，无模型请求。
- **未重跑全量 suite**。最新 repair 报告已知的全量 PACKAGE_FILE_SET 仍是历史布局冲突，不能声称完整 suite 全绿。最终交付前另核对原始字节、冻结/源码指纹、已消费许可与文件清单，见 verification.json。

本轮仅新增 `next-results/20261013-122631-flash/` 下的隔离 runner、离线诊断、报告和结果文件；唯一额外本地状态是现有固定 TEST-only SQLite 许可账本的新消费记录。没有修改仓库生产源码、测试源码、冻结文件或历史实验。

**下一项最值得执行的任务：离线设计并验证一个更小的模型 wire，让 Python 从可信冻结输入构造确定性元数据。** 优先移交 native 固定外壳/章节、全局 CL 编号、直接事实保留位、固定 proposal 问题/限制/行动、哈希及可机械拼接的可见关系文本；模型专注产生有证据约束的采购推理、假设和验证责任。用独立 synthetic 正反例验证，不修复本次被拒绝输出，不放宽 Validator，不追加 v4/v5 复杂合同。本轮只建议，不实施。

理由：本次消除了较多类型/形状错误，却仍失败在重复表达、ID 和最低分析要求；继续堆契约字段不能证明采购价值。当前结构尚未通过，所以不直接启动跨模型对照。未来若简化职责后结构通过而文章仍缺价值，再另行授权更强写作模型的质量对照。本轮没有任何跨模型调用。

**实验到此停止。** 保留风险：synthetic 证据不代表商业事实、AI 审读非人审、费用为估算、未有合法 assembled 产物、尚不能接入生产或正常 Web 候选准入。
