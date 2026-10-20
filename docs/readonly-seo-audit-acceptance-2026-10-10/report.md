# 零模型 Crawl → Packet → Audit 离线验收

日期：2026-10-10，Asia/Shanghai。交付仅为独立只读审计与导出能力。本次使用仓库现有 **合成 NovaCNC fixture**，不是 NovaCNC、COVNA、DONJOY 或其他真实网站验收。真实网站抓取、真实 LLM/付费搜索、WordPress 写入均为 0。生产 **NO-GO**、PostgreSQL **BLOCKED** 保持；没有部署、commit、push、merge 或修改冻结实验材料。

## 实现和实际调用

先阅读 AGENTS.md、商业验收准备报告、架构、`verify_site_crawl.py` 及原生三组件，并检查 git status。起始六组未提交文档保持；原生 crawler、安全策略、生产 Gate/Validator/P1、Evidence Intake、Draft、plan/runtime 和 History schema 没有修改。

新增 `audit_cli` 和独立 `audit_runtime` composition，直接复用 SafeHtmlFetcher、SiteCrawlWorkflow、TrafilaturaPageExtractor、SiteContentPacketBuilder、CrawlSeoAuditor。Auditor 消费同一次 Crawl，Packet 另外输出原生 bounded 证据；没有复制 crawler 或 SEO 算法，没有构造研究/规划/文章 writer、DeepSeek、Tavily 或 WordPress。固定 `b2b_content_v1`，通用输入 URL/fixture 目录不限定品牌；测试还用 industrial.example 验证异域 canonical 不授予抓取权限。

实际在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -B -m foreign_trade_geo_agent.audit_cli fixture `
  --fixture-dir src/foreign_trade_geo_agent/web/fixtures/novacnc `
  --output-dir docs/readonly-seo-audit-acceptance-2026-10-10/package
.\.venv\Scripts\python.exe -B -m foreign_trade_geo_agent.audit_cli verify `
  docs/readonly-seo-audit-acceptance-2026-10-10/package
```

两条命令退出码均为 **0**。不要原样重跑覆盖本包；任何已存在输出目录均被拒绝，重跑须选新目录。帮助和日常用法见 [入口文档](../readonly-seo-audit.md)。

## 实际交付文件

独立输出目录：`E:/Codex程序/foreign-trade-geo-agent/docs/readonly-seo-audit-acceptance-2026-10-10/package/`。

| 文件 | 审阅用途 |
| --- | --- |
| [input.json](package/input.json) | seed、exact-origin、预算、Packet 限额、四份合成输入文件的 SHA-256 |
| [crawl.json](package/crawl.json) | 真实执行得到的原生页面提取、资源、robots、失败与停止状态 |
| [packet.json](package/packet.json) | 原生 P1/P2 证据、保留文本/结构与截断标记 |
| [audit.json](package/audit.json) | 原生 AuditResult、15 项观察、启发式分数和建议 |
| [requests.json](package/requests.json) | MockTransport 实际收到的三次 GET；没有真实网络请求 |
| [fetches.json](package/fetches.json) | robots/HTML 内容哈希、native fetch 状态、UTC 时间、重定向候选 |
| [summary.md](package/summary.md) | 可读结果、限制和未验证项 |
| [manifest.json](package/manifest.json) | 完成性、结果分类、预算/资源、覆盖、截断及前七份文件 hash/bytes |

JSON 已实际重新读取并解析，七份文件的 SHA-256/字节数与 manifest 一致；关键输入/输出摘要、资源、范围、覆盖和失败也与导出结果交叉核对。目录中没有 INCOMPLETE 标记。完整包不是全站审计、人工批准或 SEO 指标合格证明；哈希不认证来源真实性和操作许可。

## 真实执行结果（仅合成离线链路）

| 项目 | 观察结果 |
| --- | --- |
| 执行时间 | 2026-10-10 12:49:39.803660–12:49:41.247633 +08:00；Crawl/Packet/Audit 链路约 1.422 秒 |
| seed / exact-origin | `https://novacnc.example/`；https / novacnc.example / 443 |
| 模拟访问 URL | `/robots.txt`、`/`、`/machines.html`；均为本地字节返回的 200，0 redirect |
| Crawl | 2 页，全部提取成功；0 失败；3 fetch operations / 3 HTTP attempts；wire=decoded=1,447 bytes |
| robots | 本地 robots 200、allowed；crawl-delay=null；内容 SHA-256 已记录；不是对真实站规则的判断 |
| 停止 | completed；budget_exhausted=false；outcome=sample_complete；full_site_audit=false |
| Packet | P1/P2 共 2 页；supports_absence_claims=false；packet/content/structure 均未截断 |
| Audit | success；15 项观察；heuristic score=91；band=good；不代表排名、业务效果或内容专业性 |
| 未通过指标 | 首页未观察到 H2，样本 H2 覆盖检查为 absent；最少提取正文 21 词，薄内容检查 warning |

预算始终是 5 抓取槽位、depth 1、并发 1、35 attempts、25 MiB wire / 50 MiB decoded、120 秒及现有候选/frontier 限制；本 fixture 只触达两页。未抓到的页面为未知，没有据此断言真实网站缺页。H2 的 absent 只涉及成功提取样本，不能外推网站不存在 H2。

## 验证指标与限制

已执行原生检查：当前 robots 状态；抓取/提取成功数；title 覆盖/长度/唯一性；meta description 覆盖/长度/唯一性；单一 H1 与 H2 覆盖；canonical 覆盖/有效 exact-origin/唯一性；最少正文词数；已观察内链数量。

