# 零模型只读 SEO 审计入口

此入口是独立的 composition：SafeHtmlFetcher → SiteCrawlWorkflow → SiteContentPacketBuilder / CrawlSeoAuditor → 文件包。Auditor 使用同次 Crawl 的成功提取页面；Packet 是另一份有界原生证据选择，不把 Packet 的截断正文当作完整审计输入。没有构造研究、规划、Draft、搜索、模型或 WordPress provider，不读取 `.env` 或写 History。现有 plan/deliver 和 artifact schema 保持。

## 离线运行

从仓库根目录，完成 README 的 editable install 后：

```powershell
.\.venv\Scripts\python.exe -B -m foreign_trade_geo_agent.audit_cli fixture `
  --fixture-dir src/foreign_trade_geo_agent/web/fixtures/novacnc `
  --output-dir .data/readonly-seo-audit-novacnc
.\.venv\Scripts\python.exe -B -m foreign_trade_geo_agent.audit_cli verify `
  .data/readonly-seo-audit-novacnc
```

`fixture` 固定为 `synthetic_fixture`，使用本地字节、固定测试 DNS 答案和 HTTPX MockTransport，仍经过原生安全 fetcher；没有真实 DNS/HTTP。不能把获得许可的真实快照假报为合成数据后当成真实网站验收；本版不提供 authorized_snapshot 身份摄入入口。

通用 fixture 目录需要 `manifest.json`（至少 `{"display_url":"https://industrial.example/"}`）、`robots.txt` 和静态 `.html`。根 `index.html` 映射 `/`，其余文件按相对路径映射；可用 `--url` 明确覆盖 seed。不存在的 fixture 路径仅在本次重放中返回 404，不证明真实站点不存在。输入限制为至多 250 个路由文件、单文件 4 MiB、总计 25 MiB；记录实际使用文件的 SHA-256。禁止文件链接逃出目录。并不要求特定行业或品牌。

默认和最大预算：5 页面抓取槽位、depth 1、并发 1、35 HTTP attempts、25 MiB wire、50 MiB decoded、200 候选链接/页、250 frontier、120 秒。`--max-pages 1..5`、`--max-depth 0..1` 只可缩小范围。失败页面也消耗页面槽位；robots、重定向与 IP failover 消耗原生请求预算。fetcher 仍执行自己的每响应限额、超时、IP 绑定、DNS/SSRF 和逐跳 exact-origin/robots 检查；静态 HTML 提取保留既有字节、节点、正文、结构与进程限制。robots 与 crawl-delay 原生行为保持；取得失败/未知绝不当成允许。确认为 404 的响应保留原生 `NOT_FOUND` 语义，并不代表已获内容使用许可。

## 文件、完成性与退出码

每次必须使用全新输出目录。即使目录为空也拒绝复用；先独占创建目录及 `INCOMPLETE.json`，再执行抓取。文件独占写入、flush/fsync，manifest 最后写入；读回解析并核对哈希后才移除 INCOMPLETE。程序中断、磁盘失败或未处理异常会留下明确不可信标记；不要手动删除标记使它看起来成功。未处理错误仅输出固定消息，不保存原始异常。此机制用于检测不完整输出，不提供对恶意改写或存储设备整体回滚的签名保证。

| 文件 | 内容 |
| --- | --- |
| input.json | seed、exact-origin、实际配置预算、Packet 限额和来源分类/输入哈希 |
| crawl.json | 原生 CrawlReport 页面、失败类型、资源、停止和 robots 状态；失败 error 采用固定诊断 |
| packet.json | 原生 Packet JSON，含 P#、观察范围、文本/结构截断标记 |
| audit.json | 原生 AuditResult、启发式分数、逐项观察和建议 |
| requests.json | 实际 HTTP 尝试、响应头已返回状态、URL、GET 方法与 UTC 时间；无 header/body/cookie |
| fetches.json | 原生 fetch/fetch_text 调用结果、内容 SHA-256、时间与 redirect 候选；候选可能未访问 |
| summary.md | 可读的状态、覆盖检查与未验证项 |
| manifest.json | 完成性、运行状态、预算、来源、覆盖、截断、输入/输出摘要及上述七个文件的字节数/SHA-256 |

重定向被拒绝的目标不计为实际访问。`response_received` 表示已取得响应头，不保证正文下载完整；看 fetches 与 Crawl 的结果。发生 deadline 取消时，原生资源计数可能不包含尚未返回的 fetch，requests 仍保留已启动 HTTP 尝试，manifest 明示此区别。诊断 URL 移除 credentials/query/fragment；seed 禁止 credentials 和非空 query。页面文本/结构为获准保留的观察证据，不导出原始 HTTP 响应或环境值。操作者须确保输入文件/许可记录不含秘密或不应留存的内容。

| 执行结果 | audit 命令 exit | 含义 |
| --- | --- | --- |
| sample_complete | 0 | 当前有限范围执行完毕；不表示全站覆盖、指标合格或真实站验收 |
| partial / budget_exhausted 且有可用审计 | 3 | 保存部分结果，不能按完整采样成功验收 |
| blocked_robots_or_safety / failed_no_usable_pages / 无可用页的预算停止 | 1 | 明确失败或阻断，仍导出能得到的 Crawl/Packet/失败 Audit |
| 预检/导出错误 | 1 | 不发起依赖操作或保留 INCOMPLETE；不伪造模型结果 |
| 命令语法错误 | 2 | argparse 拒绝执行 |

`verify` exit 0 仅验证文件包完整性、JSON 可读性及哈希；失败运行的完整诊断包也可通过 integrity 检查，必须另读 outcome/audit_status。Packet 截断不等于文件包不完整，截断标记和保留范围始终输出。未抓到页面为未知；缺少某字段仅针对成功提取样本。

## 将来 live 的独立许可预检

本次仅授权 fixture 和 MockTransport，没有真实站点请求。未来先取得具体 origin/seed 的人工操作授权、检查站点规则及内容保存用途，审核许可记录所引用的原始证据后，才可显式运行：

```powershell
# 仅作为未来调用方法；未在本次执行。
.\.venv\Scripts\python.exe -B -m foreign_trade_geo_agent.audit_cli live `
  --url https://authorized-industrial.example/ `
  --permission-record <local-permission-record.json> `
  --output-dir <new-output-directory>
```

