# E-only 首篇模型文章实验：离线预检

2026-10-10，Asia/Shanghai。**READY 仅代表离线实验链路和冻结请求就绪。真实 DeepSeek 请求为 0；真实文章质量 NOT_TESTED。** Mock 是手写响应，文章仍为 UNREVIEWED。生产 NO-GO、P1 原状、PostgreSQL BLOCKED。没有读取真实凭据、访问客户网站、写入 WordPress、部署或进行 Git 历史操作。

## 已实现的最小链路

新增 `scripts/prepare_seo_e_only_experiment.py`，复用既有 NovaCNC E-only Intake/TEST reviewer、原生 `CREATE_NEW_RESOURCE`、DeepSeek system prompt 与 request payload builder、Parser、Validator/Finalizer、SQLite 和 Markdown Review。复用 `prepare_seo_article_experiment.py` 的精确字节单请求 transport、独占 live attempt、60 秒期限、流式响应上限和净化诊断；只增加独立实验的校验/持久化参数，默认 P/S 行为不变。实验入口不被生产 runtime、CLI 或 Web 调用。

唯一客户产品事实来自 E1：SYNTHETIC NovaCNC NCX7，7200 rpm 连续额定，NOVA-TEST-7 protocol，20 C unloaded bench，仅适用 NCX7，不构成 cutting-load 或 production guarantee。模型必须原生输出完整原文及 `customer_refs:["E1"]`，不附加伪造的 P/S 支持。NCX7、7200 rpm、NOVA-TEST-7 均不在 P/S。P/S 只提供通用采购背景。缺失 E1、未知引用、数值改动、限定删改均拒绝；没有改动数值验证器、core 模型或生产 Gate。

初始离线准备仍使用既有固定 fixture；准备时另按实际 UTC 时间核查 TEST assessment。执行前后从冻结 Intake journal 的临时副本重新审核同一快照，必须保持完整原生输入相等，只允许 `reviewed_at` 更新，且生成前的审核在保存时仍须满足原生五分钟有效期。Prompt 不含此时间，因此当次审核刷新不能改变任何请求字节。实际前后绑定分别保存到 `execution-review.json`。这是固定 SYNTHETIC 测试审核，**不是正式人工语义签核或生产授权**；reviewer 不可用、资料/Plan/代码变更均停止。冻结 journal 本身不追加记录。

## 最终冻结与预算

唯一拟授权目录：`.data/seo-e-only-experiment-20261010-final/`。

| 项目 | 冻结值 |
| --- | --- |
| 客户 | SYNTHETIC-NOVACNC |
| project / task | ca318168-ce9d-424f-bbe1-fcbd7ada3b5a / 62173df6-d71f-46d6-889c-6aa88c271c35 |
| task / Plan / evidence / revision | 1 / 2 / 2 / 3 |
| 文章 | C1 / 一篇英文 NEW_RESOURCE_DRAFT；NovaCNC machining center buyer guide |
| Endpoint | POST https://api.deepseek.com/chat/completions |
| 模型 | deepseek-flash，thinking disabled，temperature 0 |
| 请求体 / 系统 Prompt | 12,002 UTF-8 bytes / 7,458 chars |
| 请求 / 输出预算 | 请求最多 16,000 bytes；输出最多 3000 tokens |
| 响应 / 原生输出 | 响应最多 65,536 bytes；原生输出最多 16,000 chars / 32,768 bytes |
| 原生文章预算 | 最多 8 blocks / 16 claims，paragraph claim 最多 300 chars，原有其他限制保留 |
| 调用边界 | 最多一次，60 秒总期限及 HTTP 各阶段上限，无 retry、redirect 或环境代理 |
| 金额 | 没有账户侧硬金额上限；只保证上述单请求和输入/输出预算，不声称费用已验证 |

冻结文件包含 `task.json`、`change-plan.json`、`intake-snapshot.json`、`intake.sqlite3`、`evidence-binding.json`、`customer-E1.txt`、`native-input.json`、完整原生 material、system prompt、精确请求体、独立质量检查清单及原始 history。`bundle.json` 绑定各文件及相关源码 hashes；发送前和响应后重新检查。请求不含认证 header；未来认证只在单独授权后读取 ignored `.env`，不落盘。

```text
bundle.json SHA-256（授权绑定）:
7f164ee4773b9f35ae39137bdafd4f737503d2124e0aea912e41fd20e50b6a2c
request.json SHA-256:
53a77560a5446b7d5e15699aa7f060112b7ae4dfe82f3e2d98ad9195edf1ed6b
system-prompt.txt SHA-256:
3f353b81a72db31854895b43dcabb5b1d6551268c8d3d9108d8ca1e9f07bb5f1
user-material.json SHA-256:
7728205dc3824b6d5189cd89976ef96ac3a004553ac8937eb7783ad072760b7d
Intake snapshot SHA-256:
83c553b06cdbbd111f0b9ff49fd32e3f882adeff76f461b8b6b7dd3f83d24e03
```

