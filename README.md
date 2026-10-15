# foreign-trade-geo-agent

面向 B2B 外贸独立站的固定 SEO/GEO 工作流。当前 CLI 可以生成可追踪的内容规划。生产 `plan` 和 Live API 在 Draft 执行边界 fail-closed：尚无可信任务身份、当前证据审核及 Draft 执行授权，不调用 Draft writer。既有草稿保留 `review` → `deliver` → `verify` 的独立明确批准边界。

## 本地运行

需要 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
```

`plan` 只需要：

```dotenv
DEEPSEEK_API_KEY=
TAVILY_API_KEY=
```

运行规划：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent plan `
  --site https://manufacturer.example `
  --question "What content should this industrial pump manufacturer create?" `
  --language en
```

默认历史数据库是 `.data/history.sqlite3`；可用 `--db <path>` 覆盖。原生规划成功后，当前生产入口保留前五阶段 artifacts，停止于 `content_draft`，返回 `INTAKE_EXECUTION_BLOCKED`，CLI exit 1；不会生成新的 Draft artifact。提供新 digest、旧 receipt 或一个返回允许的旧 admission 都不能授权执行。

以下是历史或隔离 TEST 成功输出的示例；当前生产入口不会产生此授权结果：

```json
{
  "run_id": "11111111-1111-4111-8111-111111111111",
  "status": "succeeded",
  "content_draft_artifact_id": "22222222-2222-4222-8222-222222222222",
  "requires_human_review": true,
  "drafts": [
    {"draft_id": "D1", "type": "SECTION_DRAFT", "title": "Selection guide"}
  ]
}
```

## 零模型只读 SEO 审计

只需要网站静态页面审计时，使用独立的零模型入口，无需 `.env`、历史数据库或模型凭据：

```powershell
.\.venv\Scripts\python.exe -B -m foreign_trade_geo_agent.audit_cli fixture `
  --fixture-dir src/foreign_trade_geo_agent/web/fixtures/novacnc `
  --output-dir .data/readonly-seo-audit-novacnc
.\.venv\Scripts\python.exe -B -m foreign_trade_geo_agent.audit_cli verify `
  .data/readonly-seo-audit-novacnc
```

输出目录必须不存在；入口原生执行 Crawl → Packet → Audit，导出 JSON、请求记录、哈希 manifest 和可读摘要。这里是合成 fixture 验收，不是真实网站。`live` 是独立的显式操作，须先取得特定站点授权并提供完整许可预检记录；本轮未授权或执行 live。状态、退出码、通用 fixture 格式和许可要求见 [零模型审计入口](docs/readonly-seo-audit.md)。不改变 `plan`、Draft 或生产 NO-GO / PostgreSQL BLOCKED。

## 人工审核（只读）

在交付前，用 `review` 只读查看某一份已持久化的草稿及其 provenance：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent review `
  --run-id 11111111-1111-4111-8111-111111111111 `
  --artifact-id 22222222-2222-4222-8222-222222222222 `
  --draft-id D1 `
  --db .data/history.sqlite3
```

`--format json` 输出同一审核视图的结构化结果（默认 `text` 供人工阅读）。

- `review` 只是只读 inspection：不创建数据库、schema、run、artifact 或 WordPress attempt，也不执行 migration。
- `review` 不等于 approval，也不改变任何 approval state；系统不记录 reviewer 或 `approved_at`。
- `review` 不调用 WordPress，也不需要任何 WordPress 凭据。
- 输出包含草稿正文、对应的 C# change context、R# opportunity，以及该草稿实际引用的 A#/P#/S# evidence provenance。

## 人工批准并交付

在 `.env` 中配置：

```dotenv
WORDPRESS_USERNAME=
WORDPRESS_APPLICATION_PASSWORD=
```

审核确认后，把规划输出中的 `run_id`、`content_draft_artifact_id` 和选定的 `D#` 传给 `deliver`；`deliver` 才是显式的 WordPress draft creation 动作：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent deliver `
  --run-id 11111111-1111-4111-8111-111111111111 `
  --artifact-id 22222222-2222-4222-8222-222222222222 `
  --draft-id D1 `
  --site https://customer.example
```

交付输出示例：

```json
{
  "selected_draft_id": "D1",
  "delivery_status": "success",
  "attempt_id": "44444444-4444-4444-8444-444444444444",
  "attempt_outcome": "success",
  "remote_post_id": 41,
  "remote_link": "https://customer.example/?p=41",
  "reconciliation_required": false
}
```

**交付只会创建 WordPress Draft，不会发布文章。** `UNKNOWN`，以及被既有 `PENDING`/`UNKNOWN` 尝试阻止的交付，都需要人工核对 WordPress 和历史记录；CLI 不会自动重试。

退出码：`0` 表示规划成功、交付成功，或已存在匹配的成功交付；`1` 表示正常工作流失败或明确交付失败；`2` 表示 CLI、配置或请求校验错误；`3` 表示需要人工 reconciliation。

## 交付后验证（verify）

`deliver` 之后，用 `verify` 独立读回已创建的 WordPress draft 状态：

```powershell
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent verify `
  --attempt-id 44444444-4444-4444-8444-444444444444 `
  --db .data/history.sqlite3
