# SEO Draft Contract v3 REAL FLASH EXPERIMENT

最终状态：**REAL_V3_EXPERIMENT_BLOCKED**。日期：2026-10-13（Asia/Shanghai）。

执行前冻结验证发现缺少冻结的 v3 供应商请求体及其预存 hash；现有 experiment config 仅描述 offline synthetic 实验，未冻结所需模型参数。依照本次“任何不一致立即停止、不得重新冻结”的要求，真实请求路径已停止。没有创建、拼装、发送或重新冻结请求，没有修改 Prompt、Selection、Evidence 或 Contract。

## 1. 请求信息与冻结核验

本次 DeepSeek 请求 **0 次**，未读取凭据。指定参数为 model=deepseek-flash、temperature=0、thinking={type:disabled}、response_format={type:json_object}、max_tokens=16384、timeout=60 秒；这些只是用户要求，未成为已验证的冻结请求。

源包：`docs/seo-draft-contract-v3-integration/`，其 verification.json 状态为 OFFLINE_V3_INTEGRATION_READY。实际核对 artifact-sha256.json 内 **57/57 文件字节 hash 一致**。

| 必查项 | 实际核验结果 |
|---|---|
| Selection hash | PASS：`237fb0ac0f5c3d5f88872405868ef080f9ec989138ad1cd9402831c58a1012be`；原 codec 解码及领域校验通过 |
| Snapshot hash | PASS（既有绑定一致性）：`a26579024bfd100c92199e5fb2af8714247b48a2514a803aedddde8cdc438430`；Selection、输入 evidence、writing brief、config 一致 |
| Plan hash | PASS：重算领域 hash 为 `2bdef501ae0eb3e3afb9f232c924bcf81ae3327fa9911b6514f32f1e89105084` |
| Prompt-v3 hash | PASS：文件字节 SHA256 `d5d06d66a202395847ecd98471cf54cadb00fee8dbd388538f077b33724e2a14`，与既有 manifest 一致 |
| Request body hash | **BLOCKED**：源包没有冻结的供应商 request body，也没有其预存 hash |
| Experiment config | 文件完整性 PASS；**真实请求配置不完整**：缺少六项模型/传输参数，仍为 state=OFFLINE_ONLY、synthetic_only=true、network_allowed=false |

Snapshot 的检查是冻结输入内部绑定核验，没有重建原始 snapshot 或访问站点。另重算完整 evidence digest 与 Selection 一致；Prompt 内嵌 Writer Projection 与独立文件一致。完整记录见 [preflight-verification.json](../seo-draft-contract-v3-flash-quality-live-2026-10-13/preflight-verification.json)。

源包报告已明确 prompt-v3-material 与 writer-projection “不是供应商请求包”。不能把 prompt hash、synthetic envelope hash 或 v2 request hash 代替缺失的 v3 request body hash。用户已授权一次真实调用，当前阻断来自冻结前提缺失，而非重复索要调用授权。

## 2. Token usage

无供应商 usage，记录为 null。请求数为 0；不能把未测量写成模型返回了 0 tokens。

## 3. 费用估算

本次请求费用 USD 0，依据是未发送请求。latency、raw response、response hash、model output 均不存在，execution-summary.json 以 null 明确记录；未创建虚假的响应文件。

## 4. v2 vs v3 比较

| 项目 | v2 历史真实实验（2026-10-12） | v3 本次 |
|---|---|---|
| 真实请求数 | 1 | 0 |
| HTTP / finish_reason | 200 / stop | 未请求 |
| prompt / completion / total tokens | 8593 / 5599 / 14192 | 未测量 |
| 历史费用估算 USD | 0.00464835（引用历史记录，未重新核价） | 0（无请求） |
| 解释结构 | 历史报告记录 6 条均存在边界/验证深度不足 | 无输出，无法比较 |
| 阻断点 | 冻结响应 Parser 拒绝；Validator 未运行 | 请求前冻结验证 |

v2 数据来自 [历史报告](../seo-draft-v2-flash-quality-live-2026-10-12/report.md)、execution-summary.json 与 cost-estimate.json。没有重跑 v2。离线 v3 产物的 12 条 synthetic chains 不是本次真实模型结果，不构成遵循率改善证据。

## 5. 解释遵循率与验证顺序

遵循率 **N/A**，实际评估解释数 **0**。selected_fact_refs、decision_object、采购影响、boundary condition、verification owner、verification artifact 六项均未测量。

Response JSON → Native candidate parser → V3 explanation contract → Native Validator 四层全部 **NOT_RUN_PRE_REQUEST_BLOCK**，因为不存在本次响应。未进入 PENDING_SEMANTIC_REVIEW，未授予 APPROVED 或 PRODUCTION_READY。

## 6. 失败原因与分类

[failure-taxonomy.json](../seo-draft-contract-v3-flash-quality-live-2026-10-13/failure-taxonomy.json) 将本次阻断归入 **A Contract failure，仅限实验冻结输入前提未满足**。这不表示已经观察到模型违反 Explanation Contract v3。

B Instruction following failure 与 C Reasoning quality failure 均未评估；D Parser/Validator issue 未建立，Parser/Validator 未运行。缺失请求包不是模型生成失败，也没有证据说明既有 Validator 存在缺陷。

## 7. 人工审核建议与停止点

请人工确认是否另有已经冻结、可核验的 v3 请求包及其 hash/config。若不存在，需要在后续独立任务中明确处理冻结包准备；本轮不实施、不重新冻结、不自动继续调用。无需针对不存在的模型输出进行语义批准。

`semantic_approved=false`，`production_authorized=false`。未执行重试、fallback、换模型、自动修复、WordPress、发布、部署、Git commit/push。

实际验证仅包括源包 57 项 SHA256、原 Selection codec/validate_selection、Plan/evidence digest、snapshot 绑定、Prompt 与 Writer Projection 一致性及请求/config 缺失检查，执行 exit code 0（核验脚本成功完成不表示实验可执行）。未运行 unittest 或全量 suite，未沿用历史测试结果声称本轮测试通过。

新增文件仅位于本报告目录与 `docs/seo-draft-contract-v3-flash-quality-live-2026-10-13/`；已有源码、测试、冻结包及用户工作区修改保留。已停止，等待项目所有者下一步。