冻结目录的 `preflight.json` 保留准备时的 `PREPARED_PENDING_MOCK`，不在运行后覆写冻结文件；最终 **READY** 证据单独写入 `.data/seo-e-only-experiment-20261010-checks/final-verification.json`。本地容量见证为手写 4 blocks / 13 claims，证明结构可容纳完整 E1 及上下文；没有 tokenizer 实测，不保证真实模型 3000 tokens 必然够用。截断、结构失败、事实遗漏或限定损失时停止，不提高上限或重发。

## 实际离线结果与工作台

成功独立输出：`.data/seo-e-only-experiment-20261010-final/mock-123778b272b3452eb66f8cbf2f4be7f4/`，run `9e9113e6-9519-4f9b-a591-8871b8c44807`，artifact `d04aef4a-e18f-450f-a715-1407444c9fd2`。含 SQLite、原生文章、净化后的模型正文、Markdown Review、前后 TEST 审核绑定、独立质量清单及 diagnostics。新文章 CL3 直接引用 E1，P/S 引用为空；SQLite 重开一致，WordPress attempts=0。非法 JSON 场景另建一个 Mock 目录，只保留 diagnostics，没有候选导出。每个场景恰好一条 Mock 请求，真实请求合计 0。

通过 `prepare_web_preview(...)` 显式生成独立工作台包 `.data/seo-e-only-experiment-20261010-web/`。只使用已有 session schema、`MVPApplicationService`、`/mvp`、`/mvp/evidence`、`/mvp/article`、`/mvp/article.md`，四个 GET 均为 200。Web facade 增加对独立实验 workflow 的读取与诊断绑定，显示 Mock/真实实验来源及精确快照版本是否一致；同样文字重新提交后，版本仍显示不一致。Markdown 下载也标明 Mock；旧 fixture 的原生导出保持原行为。没有新增生成、审批或交付路由。

原 `.data/seo-mvp` 未被替换。需要查看新包时，可使用既有 factory 参数在另一个本地端口启动：

```powershell
.\.venv\Scripts\python.exe -c "import uvicorn; from foreign_trade_geo_agent.web.app import create_app; uvicorn.run(create_app(mvp_dir='.data/seo-e-only-experiment-20261010-web'), host='127.0.0.1', port=8001)"
```

打开 `http://127.0.0.1:8001/mvp/article`。本轮仅用 TestClient 验证，没有启动服务器或部署。可直接阅读已保存的 `.data/seo-e-only-experiment-20261010-checks/mvp-article.md`。任意网页新提交资料不会自动触发模型；本轮只建立固定 SYNTHETIC 单篇实验和新候选读取桥。

## 验证与限制

新增 11 项 focused tests，涵盖 E-only 请求、版本/哈希绑定、现有 DeepSeek adapter 的 MockTransport、原生 E 校验、SQLite/Markdown/Web、变更前后拒绝、审核撤销/过期、失败无候选、live 未授权无 attempt。最终相关回归 **73 tests / 26.076s / OK**，日志 `.data/e-only-experiment-focused.log`。本轮完整回归 **1697 tests / 418.990s / OK**，日志 `.data/e-only-experiment-full.log`；详情见同名 verification JSON。

迭代失败如实记录：最初新增模块尚未实现时 import 失败；首次 6 项中 1 项的 evidence_version 预期错误（既有初值是 1，首次补充后是 2）；后续 11 项中 adapter success 枚举断言误用了大写字符串，已改为枚举比较；Markdown 来源标记测试先失败，随后补齐标记并通过。已有 Starlette/httpx 弃用警告仍存在，未顺带修改依赖。

真实模型能否写出自然完整文章、原创解释和采购决策价值仍未测试；结构、引用存在及数值保留不能替代独立全文审核。后续真实成功输出仍是待审候选，不能发布或变成 WordPress payload。

## 下一步仅需单独授权的范围

须由用户单独明确授权：**仅本报告指定最终目录及 bundle hash、固定 SYNTHETIC NovaCNC E-only 快照、C1 一篇英文文章，使用 ignored `.env` 的 DeepSeek key 向上述 endpoint 发出最多一次 deepseek-flash 请求，3000 output tokens、60 秒、不重试，仅本地留存并独立全文审核**，并给出带时区的授权截止时间。CLI digest/expiry 只是绑定护栏，不能替代真人聊天授权。输入、请求、Prompt 或受绑定源码改变则授权失效。

未来唯一真实输出为冻结目录下 `live-attempt/`；在凭据加载或联网前独占预留，缺钥匙、失败、超时或崩溃也消耗该次机会，不能自动重试。本轮没有此目录，未运行 `--live`。授权不包括真实客户资料、其他模型调用、生产 Draft、P1、PostgreSQL、WordPress、发布、部署或 Git 操作。**离线 READY 后在此停止。**

本轮代码变更：新增实验脚本和测试；增量修改既有独立实验 helpers、`web/mvp_application.py` 和 `web/templates/mvp.html`；另增加本报告、verification JSON、实施计划与 ignored 实验产物。原有其他未提交改动保留。