没有验证全站覆盖、未抓到页面的存在或缺失、JavaScript 渲染、登录内容、PDF、sitemap、schema、Open Graph、noindex、noai、llms.txt、性能、真实搜索意图、索引、排名、流量、点击、询盘或收入，也没有验证合成企业/产品事实。正文默认每页 600 字符等 Packet 限额保持；其他测试中的截断保留实际 flags，并不自动把有界 Packet 宣称为全文档案。

## 未来切换真实只读审计

存在独立 `live --url --permission-record --output-dir` 入口。CLI 与 runtime 都在构造真实 transport 前要求完整许可证据记录，检查 exact-origin/seed、用途、带时区的有效期、条款引用和预算。记录不是单一布尔；记录 SHA-256 保存在 manifest。软件不认证操作者身份、站方授权或条款合法性，原记录及其引用证据必须另外保留，人工审核真实可用范围。本轮只在 MockTransport/假 resolver 下测试该装配，没有执行真实抓取。

真实执行前仍缺：用户针对选定站点及操作的独立明确授权；可审阅的授权依据和公开内容保存/分析用途；有效许可记录；当前站点 robots/条款的合法预检；允许的 exact-origin 自动发现范围和预算；实际公网 DNS/TLS、站点响应及静态提取可用性验证。授权不覆盖 robots 拒绝或安全限制；规则获取失败必须阻断。若许可只覆盖少数路径，不能以当前 origin 级入口扩大授权范围。本轮完成后停止，不自动切 live。

保留现有 SSRF/DNS/IP 绑定、逐跳重定向、exact-origin、robots/crawl-delay、页数/深度/并发/字节/时间/请求限制。输出区独占创建，文件独占写并 fsync，读回校验后移除 INCOMPLETE；故障保留标记。部分结果或预算耗尽有可用审计时 exit 3，无可用审计/robots/安全阻断 exit 1；完整诊断包通过 verify 不会改变失败 outcome。deadline 取消中的 native counters 可能不含未返回 fetch，requests 留下真实已启动尝试；manifest 明示此差异。禁止输出原始异常、header、cookie 或环境值。

## 修改文件与验证记录

实际新增：

- `src/foreign_trade_geo_agent/audit_cli.py`：fixture/live/verify 独立命令。
- `src/foreign_trade_geo_agent/audit_runtime.py`：预算、许可预检、离线注入和三组件组合。
- `src/foreign_trade_geo_agent/reporting/audit_package.py`：独占导出、完成标记、哈希及摘要交叉检查。
- `tests/test_readonly_seo_audit.py`：28 项 focused tests。
- `docs/readonly-seo-audit.md`：使用方法、状态、通用 fixture 格式和未来许可要求。
- 本目录的 report、verification 与八个实际执行产物。

仅修改既有 `README.md`，增加独立入口说明。起始未提交文档均保留，没有修改原商业报告或冻结材料。

测试过程准确记录：初次新增模块 **24 tests / 13.635s / exit 1**，一项失败为测试桩拦截了 Windows asyncio 初始化 self-pipe，并伴随未 await/unclosed-loop 警告；修正为事件循环建立后安装网络 tripwire，完整重跑 **24 tests / 14.884s / exit 0**。这是新测试适配错误，未削弱外网禁止断言或修改已有测试。随后相关十模块 **225 tests / 44.750s / exit 0**；首轮完整 discover **1,584 tests / 275.598s / exit 0**。最后追加 runtime 许可拒绝、decoded 预算、manifest 摘要不一致和未来 live 离线装配测试，并执行最终回归，结果补充于下方和 verification.json。

最终针对性命令：

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_readonly_seo_audit tests.test_verify_site_crawl tests.test_site_crawl_workflow tests.test_site_content_packet tests.test_crawl_seo_audit tests.test_safe_http_transport tests.test_runtime tests.test_cli tests.test_end_to_end_workflow tests.test_draft_execution_boundary -v
```

实际 **229 tests / 45.454s / exit 0，OK**，含新增 28 项。覆盖零 provider 构造/零 WordPress、无真实 DNS/connect、通用 seed、安全拒绝、robots 未知/拒绝、同源与越界重定向、robots 跳转策略、请求/wire/decoded/time/page 预算、部分页面失败、结构/文本截断、可读/哈希/摘要、不覆盖、导出中断标记、许可负例及 plan/Draft 回归。

最终完整测试集实际执行：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
```

**1,588 tests / 269.862s / exit 0，OK，0 failures / 0 errors / 0 skips**。未排除或跳过测试；不能把当前 checkout 全量结果当作其他工作树历史 P1 问题已经修复。上一轮报告记录的 journal 回滚、换 journal、跨进程全局消费三项 P1 失败仍为未解决历史阻断；本轮没有修改或重新包装它们。PostgreSQL 未探测/启动/验收。

`git diff --check` 实际 exit 0；另检查六份新增源码/测试/文档没有 trailing whitespace。准确运行计数、日志 SHA-256 和源码摘要在 [verification.json](verification.json)，完整原始回归日志在 ignored `.data/readonly-seo-audit-verification/`。中间加固后的新增模块还曾单独运行 27 tests / 16.394s / exit 0，最终新增 28 项均包含在 229/1,588 计数中，不额外相加。

剩余风险：只能证明本次合成静态页面上的工程链路和拒绝/导出行为；不能证明真实站可抓或业务效果。权限记录依赖人工核实，包哈希不提供签名认证或设备整体回滚保护；没有原 HTML 全文归档和自动留存到期删除机制。本次没有顺带扩展这些能力。