```

`--format json` 输出同一 view 的结构化结果（默认 `text` 供人工阅读）。

- `deliver` 仍然只负责 WordPress create-only + draft-only，`verify` 不会重新 create。
- `verify` 对 WordPress 的远端操作只有 `GET`，绝无 POST / PUT / PATCH / DELETE。
- 本地 verification history 是 append-only，不会改写原 create attempt。
- create outcome 与 verification outcome 是两个独立维度；`SUCCESS` 不等于 `VERIFIED`。
- verification outcome 为 `VERIFIED` / `NOT_FOUND` / `MISMATCH` / `UNKNOWN` / `UNRESOLVED`；`UNKNOWN` 与 `UNRESOLVED` 含义不同。
- `UNKNOWN` / `PENDING` 且没有 remote id 时，系统不会猜测或重新 POST；此时必须人工确认，并遵循：Do not retry create while remote state is uncertain.
- `FAILED_DEFINITELY` 不需要 remote verification，`verify` 返回 NOT APPLICABLE。
- `verify` 需要与 `deliver` 相同的 WordPress 凭据（读回 draft 需要鉴权）。

## Local Web UI: Demo and Live profiles

### 本地 SEO MVP 工作台（分析 → 补资料 → 审核导出）

复用既有 FastAPI/Jinja Web 服务，无需新增前端运行时或模型凭据。
从项目根目录执行（已有演示目录时跳过准备，保留保存的任务）：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[demo]"
# 仅首次执行；输出目录必须不存在
.\.venv\Scripts\python.exe -m scripts.prepare_web_mvp
.\.venv\Scripts\python.exe -m foreign_trade_geo_agent.web
```

