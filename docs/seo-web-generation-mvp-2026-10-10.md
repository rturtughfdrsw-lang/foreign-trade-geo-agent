# Web 生成最小集成验收 · 2026-10-10

本轮只接入现有 FastAPI/Jinja 工作台。使用 MockTransport 完成新请求，未经真实 DeepSeek 联网、余额查询、客户站点抓取或 WordPress 操作。没有修改生产 Gate、P1 重复消费或 PostgreSQL 阻断；没有部署或 Git 写操作。

## 打开与复现

本轮保留地址：[生成工作台](http://127.0.0.1:8025/mvp/generate)、[文章 v1](http://127.0.0.1:8025/mvp/article?version=1)。

数据目录 `.data/web-generation-20261010/`。已经成功的绑定只能读取，不会重新生成。

```powershell
.\.venv\Scripts\python.exe -m scripts.web_generation_demo --directory .data/web-generation-20261010 --port 8025
# 独立重做：指定另一个尚不存在的目录；切勿手动删除 reservation 来重试。
```

普通 `python -m foreign_trade_geo_agent.web` 默认没有执行器。演示启动器使用服务端注入的合成 profile 和严格 `httpx.MockTransport` 类型约束；HTTP 表单只接受 CSRF 与绑定摘要。表单不能选择网站、身份、模型、凭据、路径或 live 模式。此版只配置一个合成任务；入口从现有内容任务链接选择，未引入任务管理系统。

## 实现与边界

- 复用 DeepSeek 原生请求 schema、ContentDraftWorkflow、Validator/Finalizer、SQLiteHistoryStore/Reader、ContentDraftReviewWorkflow，以及现有本地修订、重新核验和导出。
- 将已有实验的 OneShotTransport、响应接收、敏感内容检查和留存抽到 `adapters/retained_deepseek.py`。旧实验通过薄包装调用同一实现；同步/异步原生校验均可接入。原始响应先安全落盘，随后解析；失败候选独立保存，不作为成功 Draft。
- 原生 Workflow 新增 `max_repair_attempts=0` 选项；原默认行为不变，Web 禁止修复重试。真实模型 HTTP 不在 CapturedWriter 中发生，它只将已安全接收的文本交给原生 Workflow 校验。
- 当前任务完整对象、P/S/Plan 原生范围和完整客户文本必须匹配服务端测试 profile；生成不硬编码 NovaCNC 的 run ID、artifact ID 或 E1 内容。NovaCNC fixture 读取留在离线启动脚本。未来隔离测试可替换 profile；真实客户准入仍需另一项明确授权开发。
- 绑定由当前 Intake 摘要、精确请求摘要及 MOCK 模式构成，包含任务/Plan/证据版本。独占目录创建先消费绑定，再接收模型响应；跨页面、并发相同提交、刷新和进程重启均不会重新消费。缺少完成记录的 reservation 永不自动恢复。每个目录最多约 40 个记录项，无持久队列或重试功能。
- GET 只读展示；首次 POST 后立即重定向到状态页，页面仅以 GET 轮询。服务端提交窗口五分钟；执行前后核对当前绑定与 profile，最终保存期间持有既有 Intake snapshot guard。
- 成功原生 Draft 保存在本次 attempt 的 History SQLite，原 candidate/history 不覆盖。Review 页动态选择新成功候选；新候选有独立 origin 哈希，原本修订不混用。指针写入失败不能显示成功。
- 预算保持模型 deepseek-flash、thinking disabled、temperature 0、最大输出 3000 Token、HTTP/总请求 60 秒、单请求且零自动重试、请求 16000 字节、响应 65536 字节及原生正文预算。Mock 不计费；未声称精确 Token 预估或账户金额上限。
- 实际响应 usage 只取原有数字白名单，缺失则为空。模拟 usage 明示为模拟值，不是计费记录。敏感或不可安全检查的响应显式拒绝留存；不伪装为删改后的原始响应。HTTP 不提供原始留存文件下载接口。
- 本地操作员意见、TEST-only 引用结构校验和真实人工签核互相独立。生产权限始终为 false。

## 实际浏览器验收

使用可见的 Codex 内置浏览器，独立端口和全新离线目录，执行以下操作：

1. 从分析页选择现有内容任务；资料缺失时“生成文章”禁用。
2. 填入合成 E1 并保存，确认 Plan 尚未重新绑定时仍禁止生成。
3. 执行已有 recheck，任务/Plan/证据/修订为 `1 / 2 / 2 / 3`。
4. 进入生成页，检查模型、3000 Token 上限、预算、P/S/E 范围及原文；点击生成一次。
5. 观察 RUNNING → SUCCEEDED；请求次数 1、真实请求 0、零重试、COMPLETE_RESPONSE、usage 未返回。
6. 进入已有 Review 页，展开完整 E-only 原文及冻结版本；E1 → CL3，未改绑为 P/S。
7. 只修改末尾 CTA，填写明确不构成签核的本地修改说明，保存新版本 v1。
8. 看到 PENDING_REVIEW / PENDING_REVALIDATION；重启本轮服务并刷新，原生候选、v1 正文及说明均恢复。
9. 在两个额外隔离目录的故障服务器实际点击生成：请求超时显示 REQUEST_FAILED / REQUEST_TIMEOUT、请求数 1、usage 未返回；无效原生候选显示 VALIDATION_FAILED / JSON_FORMAT、原始响应与失败文本保留、不出现成功文章链接。后者返回的模拟 usage 为 prompt=50、completion=5、total=55，页面明确标为模拟数值而非计费记录。刷新失败页后仍只执行一次。故障服务器验收后关闭，主演示服务保留。

本轮新生成的 Run `3597021c-e670-4fb7-8e72-e3524f9b9f49`，Draft artifact `6154ebf8-0988-48c6-9ca1-8b17cb1c954a`。这些只记录验收结果，没有写进通用逻辑。

截图位于 [验收目录](seo-web-generation-acceptance-2026-10-10/)：生成前、生成中、成功、E 引用、保存版本、重启恢复、待重新核验、请求失败、校验失败与模拟 usage。

![修改后的 v1 保持待重新核验](seo-web-generation-acceptance-2026-10-10/07-revision-pending.png)

## 自动验证

新增 11 项聚焦测试覆盖：默认禁用、完整链路与恢复/修改、缺证据/过期绑定/伪造权限、请求失败与 Validator 拒绝、并发重复提交与重启、过期提交窗口/任务/Plan/证据变化、执行中证据变化、敏感输出拒绝留存、选择指针写失败、CSRF/Host/精确字段、未完成 reservation 禁止重试。

本轮曾运行相关 102 项，出现 1 个旧断言失败：旧测试要求 `/mvp/generate` 不存在。本轮新增路由后改为验证路由默认无执行器、不能发起生成、不会创建 reservation；其他安全断言保留。另用故障测试暴露并修正“原生 Draft 保存后选择指针写失败仍显示成功”的问题。过期版本测试原先模拟了与真实 SQLite 不一致的快照，导致展示层 fail-closed 503；改为直接验证生成服务的 409 拒绝以及零请求。

最终聚焦命令：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web_generation tests.test_seo_e_only_experiment.EOnlyExperimentTests.test_mock_native_persistence_review_and_existing_web_pages -v
```

实际结果 12 项通过，日志 `.data/web-generation-targeted.log`。

完整回归实际执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

实际结果 **1757 项通过，342.798 秒，退出码 0**；日志 `.data/web-generation-full-regression.log`。日志含 Starlette/httpx 弃用提示、asyncio 慢任务诊断和启动器测试预期的端口占用消息，没有测试失败。没有安装或更新依赖。

另外实际核对持久化文件：响应字节摘要、原生 Review 的 E1 → CL3 且 P/S 为空、当前绑定匹配、仅一个成功 attempt、v1 待核验、零 WordPress attempts；两个浏览器失败目录无成功指针/原生 Draft，Validator 失败文本与原始候选逐字一致，模拟 usage 原样保留。断言通过，见 [verification.json](seo-web-generation-acceptance-2026-10-10/verification.json)。首次辅助核对误用了相对路径，触发现有 Review SQLite URI 的绝对路径要求；改为与 Web composition 一致的绝对路径后通过，未改变产品代码。

## 真实 Web 调用的精确阻断及下一步

此版 Web 执行器强制只接受 MockTransport，没有读取 `.env` 或构造 live transport 的分支。现有 `DraftCustomerEvidence` 合约仅允许 `TEST_ONLY_SUPPORTED_NOT_HUMAN_SIGNOFF`；`EvidenceIntakeDraftAdmission` 绑定本身不能提供生产执行目的，原生生产 Gate 仍报 `INTAKE_EXECUTION_BLOCKED`。不能用此页、本地审核意见、TEST 身份或请求字段跨越这些限制。P1 与 PostgreSQL 也没有被此集成解决，生产仍为 NO-GO。

下一步最小受控真实实验无需开启生产 Web：用现有 `prepare_seo_e_only_experiment` 在全新隔离目录冻结输入/代码/精确请求，重跑 Mock 留存预检；由用户明确授权对应 bundle SHA256、合成任务、endpoint/model、单次请求、3000 输出 Token、60 秒、零重试及有效期后，通过现有 isolated runner 执行一次，随后读取原生持久化结果并创建已有 Web preview。代码抽取改变了实验代码摘要，不能直接复用旧 bundle 的授权；必须重新冻结/校验。全程仍无生产权限、无 WordPress 操作，真实返回缺 usage 时继续显示未返回。

如果下一步要求“直接从 Web 按钮触发真实调用”，还需单独设计和授权服务端可信、可撤销且一次性绑定精确输入/预算/有效期的隔离 live capability，并接入已有安全 transport；它不能借用生产 Gate 或 TEST-only 结构判断作为批准。真实客户生产开放还需要可信人工语义签核及生产执行目的合约，另行处理既有 Gate/P1/PostgreSQL 阻断。本轮不实施这些内容。

## 本轮文件

新增：`src/foreign_trade_geo_agent/adapters/retained_deepseek.py`、`src/foreign_trade_geo_agent/web/generation.py`、`src/foreign_trade_geo_agent/web/templates/mvp_generation.html`、`scripts/web_generation_demo.py`、`tests/test_web_generation.py`、本报告及截图。

增量修改：`scripts/prepare_seo_article_experiment.py`、`src/foreign_trade_geo_agent/workflows/content_draft.py`、`src/foreign_trade_geo_agent/web/app.py`、`web/mvp_application.py`、`web/mvp_routes.py`、`web/templates/mvp.html`、`web/static/mvp.js`、`tests/test_seo_e_only_experiment.py`、`README.md`。这些文件的前序未提交工作已保留。