许可 JSON 必须恰好包含下列字段。不要放 API key、cookie、密码或带 token 的引用 URL；原始授权证据应在外部受控位置保存，可由 reviewer 通过本地记录的引用核对。导出包只保存该记录的 SHA-256 与声明类别，不导出其自由文本；审核时必须同时保留原记录和所引用证据。

```json
{
  "operator": "named responsible operator",
  "authority_basis": "specific authority and permitted collection/retention use",
  "authorization_reference": "reviewable local grant reference",
  "seed_url": "https://authorized-industrial.example/",
  "exact_origin": {"scheme": "https", "host": "authorized-industrial.example", "port": 443},
  "authorized_at": "<timezone-aware ISO timestamp>",
  "expires_at": "<timezone-aware ISO timestamp>",
  "purpose": "readonly_seo_audit",
  "terms_url": "https://authorized-industrial.example/terms",
  "terms_reviewed_at": "<timezone-aware ISO timestamp>",
  "retention_scope": "specific allowed local storage scope and duration",
  "request_limits": {
    "max_pages": 5, "max_depth": 1, "max_concurrency": 1,
    "max_request_attempts": 35, "max_total_wire_bytes": 26214400,
    "max_total_decoded_bytes": 52428800, "max_candidate_links_per_page": 200,
    "max_frontier": 250, "max_runtime": 120.0
  }
}
```

代码检查字段、用途、seed/exact-origin、时间有效性、各项预算不扩大；一个 `authorized: true` 会被拒绝。这是操作者声明及可审证据记录的预检，不是身份认证、签名授权系统或自动法律许可判断。代码不能认证 grant 的真实性、自动确认条款允许或到期删除资料；需要人工在执行前完成这些条件。权限必须覆盖当前 exact-origin 范围内自动发现的公开静态 HTML；更窄许可须另行设计路径约束，不可借此入口扩大范围。用户授权、许可记录或页面公开可访问都不覆盖 robots 拒绝、访问控制或安全限制。

Live 将使用原生 SystemHostResolver 和经过安全校验的 IP pinned transport，分类为 `public_web_observation`。本轮只有 MockTransport 验证，真实 DNS/TLS、站点规则、动态渲染、规模适配和来源真实性仍未验；不得自动切换 live、以 plan 代替或把合成通过计作这些条件通过。生产 NO-GO、PostgreSQL BLOCKED、Draft 的人审边界保持。

只验证静态抓取/提取、title、description、H1/H2、canonical、正文词数、已观察内链与当前 robots 状态。索引/排名/搜索意图/流量/询盘、JavaScript、登录内容、PDF、sitemap、schema、Open Graph、noindex、noai、llms.txt、性能和企业事实均未验证。
