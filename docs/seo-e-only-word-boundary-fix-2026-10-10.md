# CLAIM_TYPE_CONTRACT 词边界修复与冻结响应离线重放（2026-10-10）

冻结的真实 DeepSeek 输出在修复后通过原生技术契约；文章质量仍为 **NOT_APPROVED**，页面显示 **UNREVIEWED**，没有人工签核或生产授权。生产 **NO-GO**，PostgreSQL **BLOCKED**。

## 原因与最小修改

已读取 `seo-e-only-live-experiment-2026-10-10.md` 及其唯一冻结目录。直接解码原 `native-input.json`，将原 `live-attempt/model-output.txt` 送入原生 `_parse_specification` 与 `finalize_draft_item`，修复前复现 `CLAIM_TYPE_CONTRACT`。历史诊断精确位置为 `draft.sections[1].blocks[1].claims[1].claim_type`，规则为 `EDITORIAL_CTA_FACTUAL_CONTENT`。

`core/content_draft.py::_has_first_party_expression` 对规范化正文执行 `any(marker in folded ...)`，其中 `our ` 命中 `your planned` 的后半部分。相同误判影响句中的 `hour later`、`flour sample`；`model ` 也误中 `remodel planning`，`certification` 误中 `recertification`。裸词 `yourself`、`hour`、`flour` 在旧规则下本来就不命中，回归仍明确覆盖。旧空格边界还漏掉句首 `We`、括号中的独立 `our`/`we`。

本轮源码只在 `src/foreign_trade_geo_agent/core/content_draft.py` 增加编译后的 `\b(?:...)\b` 表达式，并用其替换子串检测。沿用现有标记列表、NFKC、casefold 和空白规范化；对标记去除首尾空格后转义，识别独立词/词组。没有品牌特例、白名单或文章改写，没有修改数值、E-only、引用、授权或生产 Gate。

新增 `tests/test_content_draft_word_boundaries.py`，通过真实 Parser/Finalizer 覆盖 4 个测试方法、61 个子用例：

- 正常第二人称与完整英文单词，包括要求的 `your planned application`、`yourself`、`hour`、`flour`，及有后续单词的句子。
- `our product`、`our team`、现有 `we` 和 certification/warranty/model 等受限标记，分别检查 CTA 与 editorial 类型。
- 句首、标点、大小写、全角、换行与 tab 边界。
- 第二人称不能绕过数值或营销约束。

原有用户未提交改动全部保留。相对真实实验记录的 117 个源码摘要，只有 `core/content_draft.py` 改变；本轮补丁在该文件仅增加 3 行表达式定义并替换 1 行检测。

## 离线重放与证据

唯一输入来自历史冻结目录：

`E:/Codex程序/foreign-trade-geo-agent/.data/seo-e-only-retention-20261010-8a9e98bdbac84c98ad5227c04f051a66/frozen-cb46ddbe19bc4d9bbf6afb8b69c3ae09`

旧 Bundle SHA-256：`106eaa38e82a2802c267a876fad93e81b83171cb458e7a8be80966b1a46042f7`。

原响应 SHA-256：`9d116d00f981a6976e975c9b274aa79ee8b9b41fca97d0d167089689ce66c501`。

原正文 SHA-256：`02f0adc26191daa32dd23fa58387ba814d6ea2e5ef16101253212b769bed0121`。

新结果均位于 `.data/seo-e-only-word-boundary-20261010/result-3/`；此前 `result/` 和 `result-2/` 是重放工具断网桩调试时留下的未完成目录，不作为交付结果。

| 环节 | 实际结果 |
|---|---|
| 原始响应与正文 | response content、model-output、rejected-candidate 逐字节一致；未覆盖任何原文件 |
| Parser | 原生 `_parse_specification` PASS |
| 输入 Validator | 原生解码、模型构造校验及 `stable_content_draft_input_error` PASS |
| Finalizer / Draft 校验 | 原生 `finalize_draft_item` PASS，D1，2 节、5 blocks、12 claims |
| Report Validator | `ContentDraftReport.__post_init__` 及 SQLite 读回后的 `validate_persisted_content_draft_report` PASS |
| SQLite | 新副本保存完整 P/S/Plan/Draft；重新读取与原生 report 相等；独立 run 为 SUCCEEDED，仅表示技术重放成功 |
| 原生 Markdown | `article.md` 包含整篇文章、逐项引用与证据；HTTP 导出与其 5,974 bytes 逐字节一致 |
| P/S/E | CL3 → E1，page_refs/source_refs 为空；其余 10 条背景陈述 → P1/S1；CL12 为无引用 CTA |
| 当前证据绑定 | 冻结 journal 的 latest snapshot SHA、任务/Plan/证据/revision、活动原文及 native scope 全部匹配 |
| 冻结保存 | 86 个原冻结文件 SHA 全部未变，包括历史失败结论与原响应 |
| 审核时间 | 保留 `2026-10-10T09:16:40.177221+00:00`，不刷新 TEST reviewer，不赋予新执行许可 |
| 质量/授权 | NOT_APPROVED / human_signoff=false / production_authorized=false |

