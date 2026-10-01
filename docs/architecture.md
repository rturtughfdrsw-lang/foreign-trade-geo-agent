# MVP Architecture

## 目标与边界

本项目面向 B2B 外贸独立站，目标是把网站诊断、AI 可见度数据、优化建议、内容规划、文章草稿和历史结果连接为可追踪的自动化流程。

当前 MVP 实现固定业务工作流、受控第三方 Adapter 与文件型历史存储；Web API 仍不在本阶段范围内。

## 架构原则

- 第一版采用固定 Workflow：按照预先定义的步骤执行，不使用会自主决定下一步的自由 Agent。
- 核心业务逻辑只依赖项目内部的统一数据结构和抽象接口。
- 所有第三方能力必须通过 Adapter 隔离；核心层和工作流不能直接依赖某个第三方项目或 SDK。
- 第三方实现应可替换：替换诊断工具、AI 可见度数据源、内容生成服务或 WordPress 客户端时，不改变核心流程语义。
- 先保持最小化；FastAPI、Pydantic、PostgreSQL 与具体 LLM/SEO 工具仅在后续已验证的需求下引入。
- WordPress 第一版只能创建 Draft，禁止自动 Publish。

## 目录职责

- `core/`：后续放置稳定的领域模型、统一数据结构与接口定义。
- `workflows/`：后续放置固定工作流的步骤编排和状态流转。
- `adapters/`：后续放置第三方工具与服务的适配实现。
- `storage/`：后续放置历史结果的持久化抽象与实现。

## 固定数据流

```text
站点 URL
  -> 网站数据获取
  -> GEO/SEO 诊断 Adapter
  -> AI visibility / brand mention / competitor Adapter
  -> 统一数据结构（core）
  -> 固定 Workflow：优化建议与 content plan
  -> 企业真实资料驱动的文章生成
  -> WordPress Adapter：仅保存 Draft
  -> 历史结果存储（storage）
```

在第一版中，Workflow 负责以确定顺序协调这些步骤；每个 Adapter 只负责将外部能力的输入与输出转换到内部约定。

## 初步组件策略

第一版优先研究以下组件，并在评估通过后才考虑接入：

- `geo-optimizer-skill`：网站 GEO/技术诊断。
- `Elmo`：AI visibility、brand mention、competitor 与历史监测。

第一版暂不集成 Voyage GEO、GEORank、GEOFlow，除非后续技术审计证明它们具备不可替代价值。

## SiteOptimizationWorkflow（第一版）

面向具体 B2B 外贸工厂英文站的优化建议采用独立、固定工作流：

```text
SiteOptimizationRequest
  -> 1 次 SiteAuditor 顶层审计
  -> 筛选 AuditEvidence 并分配 A1…A24
  -> 2 次串行 SearchProvider 搜索
  -> 筛选外部来源并分配 S1…S6
  -> 1 次 OptimizationWriter 结构化生成
  -> 引用、类型和预算验证
  -> SiteOptimizationReport（requires_human_review=True）
```

`A#` 仅表示客户站点的结构化审计观察；`S#` 仅表示 Tavily 返回并经 Workflow 校验的外部资料。编号在筛选、去重和排序后由 Workflow 分配。geo-optimizer 的 recommendations、score、band、score breakdown 和 citability improvements 不会转换成 `A#`。

第一版固定执行两个由客户人工确认的行业主题和产品词构成的英文查询。模型不能决定搜索词、追加搜索、调用工具或自动重试。搜索失败不会静默降级为仅审计报告。

生成结果只允许引用已提供的结构化 ID，不允许模型输出 URL。来源标题与 URL 由 Workflow 从可信搜索结果复制。技术修复必须引用能够支持具体问题的 `ABSENT` 或 `WARNING` 审计证据；策略核查必须引用相关 `A#` 并保留人工决策空间；内容机会必须引用 `S#`，且外部资料不能单独证明客户站点缺少某个页面。

入口页审计不能外推至所有产品页。`NOT_DETECTED` 不等于确认不存在，启发式评分不等于搜索引擎官方排名，Tavily 来源也不是 ChatGPT、Perplexity 等 AI 平台的原生 citation。报告不保证排名、AI 提及率或询盘提升。

逻辑调用上限为 1 次顶层审计、2 次 Tavily 搜索和 1 次 DeepSeek 生成；geo-optimizer 的一次顶层审计可能包含多个内部 HTTP 请求。审计通过 `asyncio.to_thread()` 调用同步端口，外层超时只会停止 Workflow 等待并阻止后续阶段，不能保证底层审计线程被强制终止。