打开 [SEO MVP 工作台](http://127.0.0.1:8000/mvp)。分析页只查询已保存结果，
输入 URL 不会触发抓取；本版工作台仅接入 NovaCNC 本地合成任务。
依次进入客户资料补充 → 填入合成 E1 示例 → 保存资料 → 重新核对 →
文章审核与导出 → 导出 Markdown。保存及 recheck 使用原生 Intake SQLite，
状态依次为 `WAITING_FOR_EVIDENCE`、`RECHECK_REQUIRED`、`WAITING_FOR_HUMAN_REVIEW`，
刷新或重启会恢复。UTF-8 文本最多 16,000 字符，换行统一为 LF 后保存及计算哈希。
`.txt` 读取只填入文本框，不上传原始文件或处理二进制。

分析是本地 fixture 经原生 Crawl/Audit/Plan 保存的实际结果；文章是离线合成 writer
**预先生成的独立 TEST-only 候选**，不是当前提交生成的文章。候选冻结原文和交互资料
分别保存于 `.data/seo-mvp/candidate/` 与 `.data/seo-mvp/interactive-intake.sqlite3`。
候选始终 `UNREVIEWED`、质量待审；文本相同也不等于相同版本或正式人工签核。
本工作台没有批准、生产 Draft 执行或 WordPress 操作。既有 Demo/Live 路由继续保留。

文章页支持查看 P/S/E 历史来源、编辑完整正文、填写意见并保存本地版本，以及标记
“待审核 / 需要修改 / 本地审核完成”。v0 保留原始正文，后续记录追加至工作台目录内
`local-draft-review.sqlite3`，绑定原生 Draft 摘要和冻结证据版本；刷新、重启后可恢复。
每次正文变化都会重置为待审核并保持 `PENDING_REVALIDATION`，旧引用映射仅对应原文，
不自动验证改写。本地完成也不构成可信签核或执行许可。页面可回看并导出指定版本；
正文最多 16,000 字符、意见最多 2,000 字符、每篇最多 100 次保存。
真实 DeepSeek 历史候选的浏览器实操、独立本地入口及验证记录见
[文章本地审核与修订验收](docs/seo-article-review-mvp-2026-10-10.md)。

保存版本后，可在同一文章页点击“重新核验此版本”，查看原陈述、修订文字及逐项来源绑定。
最小本地核验只处理正文不变或唯一末尾 CTA 替换、此前全文逐字不变的情况；重新读取
当前 Intake，并重跑原生 Draft 技术校验。填写必需意见、选择明确复核结论并确认核对后，
结果追加至 `local-draft-revalidation.sqlite3`，绑定具体文章版本、正文和证据摘要。
技术规则通过且本地复核确认后显示 `LOCAL_REVALIDATION_COMPLETE`；有问题、未知改写、
事实/条件/范围变化或证据变化仍为 `PENDING_REVALIDATION`。新版本不能继承旧记录。
来源绑定与词汇检查不证明语义真实性；本地操作员未认证，不产生正式可信签核或生产权限。
浏览器验收与具体边界见 [修订稿重新核验验收](docs/seo-article-revalidation-mvp-2026-10-10.md)。

界面验收、截图、文件清单与限制见 [本轮交付记录](docs/seo-web-mvp-2026-10-10.md)。

Web 单次生成交互（隔离 Mock，真实请求默认且强制禁用）：

```powershell
# 新目录会离线准备合成任务；已有目录恢复记录，绝不覆盖或重新执行。
.\.venv\Scripts\python.exe -m scripts.web_generation_demo --directory .data/web-generation-demo --port 8025
```

打开 [生成工作台](http://127.0.0.1:8025/mvp/generate)，选择任务并补充合成 E1、
重新核对 Plan，再点击生成。页面显示模型、预算、证据版本和状态；成功后进入既有审核、
修改及 Markdown 导出。响应没有 usage 时明确显示未返回，不推算 Token。相同绑定的重复
提交、刷新、服务重启及失败中断均不重试；要重做隔离演示，请使用新的离线目录。

此启动器只注入精确合成资料的 `MockTransport`；普通 Web 启动不会启用生成，
页面字段不能开启联网、选择凭据或授予生产权限。生产 Gate / P1 / PostgreSQL 保持原状。
边界、实际浏览器记录及验证结果见 [Web 生成验收](docs/seo-web-generation-mvp-2026-10-10.md)。

Install the optional Web dependencies and start the loopback-only server from
the repository root:

```powershell
python -m pip install -e ".[demo]"
python -m foreign_trade_geo_agent.web
```

Open `http://127.0.0.1:8000`. The server binds only to the local loopback
interface and offers two deliberately separate modes:

- The **Demo profile** uses the fixed NovaCNC snapshot, requires no Tavily or
  DeepSeek keys, performs no real network calls, and stores history at
  `.data/demo-ui/history.sqlite3`. Its deterministic delivery and verification
  screens use a local mock WordPress boundary.
- The **Live profile** accepts one public HTTPS URL, an editable SEO goal, and
  English output. It requires both `TAVILY_API_KEY` and `DEEPSEEK_API_KEY` and
  stores history at `.data/live-ui/history.sqlite3`. Missing provider
  configuration leaves Demo usable and rejects Live before creating a job or
  run.

Demo Mode does not contact customer websites, model or search providers, or a
real WordPress service.

Live accepts normalized URLs up to 2048 characters and rejects credentials,
fragments, localhost, private/link-local/reserved literals, and non-HTTPS
schemes. DNS is checked at each connection and redirect through the pinned-IP
safe fetcher. A TUN returning a `198.18.0.0/15` Fake-IP is rejected by design;
configure the TUN DNS mode to return the public address rather than weakening
the safety policy.

The production Live crawl is bounded to 5 pages, depth 1, one concurrent
request, 35 total request attempts, 25 MiB wire bytes, 50 MiB decoded bytes,
and 120 seconds. It observes robots rules and exact-origin redirects. The audit
uses only fields retained from successful crawl pages: crawlability/extraction,
HTML title and meta description, headings, canonical URLs, extracted word
count, and observed internal links. It does not claim schema, Open Graph,
noindex, noai, or `llms.txt` coverage.

**Live stops before Draft execution and does not call WordPress.** Native Results
and Change Plan remain readable when Draft admission refuses the run; Draft is
unavailable. Historic successful drafts remain readable. WordPress delivery
remains an optional, separate, explicitly approved Demo/CLI operation. One
process permits only one active Live Web analysis; refresh can recover terminal
state from the Live database but does not resume an interrupted run.

### Operator-only manual Live smoke

This check is operator-only and must not run in automated tests or CI. It makes
real crawl, Tavily, and DeepSeek calls and therefore requires explicit approval
for the chosen public site.

1. Set `TAVILY_API_KEY` and `DEEPSEEK_API_KEY`, then run
   `.\.venv\Scripts\python.exe -m foreign_trade_geo_agent.web`.
2. Open `http://127.0.0.1:8000/`, choose Live Analysis, and enter an approved
   public HTTPS URL.
3. Confirm the five planning stages and the fail-closed Draft boundary, then
   inspect Results and Change Plan. Record the run ID, hostname, page count,
   crawl stop reason, and that no Draft artifact/writer call occurred.
4. Confirm the target evidence is site-specific, no NovaCNC copy appears, and
   no delivery route or WordPress call occurs.

For an operator-controlled CLI diagnostic, run `plan` with an approved HTTPS
site and a separate `--db` path; do not run `deliver`. Provider and crawl
failures shown by the Web or CLI are fixed sanitized messages, never raw
provider payloads, credentials, or stack traces.