E1 原句完整保留：NovaCNC NCX7、7200 rpm、continuously、NOVA-TEST-7、20 C、unloaded bench、only NCX7、not a cutting-load or production guarantee。引用字符区间仍为 `[46, 239]`，证据 v2。P/S 输入不含 NCX7、7200 rpm 或 NOVA-TEST-7，未把 E1 参数重标为 P/S。

Markdown SHA-256：`33f1ca8d478664250d63aaf2076cceaf864de14074d8d103427e710167225ea2`。

重放脚本为本地审计文件 `.data/seo-e-only-word-boundary-20261010/replay.py`。其 network transports 被禁止，socket 仅允许 Windows 事件循环需要的 loopback；TEST reviewer 刷新被显式禁止。它直接验证历史输入，不调用有源码冻结/新审核/新实时授权语义的 live 入口，也不修改该入口的约束。

`diagnostics.json` 的 `mode=LIVE` 仅用于现有工作台识别文章的真实模型来源；同时明确记录 `execution_mode=OFFLINE_REPLAY`、`real_requests=0`、`request_count=0`、`source_status=FAILED`、原失败类别和原响应摘要。原失败结果没有被改写。

## 本地 /mvp 展示

复用现有应用工厂、MVP service、模板、原生 review workflow 与 Markdown renderer，未修改 Web 源码。候选与交互 journal 使用新目录中的副本。

已实际启动 loopback 服务并通过浏览器打开：<http://127.0.0.1:8010/mvp/article>。

`/mvp`、`/mvp/evidence`、`/mvp/article`、`/mvp/article.md` 在进程内及实际 loopback HTTP 检查中均返回 200。浏览器可见完整原文、12 条引用映射、CL3/E1、版本匹配、真实模型来源和 UNREVIEWED；生产按钮 disabled。`POST /mvp/approve` 与 `/mvp/deliver` 均为 404，没有新增批准入口。启动使用 `lifespan=off`，不初始化旧 Demo/Live 服务；仅供本轮现有 MVP 路由展示。

## 验证记录

- 修复前原响应复现：Parser PASS、Finalizer `CLAIM_TYPE_CONTRACT`。
- 新增词边界回归的 RED：4 个方法，17 个子用例失败，exit 1；属于预期缺陷复现。
- 修复后相关回归：`tests.test_content_draft_word_boundaries tests.test_content_draft_claim_type_diagnostic tests.test_content_draft_workflow tests.test_content_draft_numeric_boundaries tests.test_seo_e_only_retention tests.test_seo_e_only_experiment tests.test_web_mvp`，74 项通过，28.586 秒，exit 0。
- 完整回归：`.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`，**1725 项通过，435.832 秒，0 failures / 0 errors，exit 0**；日志 `.data/claim-boundary-full-suite.log`。日志末尾的端口占用/启动提示是 Web 启动测试的预期输出，不是回归失败。
- `git diff --check` 对本轮涉及源码与测试无空白错误；Git 提示现有 LF/CRLF 转换配置。
- 重放工具曾 3 次 exit 1：先将精简 diagnostics usage 与含嵌套字段的原 usage 作了整字典比较；随后断网桩拦截了进程内 TestClient；最后拦截了 Windows asyncio loopback socket。均只修正本地重放工具，未修改原响应或业务校验。最终重放 exit 0。
- 存在已有 Starlette/httpx deprecation warning，未升级测试依赖。

审计文件：`result-3/verification.json`、`source-preservation.json`、`reference-ledger.json`、`content-draft.json`、`history.sqlite3`、`article.md`、`mvp-article.html`、`historical-quality-review.json`。历史 usage 保留用于追溯，不作为本轮新调用或费用记录。

## 尚未解决的 MVP 阻断

本轮只解除词边界造成的技术拒绝。文章仍约 209 词，解释浅且重复，4 句沿用 S1；采购指南质量未获批准。客户证据仍只具 TEST-only 审核，缺少真实人工语义签核和生产执行授权。Web 单次生成及失败/usage 留存交互尚未接入。PostgreSQL 仍 BLOCKED，生产 NO-GO。

没有 DeepSeek/余额请求、重新生成、WordPress、部署、commit、push 或 merge；没有修改生产 Gate、P1 或 PostgreSQL。修复验证后停止。