## SiteCrawlWorkflow（有限多页面抓取）

多页面抓取是独立的固定工作流，不接入 LLM，也不修改已有优化与行业研究流程：

```text
seed URL
  -> SafeHtmlFetcher.fetch_text(/robots.txt)
  -> robots 规则与 crawl-delay
  -> SafeHtmlFetcher.fetch（exact-origin BFS）
  -> 静态 a[href] 发现
  -> TrafilaturaPageExtractor（已下载 HTML）
  -> SiteCrawlReport
```

`fetch_text()` 与 HTML 获取共用 DNS 公网地址校验、已验证 IP 连接绑定、逐跳重定向校验、响应解压限制和 `trust_env=False`。HTML 获取的默认媒体类型策略保持不变。页面重定向的下一跳还须通过 Workflow 提供的 robots 策略，目标被拒绝时不会发起下一次 DNS 或连接。

抓取任务默认强制 25 MiB wire bytes 和 50 MiB decoded bytes 的全局硬上限。robots、重定向与失败响应已消耗的响应体字节都纳入统计；并发批次会在启动前分配当前剩余额度，各 Fetcher 调用再在流式读取和解压过程中执行自己的份额，而不是等下载完成后才判断超限。全局字节预算耗尽时，报告保留已成功页面，并标记对应的停止原因与预算提前停止。

工作流按 scheme、IDNA hostname 与 effective port 实施 exact-origin；去除 fragment 和默认端口，但保留路径大小写。只发现静态 `a[href]`，新发现的非空 query URL 不进入 frontier，canonical、Open Graph 与 JSON-LD URL 不授予抓取权限。请求尝试数由 Fetcher 按实际 IP failover 和重定向逐次统计，robots 请求与页面请求共同消耗总预算。

链接优先策略是固定枚举。Core 默认使用 `document_order`，保留原有调用方的文档顺序行为；本地验证 CLI 固定使用 `b2b_content_v1`。该策略只对 frontier 队首连续的同一 depth 区间作稳定排序，因此不改变 BFS 的深度优先语义。它将已规范化 path 的每个 segment 仅 percent-decode 一次，再 `casefold()` 并按非 ASCII 字母数字边界切分；仅完整 token 命中才参与高价值、中性、低价值三档排序，同档保留原发现顺序，同一路径同时命中时由低价值覆盖高价值。所有 robots、exact-origin、query、fragment、去重与资源预算规则均在原安全边界内保持不变。验证 CLI 的 `--max-depth` 允许 0–2，默认仍为 1。

## MVP 历史持久化

历史层通过同步的 `HistoryStore` port 与工作流隔离；core 与 workflow 不依赖 `sqlite3`。MVP 使用文件型 SQLite、`PRAGMA user_version = 1`，并固定三张表：`runs`、`artifacts`、`wordpress_draft_attempts`。每次操作使用独立连接并启用、验证外键；数据库父目录必须由调用方预先创建。

`runs` 只允许一次原子的 `RUNNING -> SUCCEEDED | FAILED | NEEDS_RECONCILIATION` 转换。`artifacts` 为追加式、版本化 JSON 快照，只支持 allowlist 中的八类稳定根模型，不保存 Python 类名，不使用 `eval` 或 pickle。站点身份仅由 scheme、IDNA 规范化 hostname 与 effective port 组成，不包含凭证、path、query 或 fragment。

WordPress 投递使用独立的持久化 attempt 状态：`PENDING`、`SUCCESS`、`FAILED_DEFINITELY`、`UNKNOWN`。发送前必须先提交 `PENDING`；发送后的超时、连接中断、重定向、未确认 draft 的 2xx、格式异常成功响应以及不能排除已创建草稿的服务端失败均记录为 `UNKNOWN`。`target_site_key + request_fingerprint` 上的 partial unique index 阻止并发的 `PENDING`、`SUCCESS` 或 `UNKNOWN` 重复投递；只有 `FAILED_DEFINITELY` 可由后续人工发起的新 attempt 重试。系统不自动查询、匹配、更新或重发 WordPress 内容。

SQLite 文件会包含客户页面文本、模型输出、生成草稿以及公开引用和链接。它不得包含 WordPress 用户名、Application Password、Authorization、API key、cookie、环境 secret、原始 HTTP request/response 或原始 exception。该里程碑不提供静态加密或密钥管理；部署方必须按包含客户内容的敏感业务数据保护数据库文件、目录权限和备份。
