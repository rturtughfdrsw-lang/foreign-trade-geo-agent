# Phase 7-A.4 REAL LLM REVALIDATION

**PHASE7A4_REAL_LLM_REVALIDATION_FAIL — TEST FAIL**

首个失败层：**Layer 1 / JSON contract**。本次报告 code：`P7A4_JSON_CONTRACT`；未修改的既有执行器原始 code：`P7A2_JSON_CONTRACT`。

唯一一次 DeepSeek HTTP 请求已完成，HTTP 200，reported model 为 `deepseek-flash`，finish_reason 为 `stop`，未返回 thinking content。Provider envelope 可解析，但其中 message.content 的 article JSON 字符串含未转义的换行符。严格解析在字符位置 87、行 1、列 88 遇到 U+000A，返回 `JSONDecodeError: Invalid control character at`。response_format=json_object 并未保证本次内层 JSON 有效。

已在首个失败层停止。Layer 2 Draft contract、Layer 3 Evidence boundary、Layer 4 Phase3 Editorial Review 均未运行。本次不能确认历史 `P7A2_EDITORIAL_INTERNAL_LANGUAGE_LEAK` 是否消失，也不能标记 PASS。没有修复 JSON、过滤输出、改 prompt、retry 或 fallback。

冻结输入来自原 Phase7A1 READY admission envelope；准备、请求前及最终归档时均通过既有 `require_ready(input, result)` 重算。A.1 artifact/implementation hashes 与 A.3 artifact hashes 已核对。prompt.json 与 Phase7A3 prompt.json 完全一致。请求直接由 A.3 messages 和以下冻结参数构造，没有使用 A.2 prompt/request 或旧 article 作为输入。A.3 冻结 user message 内保留的历史 `Phase 7-A.2 TEST ONLY` 标签未修改，以保持变量一致。

参数：model=deepseek-flash；temperature=0；thinking={type: disabled}；response_format={type: json_object}；max_tokens=3000。既有单次 transport 限制、零 retry、禁止 redirect、持久化 attempt-consumed 标记均生效。本次通过 stdin 调用既有 experiment.py 的验证/执行函数，仅将输出目录指定为 A.4；未编辑任何代码或历史文件。

延迟：5.594 秒。usage：prompt_tokens=3571，completion_tokens=579，total_tokens=4150；cache hit=128，cache miss=3443。完整 usage 保存在 usage.json 和 response-metadata.json。

原始 provider 响应保存在 response.raw.json；未经修改的模型 content 保存在 model-response.txt。由于 Layer 1 失败，未启用宽松解析或提取 article.md，article-status.json 记录这一状态。validation-result.json、failure-logs.json、editorial-review-status.json、request-metadata.json、frozen-manifest.json 和 artifact-manifest.json 记录失败、停点、参数及 SHA256。

实际验证：准备阶段在 OfflineGuard、真实 HTTP 禁用和生产 Writer/WordPress guard 下运行了既有单次实验回归 10 项、A.1 admission 26 项、Phase3 editorial 26 项，共 62 项，0 failures、0 errors、0 skipped、0 network attempts；日志为 offline-tests.log/json。没有运行全仓库套件。请求后的检查仅复核 Layer 1 错误、冻结哈希和文件保留状态，不运行后续验收层。当前仓库与原 Phase6 工作区的既有代码/测试/docs 文件清单及 Git HEAD 前后相同；A.2、A.3 历史 artifact 保持原样。只新增 docs/real-llm-draft-phase7a4/ 内的实验数据和报告。

`semantic_approved=false`、`production_authorized=false`、已保存 envelope 的 `live_execution_authorized=false` 均未改变。本次用户单独授权仅覆盖一次 TEST ONLY 请求。失败结果不构成生产或发布许可。

```yaml
real_api_calls: 1
production_writer_calls: 0
wordpress_calls: 0
deployment: false
git_commit: false
git_push: false
```
